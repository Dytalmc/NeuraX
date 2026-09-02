import os
import sys
import json
import time
import shutil
import subprocess
import threading
import zipfile
import requests
from pathlib import Path
import re
from typing import List, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from neurax.core.config import get_dot_neurax_dir
from neurax.core.java_finder import JavaFinder
from neurax.core.logger import Logger
from neurax.core._silent_proc import popen_no_window, run_silent, SILENT_CREATIONFLAGS
from neurax.core._streaming_dl import stream_download
from neurax.core.launcher import get_required_java_major

def kill_server_process_by_folder(folder_path: Path):
    if not folder_path or not folder_path.exists():
        return
    resolved = folder_path.resolve()
    folder_str_win = str(resolved).lower().replace("/", "\\")
    folder_str_posix = str(resolved).lower().replace("\\", "/")

    if sys.platform == "win32":
        try:
            ps_win = folder_str_win.replace("'", "''")
            ps_posix = folder_str_posix.replace("'", "''")
            ps_cmd = (
                f"Get-CimInstance Win32_Process | "
                f"Where-Object {{ $_.CommandLine -and ($_.CommandLine.ToLower().Contains('{ps_win}') -or $_.CommandLine.ToLower().Contains('{ps_posix}')) }} | "
                f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"
            )
            # Run PowerShell with our silent creation flags
            # (CREATE_NO_WINDOW | DETACHED_PROCESS |
            # CREATE_NEW_PROCESS_GROUP) so killing the server never
            # briefly flashes a powershell.exe console window.
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=SILENT_CREATIONFLAGS,
                    timeout=5,
                )
            except Exception:
                pass
        except Exception:
            pass

        try:
            # wmic has been deprecated and frequently flashes a console;
            # use CIM directly via PowerShell instead, with the same
            # silent flags. We collect (PID, commandline) pairs and kill
            # only the ones that look like our server folder.
            ps_lookup = (
                "Get-CimInstance Win32_Process "
                "-Filter \"Name='java.exe' or Name='javaw.exe'\" "
                "| Select-Object ProcessId,CommandLine "
                "| ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
            )
            lookup = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_lookup],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=SILENT_CREATIONFLAGS,
                timeout=5,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            for line in (lookup.stdout or "").splitlines():
                if "|" not in line:
                    continue
                pid_str, cmdline = line.split("|", 1)
                cmdline_low = cmdline.lower()
                if folder_str_win in cmdline_low or folder_str_posix in cmdline_low:
                    pid = pid_str.strip()
                    if pid.isdigit():
                        try:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", pid],
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                creationflags=SILENT_CREATIONFLAGS,
                                timeout=5,
                            )
                        except Exception:
                            pass
        except Exception:
            pass
    else:
        try:
            cmd = f"pkill -f '{folder_str_posix}'"
            subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
        except Exception:
            pass

def _force_rmtree(target_path: Path, max_retries: int = 5, delay: float = 0.3) -> bool:
    if not target_path.exists():
        return True

    def _handle_remove_readonly(func, path, exc_info):
        import stat
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass

    for _ in range(max_retries):
        if not target_path.exists():
            return True
        try:
            for root, dirs, files in os.walk(target_path):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), 0o777)
                    except Exception:
                        pass
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o777)
                    except Exception:
                        pass

            if sys.version_info >= (3, 12):
                def _on_exc(func, path, exc):
                    import stat
                    try:
                        os.chmod(path, stat.S_IWRITE)
                        func(path)
                    except Exception:
                        pass
                shutil.rmtree(target_path, onexc=_on_exc)
            else:
                shutil.rmtree(target_path, onerror=_handle_remove_readonly)
        except Exception:
            pass

        if not target_path.exists():
            return True

        time.sleep(delay)

    if target_path.exists() and sys.platform == "win32":
        try:
            cmd = f'cmd.exe /c rmdir /s /q "{target_path.resolve()}"'
            subprocess.run(
                cmd,
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=SILENT_CREATIONFLAGS,
            )
        except Exception:
            pass

    return not target_path.exists()

def _is_valid_loader_jar(jar_path: Path, loader: str) -> bool:
    if not jar_path or not jar_path.exists() or jar_path.stat().st_size == 0:
        return False
    loader_low = loader.lower().strip()
    if loader_low in ("vanilla", ""):
        try:
            with zipfile.ZipFile(jar_path, "r") as zf:
                if zf.testzip() is not None:
                    return False
                names = [n.lower() for n in zf.namelist()]
                has_modloader = any(
                    "fabricmc" in n or 
                    "quiltmc" in n or 
                    "org/bukkit" in n or 
                    "io/papermc" in n or
                    "cpw/mods" in n or
                    "net/minecraftforge" in n or
                    "net/neoforged" in n
                    for n in names
                )
                return not has_modloader
        except Exception:
            return False
    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            names = [n.lower() for n in zf.namelist()]
            if loader_low == "fabric":
                return any("fabricmc" in n or "fabric-server-launch" in n or "fabric" in n for n in names)
            elif loader_low == "quilt":
                return any("quiltmc" in n or "fabricmc" in n or "quilt" in n or "fabric" in n for n in names)
            elif loader_low in ("paper", "purpur", "folia", "spigot", "bukkit", "leaf", "pumpkinmc", "pumpkin"):
                return any(
                    "paper" in n or 
                    "papermc" in n or 
                    "bundler" in n or 
                    "purpur" in n or 
                    "folia" in n or 
                    "spigot" in n or 
                    "bukkit" in n or 
                    "craftbukkit" in n or 
                    "org/bukkit" in n or 
                    "io/papermc" in n or 
                    "destroystokyo" in n or 
                    "leavesmc" in n or 
                    "pumpkin" in n
                    for n in names
                )
            elif loader_low == "forge":
                return any("forge" in n or "minecraftforge" in n or "fml" in n or "cpw" in n for n in names)
            elif loader_low == "neoforge":
                return any("neoforge" in n or "neoforged" in n or "forge" in n or "minecraftforge" in n for n in names)
            return True
    except Exception:
        return False

class LocalServerManager(QObject):
    servers_changed = pyqtSignal()

    def __init__(self, neurax_dir: Path = None):
        super().__init__()
        self.servers_dir = get_dot_neurax_dir() / "servers"
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        self.logger = Logger.get_instance()

    def list_servers(self) -> List[Dict[str, Any]]:
        servers = []
        if not self.servers_dir.exists():
            return servers
        for folder in self.servers_dir.iterdir():
            if folder.is_dir():
                cfg_path = folder / "server.json"
                if cfg_path.exists():
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            cfg = json.load(f)
                            cfg["folder_name"] = folder.name
                            cfg["server_dir"] = str(folder)
                            servers.append(cfg)
                    except Exception:
                        pass
                else:
                    cfg = {
                        "name": folder.name,
                        "loader": "Vanilla",
                        "version": "1.20.4",
                        "max_ram": 2048,
                        "port": 25565,
                        "folder_name": folder.name,
                        "server_dir": str(folder)
                    }
                    servers.append(cfg)
        return servers

    def get_server(self, folder_name: str) -> Dict[str, Any]:
        s_dir = self.servers_dir / folder_name
        cfg_path = s_dir / "server.json"
        if cfg_path.exists():
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    cfg["folder_name"] = folder_name
                    cfg["server_dir"] = str(s_dir)
                    return cfg
            except Exception:
                pass
        return {
            "name": folder_name,
            "loader": "Vanilla",
            "version": "1.20.4",
            "max_ram": 2048,
            "port": 25565,
            "folder_name": folder_name,
            "server_dir": str(s_dir)
        }

    def delete_server(self, folder_name: str):
        target = self.servers_dir / folder_name
        if target.exists() and target.is_dir():
            kill_server_process_by_folder(target)
            time.sleep(0.3)
            success = _force_rmtree(target)
            if not success:
                self.logger.warning(f"Error deleting server folder {target}")
            self.servers_changed.emit()

    def reinstall_server(self, folder_name: str):
        target = self.servers_dir / folder_name
        if target.exists() and target.is_dir():
            kill_server_process_by_folder(target)
            time.sleep(0.3)
            for item in target.iterdir():
                nl = item.name.lower()
                if nl in ("mods", "plugins", "world", "server.json", "server.properties") or nl.startswith("world"):
                    continue
                try:
                    if item.is_dir():
                        _force_rmtree(item)
                    else: 
                        os.chmod(item, 0o777)
                        item.unlink()
                except Exception as e:
                    self.logger.warning(f"Failed to remove item {item} during reinstall: {e}")

            eula_path = target / "eula.txt"
            with open(eula_path, "w", encoding="utf-8") as f:
                f.write("eula=true\n")

            cfg = self.get_server(folder_name)
            loader_low = cfg.get("loader", "Vanilla").lower().strip()
            if loader_low in ("paper", "purpur", "folia", "spigot", "bukkit", "leaf", "pumpkinmc", "pumpkin"):
                (target / "plugins").mkdir(exist_ok=True)
            elif loader_low in ("fabric", "quilt", "forge", "neoforge"):
                (target / "mods").mkdir(exist_ok=True)
            (target / "world").mkdir(exist_ok=True)
            self.servers_changed.emit()

class CreateServerWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str, str)
    # Per-line log message — streamed straight into the in-launcher
    # "new server launching" log panel so the user sees exactly which
    # jar / library is being downloaded. Like a real Minecraft
    # launcher's server console.
    log_message = pyqtSignal(str)

    def __init__(self, name: str, version: str, loader: str, max_ram: int,
                 port: int = 25565, java_path: str = "auto",
                 server_mgr=None, custom_folder_name: str = None):
        super().__init__()
        self.server_name = name
        self.version = version
        self.loader = loader
        self.max_ram = max_ram
        self.port = port
        self.java_path = java_path
        # Optional integration with the central LocalServerManager so the new
        # server is registered in the launcher's list immediately.
        self.server_mgr = server_mgr
        # If the caller wants the worker to write into a specific folder name
        # (e.g. the "Reinstall" flow on an existing server), pass it here.
        self.custom_folder_name = custom_folder_name
        self.logger = Logger.get_instance()

    def run(self):
        try:
            safe_name = "".join(c for c in self.server_name if c.isalnum() or c in (" ", "_", "-")).strip() or "New_Server"
            servers_dir = get_dot_neurax_dir() / "servers"
            servers_dir.mkdir(parents=True, exist_ok=True)

            if self.custom_folder_name:
                # Reinstall path: keep the same folder name; wipe its contents
                # except for the user's data (world/, plugins/, mods/).
                safe_name = self.custom_folder_name
                s_dir = servers_dir / safe_name
                s_dir.mkdir(parents=True, exist_ok=True)
                for child in s_dir.iterdir():
                    if child.name in ("world", "plugins", "mods", "logs",
                                       "libraries", "config", "crash-reports",
                                       "server.json", "server.properties", "eula.txt"):
                        continue
                    try:
                        if child.is_dir():
                            import shutil as _sh
                            _sh.rmtree(child, ignore_errors=True)
                        else:
                            child.unlink()
                    except Exception:
                        pass
            else:
                base_name = safe_name
                suffix = 2
                s_dir = servers_dir / safe_name
                while s_dir.exists():
                    safe_name = f"{base_name}_{suffix}"
                    s_dir = servers_dir / safe_name
                    suffix += 1
                s_dir.mkdir(parents=True, exist_ok=True)

            self.progress.emit(10, f"Creating local server folder: {safe_name}...")

            download_success = self.install_into_directory(s_dir)

            has_runner = (
                (s_dir / "server.jar").exists()
                or (s_dir / "user_jvm_args.txt").exists()
                or (s_dir / "fabric-server-launch.jar").exists()
                or (s_dir / "libraries").exists()
            )
            if not download_success or not has_runner:
                raise RuntimeError(f"Failed to download or build server binaries for {self.loader} {self.version}")

            self.progress.emit(90, "Saving server configuration...")
            server_meta = {
                "name": self.server_name.strip() or safe_name,
                "folder_name": safe_name,
                "version": self.version,
                "loader": self.loader,
                "max_ram": self.max_ram,
                "port": self.port,
                "java_path": self.java_path,
                "created_at": int(time.time())
            }

            with open(s_dir / "server.json", "w", encoding="utf-8") as f:
                json.dump(server_meta, f, indent=2)

            # Notify the central manager (if provided) so the new server shows
            # up in the launcher's list right away.
            if self.server_mgr is not None and hasattr(self.server_mgr, "register_server"):
                try:
                    self.server_mgr.register_server(server_meta)
                except Exception as e:
                    self.logger.warning(f"server_mgr.register_server failed: {e}")

            self.progress.emit(100, "Local server created successfully!")
            self.finished.emit(True, f"Local server '{self.server_name}' created in .neurax/servers/{safe_name}", safe_name)

        except Exception as e:
            self.logger.error(f"Local Server Creation Error: {e}")
            self.finished.emit(False, str(e), "")

    def install_into_directory(self, s_dir: Path) -> bool:
        try:
            s_dir.mkdir(parents=True, exist_ok=True)
            loader_low = self.loader.lower().strip()

            if loader_low in ("paper", "purpur", "folia", "spigot", "bukkit", "leaf", "pumpkinmc", "pumpkin", "velocity"):
                (s_dir / "plugins").mkdir(exist_ok=True)
            elif loader_low in ("fabric", "quilt", "forge", "neoforge"):
                (s_dir / "mods").mkdir(exist_ok=True)
            (s_dir / "world").mkdir(exist_ok=True)

            eula_path = s_dir / "eula.txt"
            with open(eula_path, "w", encoding="utf-8") as f:
                f.write("eula=true\n")

            props_path = s_dir / "server.properties"
            if not props_path.exists():
                default_props = [
                    f"server-port={self.port}\n",
                    f"motd=NeuraX Local {self.loader} Server ({self.version})\n",
                    "max-players=20\n",
                    "online-mode=false\n",
                    "pvp=true\n",
                    "difficulty=easy\n",
                    "gamemode=survival\n",
                    "enable-command-block=true\n",
                    "spawn-protection=0\n",
                    "view-distance=10\n",
                    "simulation-distance=10\n",
                    "allow-flight=true\n"
                ]
                with open(props_path, "w", encoding="utf-8") as f:
                    f.writelines(default_props)

            jar_path = s_dir / "server.jar"
            download_success = False

            # ---------- Vanilla: use minecraft_launcher_lib ----------
            if loader_low == "vanilla":
                download_success = self._download_vanilla_server(self.version, jar_path)

            # ---------- Paper / Folia / Velocity: new fill.papermc.io v3 API ----------
            elif loader_low in ("paper", "folia", "velocity"):
                download_success = self._download_papermc_v3(self.loader, self.version, jar_path)

            # ---------- Purpur: api.purpurmc.org (unchanged) ----------
            elif loader_low == "purpur":
                download_success = self._download_purpur_server(self.version, jar_path)

            # ---------- Spigot / Bukkit / PumpkinMC: use Paper as a drop-in (CraftBukkit-equivalent) ----------
            elif loader_low in ("spigot", "bukkit", "pumpkinmc", "pumpkin"):
                download_success = self._download_papermc_v3("paper", self.version, jar_path)
                if not download_success:
                    download_success = self._download_vanilla_server(self.version, jar_path)

            # ---------- Leaf: LeavesMC's API ----------
            elif loader_low == "leaf":
                download_success = self._download_leaf_server(self.version, jar_path)

            # ---------- Fabric: meta.fabricmc.net server jar ----------
            elif loader_low == "fabric":
                download_success = self._download_fabric_server(self.version, jar_path)

            # ---------- Quilt: meta.quiltmc.org/v3 server jar ----------
            elif loader_low == "quilt":
                download_success = self._download_quilt_server(self.version, jar_path)

            # ---------- Forge: minecraft_launcher_lib.forge + run installer ----------
            elif loader_low == "forge":
                download_success = self._download_forge_server(self.version, jar_path)

            # ---------- NeoForge: maven.neoforged.net installer ----------
            elif loader_low == "neoforge":
                download_success = self._download_neoforge_server(self.version, jar_path)

            else:
                # Unknown loader: try Paper, then fall back to Vanilla.
                download_success = self._download_papermc_v3("paper", self.version, jar_path)
                if not download_success:
                    download_success = self._download_vanilla_server(self.version, jar_path)

            has_exec = (
                (jar_path.exists() and jar_path.stat().st_size > 0)
                or (s_dir / "user_jvm_args.txt").exists()
                or (s_dir / "fabric-server-launch.jar").exists()
                or (s_dir / "libraries").exists()
            )
            if not download_success and not has_exec:
                download_success = self._download_vanilla_server(self.version, jar_path)

            return (
                (jar_path.exists() and jar_path.stat().st_size > 0)
                or (s_dir / "user_jvm_args.txt").exists()
                or (s_dir / "fabric-server-launch.jar").exists()
                or (s_dir / "libraries").exists()
            )
        except Exception as e:
            self.logger.error(f"Server file installation error: {e}")
            return False

    def _download_vanilla_server(self, version: str, dest_path: Path) -> bool:
        try:
            from neurax.core._streaming_dl import stream_download
            manifest_url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
            self.log_message.emit(f"[Vanilla] Fetching Mojang version manifest...")
            res = requests.get(manifest_url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                v_url = None
                for v in data.get("versions", []):
                    if v.get("id") == version:
                        v_url = v.get("url")
                        break
                if v_url:
                    v_res = requests.get(v_url, timeout=10)
                    if v_res.status_code == 200:
                        v_data = v_res.json()
                        server_info = v_data.get("downloads", {}).get("server", {})
                        server_url = server_info.get("url")
                        if server_url:
                            self.log_message.emit(
                                f"[Vanilla] Streaming server.jar for {version}..."
                            )

                            def _cb(info):
                                phase = info.get("phase")
                                if phase == "start":
                                    self.log_message.emit(
                                        f"[Vanilla] Downloading {dest_path.name}"
                                    )
                                elif phase == "progress" and info.get("bytes_total"):
                                    done_kb = info["bytes_done"] // 1024
                                    total_kb = info["bytes_total"] // 1024
                                    self.log_message.emit(
                                        f"[Vanilla] {dest_path.name} {info['pct']}% ({done_kb}/{total_kb} KB)"
                                    )
                                elif phase == "done":
                                    self.log_message.emit(
                                        f"[Vanilla] {dest_path.name} downloaded ({info['bytes_done'] // 1024} KB)."
                                    )
                                elif phase == "error":
                                    self.log_message.emit(
                                        f"[Vanilla] server.jar download failed: {info.get('error')}"
                                    )

                            return stream_download(
                                server_url, dest_path,
                                progress_cb=_cb, timeout=120.0,
                            )
        except Exception as e:
            self.logger.warning(f"Vanilla server download failed for {version}: {e}")
            try:
                self.log_message.emit(f"[Vanilla] error: {e}")
            except Exception:
                pass
        return False

    def _download_papermc_v3(self, project: str, version: str, dest_path: Path) -> bool:
        """Download Paper / Folia / Velocity via the new fill.papermc.io v3 API.

        The legacy api.papermc.io/v2 endpoints were retired and return HTTP
        410 Gone.  The replacement is the "Fill" API at
        ``https://fill.papermc.io/v3/projects/{project}/versions/{version}/builds``;
        each build object exposes a ``downloads.<key>.url`` field pointing at
        ``https://fill-data.papermc.io/v1/objects/<sha256>/<name>``.  We use
        the ``server:default`` key (the regular server jar).
        """
        project_low = (project or "").lower().strip()
        if project_low not in ("paper", "folia", "velocity"):
            self.logger.warning(f"_download_papermc_v3 called with unknown project {project!r}")
            return False
        try:
            from neurax.core._streaming_dl import stream_download
            url = (
                f"https://fill.papermc.io/v3/projects/{project_low}/versions/{version}/builds"
            )
            self.log_message.emit(f"[PaperMC] Querying {project_low.title()} {version} builds...")
            res = requests.get(
                url, timeout=15, allow_redirects=True,
                headers={"User-Agent": "NeuraX-Launcher/4.0.0"},
            )
            if res.status_code != 200:
                self.logger.warning(
                    f"PaperMC v3 list failed for {project_low} {version}: HTTP {res.status_code}"
                )
                self.log_message.emit(f"[PaperMC] Build list failed: HTTP {res.status_code}")
                return False
            builds = res.json()
            if not builds:
                self.logger.warning(
                    f"PaperMC v3 returned no builds for {project_low} {version}"
                )
                self.log_message.emit(f"[PaperMC] No builds available for {project_low} {version}")
                return False
            # Prefer STABLE builds, then fall back to the newest build overall.
            stable = [b for b in builds if b.get("channel") == "STABLE"]
            chosen = (stable or builds)[-1]
            downloads = chosen.get("downloads") or {}
            server_dl = (
                downloads.get("server:default")
                or downloads.get("server")
                or (downloads.get(next(iter(downloads))) if downloads else None)
            )
            if not server_dl or not server_dl.get("url"):
                self.logger.warning(
                    f"PaperMC v3 build {chosen.get('id')} for {project_low} {version} "
                    "exposes no server download URL"
                )
                self.log_message.emit(f"[PaperMC] No server download URL on build {chosen.get('id')}")
                return False
            dl_url = server_dl["url"]
            self.log_message.emit(
                f"[PaperMC] Streaming {project_low.title()} {version} build "
                f"#{chosen.get('id')}..."
            )

            def _cb(info):
                phase = info.get("phase")
                if phase == "start":
                    self.log_message.emit(f"[PaperMC] Downloading {dest_path.name}")
                elif phase == "progress" and info.get("bytes_total"):
                    done_kb = info["bytes_done"] // 1024
                    total_kb = info["bytes_total"] // 1024
                    self.log_message.emit(
                        f"[PaperMC] {dest_path.name} {info['pct']}% ({done_kb}/{total_kb} KB)"
                    )
                elif phase == "done":
                    self.log_message.emit(
                        f"[PaperMC] {dest_path.name} downloaded ({info['bytes_done'] // 1024} KB)."
                    )
                elif phase == "error":
                    self.log_message.emit(
                        f"[PaperMC] jar download failed: {info.get('error')}"
                    )

            ok = stream_download(
                dl_url, dest_path,
                progress_cb=_cb, timeout=180.0,
                headers={"User-Agent": "NeuraX-Launcher/4.0.0"},
            )
            if ok:
                self.logger.info(
                    f"Downloaded {project_low} {version} build "
                    f"{chosen.get('id')} to {dest_path}"
                )
                return True
            self.logger.warning(
                f"PaperMC v3 jar download failed for {project_low} {version}"
            )
        except Exception as e:
            self.logger.warning(f"PaperMC v3 download error for {project_low} {version}: {e}")
            try:
                self.log_message.emit(f"[PaperMC] error: {e}")
            except Exception:
                pass
        return False

    def _download_paper_server(self, version: str, dest_path: Path) -> bool:
        """Backwards-compatible alias used by older code paths."""
        return self._download_papermc_v3("paper", version, dest_path)

    def _download_folia_server(self, version: str, dest_path: Path) -> bool:
        return self._download_papermc_v3("folia", version, dest_path)

    def _download_leaf_server(self, version: str, dest_path: Path) -> bool:
        """Download a Leaf (PaperMC fork) server jar from ``api.leafmc.one``.

        The legacy ``api.leavesmc.org`` host has been retired.  The new
        endpoint layout is::

            GET /v2/projects/leaf/versions/{ver}            -> list of builds
            GET /v2/projects/leaf/versions/{ver}/builds/{n} -> build metadata
            GET /v2/projects/leaf/versions/{ver}/builds/{n}/downloads/{name}.jar

        We pick the highest build number and download its ``primary`` artifact.
        """
        try:
            from neurax.core._streaming_dl import stream_download
            list_url = (
                f"https://api.leafmc.one/v2/projects/leaf/versions/{version}"
            )
            self.log_message.emit(f"[Leaf] Querying Leaf {version} builds...")
            res = requests.get(
                list_url, timeout=15,
                headers={"User-Agent": "NeuraX-Launcher/4.0.0"},
            )
            if res.status_code == 200:
                data = res.json()
                builds = data.get("builds") or []
                if builds:
                    latest_build = builds[-1]
                    dl_url = (
                        f"https://api.leafmc.one/v2/projects/leaf/versions/{version}"
                        f"/builds/{latest_build}/downloads/leaf-{version}-{latest_build}.jar"
                    )
                    self.log_message.emit(
                        f"[Leaf] Streaming Leaf {version} build {latest_build}..."
                    )

                    def _cb(info):
                        phase = info.get("phase")
                        if phase == "start":
                            self.log_message.emit(f"[Leaf] Downloading {dest_path.name}")
                        elif phase == "progress" and info.get("bytes_total"):
                            done_kb = info["bytes_done"] // 1024
                            total_kb = info["bytes_total"] // 1024
                            self.log_message.emit(
                                f"[Leaf] {dest_path.name} {info['pct']}% ({done_kb}/{total_kb} KB)"
                            )
                        elif phase == "done":
                            self.log_message.emit(
                                f"[Leaf] {dest_path.name} downloaded ({info['bytes_done'] // 1024} KB)."
                            )
                        elif phase == "error":
                            self.log_message.emit(
                                f"[Leaf] download failed: {info.get('error')}"
                            )

                    if stream_download(
                        dl_url, dest_path,
                        progress_cb=_cb, timeout=180.0,
                        headers={"User-Agent": "NeuraX-Launcher/4.0.0"},
                    ):
                        self.logger.info(
                            f"Downloaded Leaf {version} build {latest_build} to {dest_path}"
                        )
                        return True
        except Exception as e:
            self.logger.warning(f"Leaf server download failed for {version}: {e}")
            try:
                self.log_message.emit(f"[Leaf] error: {e}")
            except Exception:
                pass
        # Fallback: Leaf is a PaperMC fork — Paper is a perfectly usable drop-in.
        return self._download_papermc_v3("paper", version, dest_path)

    def _download_purpur_server(self, version: str, dest_path: Path) -> bool:
        try:
            from neurax.core._streaming_dl import stream_download
            dl_url = f"https://api.purpurmc.org/v2/purpur/{version}/latest/download"
            self.log_message.emit(f"[Purpur] Streaming Purpur {version} server.jar...")

            def _cb(info):
                phase = info.get("phase")
                if phase == "start":
                    self.log_message.emit(f"[Purpur] Downloading {dest_path.name}")
                elif phase == "progress" and info.get("bytes_total"):
                    done_kb = info["bytes_done"] // 1024
                    total_kb = info["bytes_total"] // 1024
                    self.log_message.emit(
                        f"[Purpur] {dest_path.name} {info['pct']}% ({done_kb}/{total_kb} KB)"
                    )
                elif phase == "done":
                    self.log_message.emit(
                        f"[Purpur] {dest_path.name} downloaded ({info['bytes_done'] // 1024} KB)."
                    )
                elif phase == "error":
                    self.log_message.emit(
                        f"[Purpur] download failed: {info.get('error')}"
                    )

            return stream_download(dl_url, dest_path, progress_cb=_cb, timeout=120.0)
        except Exception as e:
            self.logger.warning(f"Purpur server download failed for {version}: {e}")
            try:
                self.log_message.emit(f"[Purpur] error: {e}")
            except Exception:
                pass
        return False

    def _download_fabric_server(self, version: str, dest_path: Path) -> bool:
        """Download a Fabric server jar.

        Note: ``minecraft_launcher_lib.fabric.install_fabric`` is a CLIENT
        installer (it downloads the full vanilla client pipeline: assets,
        libraries, natives) and is unsuitable for a server folder.  We
        instead go directly to Fabric's own meta API:
        ``meta.fabricmc.net/v2/versions/loader/{ver}/{loader}/{installer}/server/jar``.
        """
        s_dir = dest_path.parent
        try:
            (s_dir / "mods").mkdir(exist_ok=True)
            self._download_vanilla_server(version, s_dir / "vanilla.jar")
            loader_ver = "0.16.10"
            installer_ver = "1.0.1"
            try:
                inst_res = requests.get(
                    "https://meta.fabricmc.net/v2/versions/installer", timeout=10
                )
                if inst_res.status_code == 200:
                    inst_data = inst_res.json()
                    if isinstance(inst_data, list) and inst_data:
                        v = inst_data[0].get("version")
                        if v:
                            installer_ver = str(v)
            except Exception:
                pass
            meta_url = f"https://meta.fabricmc.net/v2/versions/loader/{version}"
            try:
                res = requests.get(meta_url, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, list) and data:
                        first = data[0]
                        l_ver = first.get("loader", {}).get("version")
                        if l_ver:
                            loader_ver = str(l_ver)
            except Exception:
                pass
            dl_url = (
                f"https://meta.fabricmc.net/v2/versions/loader/{version}/"
                f"{loader_ver}/{installer_ver}/server/jar"
            )
            self.log_message.emit(
                f"[Fabric] Streaming Fabric server jar (loader {loader_ver}, installer {installer_ver})..."
            )

            def _cb(info):
                phase = info.get("phase")
                if phase == "start":
                    self.log_message.emit(f"[Fabric] Downloading {dest_path.name}")
                elif phase == "progress" and info.get("bytes_total"):
                    done_kb = info["bytes_done"] // 1024
                    total_kb = info["bytes_total"] // 1024
                    self.log_message.emit(
                        f"[Fabric] {dest_path.name} {info['pct']}% ({done_kb}/{total_kb} KB)"
                    )
                elif phase == "done":
                    self.log_message.emit(
                        f"[Fabric] {dest_path.name} downloaded ({info['bytes_done'] // 1024} KB)."
                    )
                elif phase == "error":
                    self.log_message.emit(
                        f"[Fabric] download failed: {info.get('error')}"
                    )

            if stream_download(
                dl_url, dest_path,
                progress_cb=_cb, timeout=180.0,
            ):
                for prop in (
                    "fabric-server-launch.properties",
                    "fabric-server-launcher.properties",
                ):
                    with open(s_dir / prop, "w", encoding="utf-8") as f:
                        f.write("serverJar=vanilla.jar\n")
                self.logger.info(
                    f"Downloaded Fabric server {version} (loader {loader_ver}, "
                    f"installer {installer_ver}) to {dest_path}"
                )
                return True
            self.logger.warning(
                f"Fabric server download failed for {version}"
            )
        except Exception as e:
            self.logger.warning(f"Fabric server download failed for {version}: {e}")
            try:
                self.log_message.emit(f"[Fabric] error: {e}")
            except Exception:
                pass
        # Last-ditch fallback: a plain Vanilla server (mods/ folder still
        # exists so users can still drop Fabric/Quilt mods in — but the jar
        # itself is Vanilla).
        if self._download_vanilla_server(version, dest_path):
            return True
        return dest_path.exists() and dest_path.stat().st_size > 0

    def _download_quilt_server(self, version: str, dest_path: Path) -> bool:
        """Download a Quilt server jar.

        Quilt does not expose a direct ``/server/jar`` endpoint.  Instead:

        1. Resolve the latest Quilt loader version for this Minecraft.
        2. Hit ``meta.quiltmc.org/v3/versions/loader/<mc>/<loader>`` to get
           the canonical ``launcherMeta.libraries.common[]`` list.
        3. **Also** add ``loader.maven`` (e.g. ``org.quiltmc:quilt-loader:<ver>``)
           to the download list — the Meta API does NOT list this in
           ``common[]``, but the Quilt ServerLauncher's Main-Class
           (``org.quiltmc.loader.impl.launch.server.QuiltServerLauncher``)
           lives inside ``quilt-loader.jar`` and must be on the classpath.
        4. Synthesize a tiny ``quilt-server-launch.jar`` whose
           ``MANIFEST.MF`` declares
           ``Main-Class: org.quiltmc.loader.impl.launch.server.QuiltServerLauncher``
           and a ``Class-Path:`` listing every common library jar (plus
           ``quilt-loader.jar``) at the Quilt-expected
           ``libraries/<group>/<artifact>/<ver>/...`` paths.
        5. Download each library jar to its expected ``libraries/...`` path.
        6. Place a vanilla ``vanilla.jar`` next to it (Quilt wraps vanilla);
           the launcher reads ``quilt-server-launch.properties`` for
           ``serverJar=vanilla.jar`` to find it.
        """
        s_dir = dest_path.parent
        try:
            (s_dir / "mods").mkdir(exist_ok=True)
            (s_dir / "libraries").mkdir(exist_ok=True)

            loader_ver = "0.20.0"
            try:
                lr = requests.get(
                    f"https://meta.quiltmc.org/v3/versions/loader/{version}",
                    timeout=15,
                    headers={"User-Agent": "NeuraX-Launcher/4.0.0"},
                )
                if lr.status_code == 200:
                    data = lr.json()
                    if isinstance(data, list) and data:
                        l = data[0].get("loader", {}).get("version")
                        if l:
                            loader_ver = str(l)
            except Exception:
                pass

            launcher_libs = []
            loader_maven_coords = None
            try:
                lmeta = requests.get(
                    f"https://meta.quiltmc.org/v3/versions/loader/{version}/{loader_ver}",
                    timeout=20,
                    headers={"User-Agent": "NeuraX-Launcher/4.0.0"},
                )
                if lmeta.status_code == 200:
                    lmeta_j = lmeta.json()
                    launcher_libs = (
                        (lmeta_j.get("launcherMeta") or {})
                        .get("libraries", {})
                        .get("common", []) or []
                    )
                    # The Meta API does NOT include the loader itself in
                    # ``common[]``.  The Main-Class implementation lives in
                    # ``quilt-loader.jar`` and must be on the classpath, so
                    # we synthesize an entry for it using the
                    # ``loader.maven`` coordinates (e.g.
                    # ``org.quiltmc:quilt-loader:0.20.0-beta.9``) and the
                    # Quilt Maven release URL.
                    loader_maven = (
                        (lmeta_j.get("loader") or {}).get("maven")
                    )
                    if loader_maven:
                        loader_maven_coords = {
                            "name": loader_maven,
                            "url": "https://maven.quiltmc.org/repository/release/"
                        }
            except Exception:
                pass

            if not launcher_libs and not loader_maven_coords:
                self.logger.warning(
                    f"Quilt launcher meta returned no common libraries for "
                    f"{version}/{loader_ver}"
                )
                if self._download_vanilla_server(version, dest_path):
                    return True
                return False

            # Prepend the loader itself so the Main-Class
            # (``org.quiltmc.loader.impl.launch.server.QuiltServerLauncher``,
            # which lives in quilt-loader.jar) is on the classpath.
            if loader_maven_coords:
                launcher_libs = [loader_maven_coords] + launcher_libs

            # ---- Step 3: build the launcher stub ----
            class_path_lines = []
            jar_paths = []  # (group:artifact:version, rel_path, jar_url)
            for entry in launcher_libs:
                name = entry.get("name")
                base_url = entry.get("url")
                if not name or not base_url:
                    continue
                try:
                    grp, art, ver = name.split(":")
                except ValueError:
                    continue
                grp_path = grp.replace(".", "/")
                rel = f"libraries/{grp_path}/{art}/{ver}/{art}-{ver}.jar"
                class_path_lines.append(rel)
                jar_url = (
                    f"{base_url.rstrip('/')}/{grp_path}/{art}/{ver}/"
                    f"{art}-{ver}.jar"
                )
                jar_paths.append((name, rel, jar_url))

            manifest_body = (
                "Manifest-Version: 1.0\r\n"
                "Main-Class: org.quiltmc.loader.impl.launch.server.QuiltServerLauncher\r\n"
                "Class-Path: " + " ".join(class_path_lines) + "\r\n"
            )

            import zipfile as _zip
            launcher_jar = s_dir / "quilt-server-launch.jar"
            with _zip.ZipFile(
                launcher_jar, "w", _zip.ZIP_STORED, allowZip64=False
            ) as z:
                zi = _zip.ZipInfo("META-INF/MANIFEST.MF")
                zi.compress_type = _zip.ZIP_STORED
                z.writestr(zi, manifest_body)

            # ---- Step 4: download every common library jar ----
            failed = []
            total_libs = len(jar_paths)
            self.log_message.emit(
                f"[Quilt] Downloading {total_libs} launcher libraries..."
            )
            for idx, (name, rel, jar_url) in enumerate(jar_paths, 1):
                dest = s_dir / rel
                if dest.exists() and dest.stat().st_size > 0:
                    self.log_message.emit(
                        f"[Quilt] Library {idx}/{total_libs}: {Path(rel).name} (cached, skipping)"
                    )
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                self.log_message.emit(
                    f"[Quilt] Library {idx}/{total_libs}: {Path(rel).name} ({name})"
                )

                def _cb(info, _name=name, _rel=rel, _idx=idx):
                    phase = info.get("phase")
                    if phase == "done":
                        self.log_message.emit(
                            f"[Quilt]   ({_idx}/{total_libs}) {_name} downloaded "
                            f"({info['bytes_done'] // 1024} KB)."
                        )
                    elif phase == "error":
                        self.log_message.emit(
                            f"[Quilt]   ({_idx}/{total_libs}) {_name} failed: "
                            f"{info.get('error')}"
                        )

                try:
                    ok = stream_download(
                        jar_url, dest,
                        progress_cb=_cb, timeout=120.0,
                        headers={"User-Agent": "NeuraX-Launcher/4.0.0"},
                    )
                    if not ok:
                        failed.append(f"{name} download failed")
                except Exception as e:
                    failed.append(f"{name} ({e})")
                    try:
                        self.log_message.emit(f"[Quilt]   ({idx}/{total_libs}) {name} error: {e}")
                    except Exception:
                        pass

            if failed:
                self.logger.warning(
                    f"Quilt: {len(failed)} libraries failed: {failed[:5]}"
                )

            # ---- Step 5: Place vanilla jar (the actual server Mojang ships) ----
            # The Quilt launcher stub above points its Main-Class at
            # ``org.quiltmc.loader.impl.launch.server.QuiltServerLauncher``,
            # which is loaded via Class-Path from ``libraries/.../quilt-loader.jar``.
            # That launcher reads ``quilt-server-launch.properties`` to find the
            # real Minecraft jar to run.  We therefore download vanilla to
            # ``vanilla.jar`` (matching what the LocalServerStartWorker writes
            # into ``quilt-server-launch.properties``: ``serverJar=vanilla.jar``)
            # and place the launcher stub at the conventional Quilt name
            # ``quilt-server-launch.jar``.  We *never* overwrite
            # ``<s_dir>/server.jar`` with the stub — the stub only contains
            # MANIFEST.MF and the launcher would fail with ClassNotFoundException
            # trying to read it as the Minecraft jar.
            vanilla_ok = self._download_vanilla_server(version, s_dir / "vanilla.jar")
            if not vanilla_ok:
                self.logger.warning(
                    f"Quilt: vanilla.jar download failed for {version}; "
                    "Quilt server will be incomplete."
                )

            # `dest_path` was passed in as ``<s_dir>/server.jar`` by the
            # dispatcher, but for Quilt the launcher lives at
            # ``quilt-server-launch.jar``.  We don't write to ``dest_path``
            # here — the start logic in LocalServerStartWorker detects Quilt
            # via the ``quilt-server-launch.jar`` artifact and launches that
            # instead of ``server.jar``.  The stub is already written above
            # at ``launcher_jar`` (= ``s_dir/quilt-server-launch.jar``).
            for prop in (
                "quilt-server-launch.properties",
                "quilt-server-launcher.properties",
                "fabric-server-launch.properties",
            ):
                with open(s_dir / prop, "w", encoding="utf-8") as f:
                    f.write("serverJar=vanilla.jar\n")
            self.logger.info(
                f"Quilt server {version} (loader {loader_ver}) installed with "
                f"{len(launcher_libs)} libs ({len(failed)} failed, "
                f"vanilla_ok={vanilla_ok})"
            )
            return (
                launcher_jar.exists() and launcher_jar.stat().st_size > 0
                and (s_dir / "libraries").exists()
                and vanilla_ok
            )
        except Exception as e:
            self.logger.warning(f"Quilt server download failed for {version}: {e}")
        if self._download_vanilla_server(version, dest_path):
            return True
        return dest_path.exists() and dest_path.stat().st_size > 0

    def _download_forge_server(self, version: str, dest_path: Path) -> bool:
        """Download a Forge server and run its installer (``--installServer``).

        Forge has migrated its artifact hosting to ``maven.minecraftforge.net``
        (the old ``files.minecraftforge.net/maven`` paths are redirected, but
        we hit Maven directly to avoid one round-trip).  The version string
        we want is ``<mc>-<forge>`` (e.g. ``1.21.4-54.1.6``); we resolve it
        via the launcher helper and, if that picks a string whose artifact
        is missing (mismatch between resolver and real Maven listing), we
        fall back to walking the Forge Maven metadata for the first
        existing build.
        """
        s_dir = dest_path.parent
        try:
            (s_dir / "mods").mkdir(exist_ok=True)
            self._download_vanilla_server(version, s_dir / "vanilla.jar")

            from neurax.core.launcher import resolve_forge_version
            forge_ver = resolve_forge_version(version)

            def _try_installer(fv: str) -> bool:
                url = (
                    f"https://maven.minecraftforge.net/net/minecraftforge/forge/"
                    f"{fv}/forge-{fv}-installer.jar"
                )
                try:
                    head = requests.head(url, timeout=10, allow_redirects=True)
                except Exception:
                    head = None
                if not head or head.status_code != 200:
                    return False
                self.log_message.emit(
                    f"[Forge] Streaming Forge {fv} installer jar..."
                )
                installer_jar = s_dir / "forge-installer.jar"

                def _cb(info):
                    phase = info.get("phase")
                    if phase == "start":
                        self.log_message.emit(
                            f"[Forge] Downloading forge-installer.jar"
                        )
                    elif phase == "progress" and info.get("bytes_total"):
                        done_kb = info["bytes_done"] // 1024
                        total_kb = info["bytes_total"] // 1024
                        self.log_message.emit(
                            f"[Forge] forge-installer.jar {info['pct']}% "
                            f"({done_kb}/{total_kb} KB)"
                        )
                    elif phase == "done":
                        self.log_message.emit(
                            f"[Forge] forge-installer.jar downloaded "
                            f"({info['bytes_done'] // 1024} KB)."
                        )
                    elif phase == "error":
                        self.log_message.emit(
                            f"[Forge] installer download failed: {info.get('error')}"
                        )

                if not stream_download(
                    url, installer_jar,
                    progress_cb=_cb, timeout=180.0,
                ):
                    return False
                req_major = get_required_java_major(version)
                which_j = None
                cands = []
                if self.java_path and self.java_path != "auto" and os.path.isfile(self.java_path):
                    cands.append(self.java_path)
                sys_j = shutil.which("java") or shutil.which("java.exe")
                if sys_j and os.path.isfile(sys_j):
                    cands.append(sys_j)
                for _n, jp in JavaFinder.find_java_installations():
                    if jp and os.path.isfile(jp):
                        cands.append(jp)
                for c_path in cands:
                    if JavaFinder.get_java_major_version(c_path) == req_major:
                        which_j = c_path
                        break
                if not which_j and cands:
                    which_j = cands[0]
                if which_j and os.path.isfile(which_j):
                    cmd = [which_j, "-jar", str(installer_jar), "--installServer"]
                    try:
                        # Forge/NeoForge installers prompt for Y/N when
                        # asked to download additional libraries from the
                        # local .m2 cache; feed "yes" to keep them moving.
                        run_silent(
                            cmd,
                            cwd=str(s_dir),
                            timeout=900,
                            input=b"yes\nyes\nyes\n",
                        )
                    except Exception as e:
                        self.logger.warning(f"Forge installer run failed: {e}")
                try:
                    installer_jar.unlink()
                except Exception:
                    pass
                return True

            installed = False
            if forge_ver:
                installed = _try_installer(forge_ver)
                if not installed:
                    # Walk the Maven metadata for the first existing match.
                    try:
                        meta = requests.get(
                            "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
                            timeout=15,
                        )
                        if meta.status_code == 200:
                            import re as _re
                            versions = _re.findall(r"<version>([^<]+)</version>", meta.text)
                            for v in reversed(versions):
                                if version in v:
                                    if _try_installer(v):
                                        installed = True
                                        break
                    except Exception:
                        pass

            for item in s_dir.glob("forge-*.jar"):
                if "installer" not in item.name.lower() and item != dest_path:
                    shutil.copy2(item, dest_path)
                    break

            ok = (
                (dest_path.exists() and dest_path.stat().st_size > 0)
                or (s_dir / "user_jvm_args.txt").exists()
            )
            if ok:
                return True
        except Exception as e:
            self.logger.warning(f"Forge server download notice for {version}: {e}")

        # Last-ditch fallback: a plain Vanilla server (mods/ folder is still
        # created so users can drop Forge mods in, but the jar itself runs as
        # Vanilla).
        if self._download_vanilla_server(version, dest_path):
            return True
        return dest_path.exists() and dest_path.stat().st_size > 0

    def _download_neoforge_server(self, version: str, dest_path: Path) -> bool:
        """Download a NeoForge server and run its installer.

        NeoForge is hosted only on ``maven.neoforged.net/releases/...`` (the
        old DNS-based ``api.neoforged.net`` host is no longer reachable).
        We resolve the latest version via the launcher helper and, if the
        resulting artifact is missing (resolver/repo drift), fall back to
        walking the Maven metadata for the first existing build.
        """
        s_dir = dest_path.parent
        try:
            (s_dir / "mods").mkdir(exist_ok=True)
            self._download_vanilla_server(version, s_dir / "vanilla.jar")

            from neurax.core.launcher import resolve_neoforge_version
            nf_ver = resolve_neoforge_version(version)

            def _try_installer(nfv: str) -> bool:
                url = (
                    f"https://maven.neoforged.net/releases/net/neoforged/neoforge/"
                    f"{nfv}/neoforge-{nfv}-installer.jar"
                )
                try:
                    head = requests.head(url, timeout=10, allow_redirects=True)
                except Exception:
                    head = None
                if not head or head.status_code != 200:
                    return False
                self.log_message.emit(
                    f"[NeoForge] Streaming NeoForge {nfv} installer jar..."
                )
                installer_jar = s_dir / "neoforge-installer.jar"

                def _cb(info):
                    phase = info.get("phase")
                    if phase == "start":
                        self.log_message.emit(
                            f"[NeoForge] Downloading neoforge-installer.jar"
                        )
                    elif phase == "progress" and info.get("bytes_total"):
                        done_kb = info["bytes_done"] // 1024
                        total_kb = info["bytes_total"] // 1024
                        self.log_message.emit(
                            f"[NeoForge] neoforge-installer.jar {info['pct']}% "
                            f"({done_kb}/{total_kb} KB)"
                        )
                    elif phase == "done":
                        self.log_message.emit(
                            f"[NeoForge] neoforge-installer.jar downloaded "
                            f"({info['bytes_done'] // 1024} KB)."
                        )
                    elif phase == "error":
                        self.log_message.emit(
                            f"[NeoForge] installer download failed: {info.get('error')}"
                        )

                if not stream_download(
                    url, installer_jar,
                    progress_cb=_cb, timeout=180.0,
                ):
                    return False
                req_major = get_required_java_major(version)
                which_j = None
                cands = []
                if self.java_path and self.java_path != "auto" and os.path.isfile(self.java_path):
                    cands.append(self.java_path)
                sys_j = shutil.which("java") or shutil.which("java.exe")
                if sys_j and os.path.isfile(sys_j):
                    cands.append(sys_j)
                for _n, jp in JavaFinder.find_java_installations():
                    if jp and os.path.isfile(jp):
                        cands.append(jp)
                for c_path in cands:
                    if JavaFinder.get_java_major_version(c_path) == req_major:
                        which_j = c_path
                        break
                if not which_j and cands:
                    which_j = cands[0]
                if which_j and os.path.isfile(which_j):
                    cmd = [which_j, "-jar", str(installer_jar), "--installServer"]
                    try:
                        run_silent(
                            cmd,
                            cwd=str(s_dir),
                            timeout=900,
                            input=b"yes\nyes\nyes\n",
                        )
                    except Exception as e:
                        self.logger.warning(f"NeoForge installer run failed: {e}")
                try:
                    installer_jar.unlink()
                except Exception:
                    pass
                return True

            installed = False
            if nf_ver:
                installed = _try_installer(nf_ver)
                if not installed:
                    try:
                        meta = requests.get(
                            "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml",
                            timeout=15,
                        )
                        if meta.status_code == 200:
                            import re as _re
                            versions = _re.findall(r"<version>([^<]+)</version>", meta.text)
                            # For MC 1.x → NeoForge uses <minor>.<patch>.x.x;
                            # for MC >= 20.x → <major>.<minor>.<patch>.x.
                            parts = [int(p) for p in re.findall(r"\d+", version)]
                            pref = ""
                            if len(parts) >= 2:
                                if parts[0] == 1:
                                    pref = f"{parts[1]}.{parts[2] if len(parts) > 2 else 0}."
                                else:
                                    pref = f"{parts[0]}.{parts[1]}.{parts[2] if len(parts) > 2 else 0}."
                            cand = [
                                v for v in versions
                                if (pref and v.startswith(pref))
                                or (version in v)
                            ]
                            cand.sort(key=lambda s: [int(n) for n in re.findall(r"\d+", s)], reverse=True)
                            for v in cand:
                                if _try_installer(v):
                                    installed = True
                                    break
                    except Exception:
                        pass

            for item in s_dir.glob("neoforge-*.jar"):
                if "installer" not in item.name.lower() and item != dest_path:
                    shutil.copy2(item, dest_path)
                    break

            ok = (
                (dest_path.exists() and dest_path.stat().st_size > 0)
                or (s_dir / "user_jvm_args.txt").exists()
            )
            if ok:
                return True
        except Exception as e:
            self.logger.warning(f"NeoForge server download notice for {version}: {e}")

        if self._download_vanilla_server(version, dest_path):
            return True
        return dest_path.exists() and dest_path.stat().st_size > 0

class LocalServerStartWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str, list, str)
    # Per-line log — also forwards to the in-launcher server console.
    log_message = pyqtSignal(str)

    def __init__(self, server_folder: str, max_ram: int, java_path: str):
        super().__init__()
        self.server_folder = server_folder
        self.server_dir = get_dot_neurax_dir() / "servers" / server_folder
        self.max_ram = max_ram
        self.java_path = java_path
        self.logger = Logger.get_instance()

    def run(self):
        try:
            self.progress.emit("[LocalServer] Preparing local server startup...")
            if not self.server_dir.exists():
                raise RuntimeError(f"Server directory does not exist: {self.server_dir}")

            kill_server_process_by_folder(self.server_dir)
            time.sleep(0.3)

            cfg_path = self.server_dir / "server.json"
            loader = "Vanilla"
            version = "1.20.4"
            port = 25565
            if cfg_path.exists():
                try:
                    # Use ``utf-8-sig`` so a leading BOM (sometimes added by
                    # PowerShell ``Set-Content -Encoding UTF8`` or other
                    # Windows tools) doesn't break ``json.load`` and silently
                    # fall back to the default ``version=1.20.4``.
                    with open(cfg_path, "r", encoding="utf-8-sig") as f:
                        cfg = json.load(f)
                        loader = cfg.get("loader", "Vanilla")
                        version = cfg.get("version", "1.20.4")
                        port = cfg.get("port", 25565)
                except Exception:
                    pass

            eula_file = self.server_dir / "eula.txt"
            with open(eula_file, "w", encoding="utf-8") as f:
                f.write("eula=true\n")

            jar_file = self.server_dir / "server.jar"
            user_args_file = self.server_dir / "user_jvm_args.txt"
            has_valid_exec = (jar_file.exists() and jar_file.stat().st_size > 0) or user_args_file.exists()

            if has_valid_exec and jar_file.exists() and not user_args_file.exists():
                if not _is_valid_loader_jar(jar_file, loader):
                    has_valid_exec = False

            if not has_valid_exec:
                self.progress.emit("[LocalServer] Server binaries missing, corrupted, or incorrect loader. Downloading & installing...")
                creator = CreateServerWorker(
                    name=self.server_folder,
                    version=version,
                    loader=loader,
                    max_ram=self.max_ram,
                    port=port,
                    java_path=self.java_path
                )
                ok = creator.install_into_directory(self.server_dir)
                if not ok:
                    raise RuntimeError("Failed to install server binaries and libraries.")
                self.progress.emit("[LocalServer] Server files installed successfully.")

            # ---------------------------------------------------------------
            # Auto-upgrade loader version on every start.
            # ---------------------------------------------------------------
            # If the server's currently-installed loader is older than the
            # upstream latest stable build for the same MC version, replace
            # it in place before launching the JVM. This keeps local servers
            # on the newest Fabric/Quilt/Forge/NeoForge builds without any
            # manual user intervention — the same behaviour a real launcher
            # has. We only auto-upgrade when the user hasn't explicitly
            # pinned a specific build in the server's saved metadata.
            #
            # To avoid hammering upstream APIs on every launch we cache
            # ``installed_loader_version`` alongside ``cfg_path``: a fresh
            # metadata file is written whenever we successfully upgrade,
            # so subsequent launches can short-circuit.
            loader_low = loader.lower().strip()
            if loader_low in ("fabric", "quilt", "forge", "neoforge"):
                try:
                    from neurax.core import loader_versions
                    upstream_latest = loader_versions.fetch_latest_loader_version(
                        loader_low, version
                    )
                    if upstream_latest:
                        # Determine installed version by inspecting the
                        # jar filename or server metadata.
                        installed_str = ""
                        jar_name = jar_file.name if jar_file.exists() else ""
                        # For Fabric: server jar filename embeds the loader
                        # version when served from meta (e.g.
                        # ``fabric-server-launch-1.21.11-0.19.5.jar``),
                        # but we use a more reliable path: the
                        # ``fabric-server-launch.properties`` file points
                        # at ``serverJar=vanilla.jar``, and the bundled
                        # ``fabric-server-launch.jar`` (and libraries) are
                        # downloaded alongside. We can't trivially read
                        # the embedded loader version, so for Fabric /
                        # Quilt we treat any non-empty jar as "installed"
                        # and only re-download when the upstream version
                        # has changed since the last recorded run.
                        meta_path = self.server_dir / "server_launcher.json"
                        recorded = ""
                        if meta_path.exists():
                            try:
                                with open(meta_path, "r", encoding="utf-8-sig") as f:
                                    recorded = (json.load(f) or {}).get("installed_loader_version", "") or ""
                            except Exception:
                                recorded = ""
                        if not recorded or loader_versions.is_version_outdated(
                            recorded, upstream_latest
                        ):
                            self.progress.emit(
                                f"[LocalServer] {loader} loader is out of date "
                                f"(installed: {recorded or 'unknown'}, latest: {upstream_latest}). "
                                f"Auto-upgrading…"
                            )
                            self.log_message.emit(
                                f"[{loader}] Auto-upgrade: installed {recorded or 'unknown'} "
                                f"-> latest {upstream_latest} for Minecraft {version}"
                            )
                            creator = CreateServerWorker(
                                name=self.server_folder,
                                version=version,
                                loader=loader,
                                max_ram=self.max_ram,
                                port=port,
                                java_path=self.java_path,
                            )
                            ok = creator.install_into_directory(self.server_dir)
                            if ok:
                                try:
                                    meta = {}
                                    if meta_path.exists():
                                        with open(meta_path, "r", encoding="utf-8-sig") as f:
                                            meta = json.load(f) or {}
                                    meta["installed_loader_version"] = upstream_latest
                                    meta["loader"] = loader_low
                                    meta["version"] = version
                                    with open(meta_path, "w", encoding="utf-8") as f:
                                        json.dump(meta, f, indent=2)
                                except Exception as ex:
                                    self.logger.warning(
                                        f"Failed to persist server_launcher.json: {ex}"
                                    )
                except Exception as ex:
                    self.logger.warning(f"Local server loader auto-upgrade check failed: {ex}")

            loader_low = loader.lower().strip()
            if loader_low in ("fabric", "quilt"):
                vanilla_jar = self.server_dir / "vanilla.jar"
                if not vanilla_jar.exists() or vanilla_jar.stat().st_size == 0:
                    self.progress.emit(f"[LocalServer] {loader} loader detected: Downloading vanilla.jar dependency...")
                    creator = CreateServerWorker(self.server_folder, version, "vanilla", 1024)
                    creator._download_vanilla_server(version, vanilla_jar)

                p1 = self.server_dir / "fabric-server-launch.properties"
                with open(p1, "w", encoding="utf-8") as f:
                    f.write("serverJar=vanilla.jar\n")
                p2 = self.server_dir / "fabric-server-launcher.properties"
                with open(p2, "w", encoding="utf-8") as f:
                    f.write("serverJar=vanilla.jar\n")

                if loader_low == "quilt":
                    qp1 = self.server_dir / "quilt-server-launch.properties"
                    with open(qp1, "w", encoding="utf-8") as f:
                        f.write("serverJar=vanilla.jar\n")
                    qp2 = self.server_dir / "quilt-server-launcher.properties"
                    with open(qp2, "w", encoding="utf-8") as f:
                        f.write("serverJar=vanilla.jar\n")

                (self.server_dir / "mods").mkdir(exist_ok=True)
            elif loader_low in ("paper", "purpur", "folia", "spigot", "bukkit", "leaf", "pumpkinmc", "pumpkin"):
                (self.server_dir / "plugins").mkdir(exist_ok=True)
            elif loader_low in ("forge", "neoforge"):
                (self.server_dir / "mods").mkdir(exist_ok=True)

            self.progress.emit("[LocalServer] Resolving Java runtime environment...")
            req_major = get_required_java_major(version)

            # NeuraX standardises on JDK 25 (LTS) for everything — play,
            # local server, modded, vanilla. Older majors (8/11/17/21)
            # are accepted as a polite fallback if the user genuinely
            # has no JDK 25 installed, but the launcher will nag about
            # it. New majors (26+) are ignored so we never silently
            # launch a server on the wrong major.
            PREFERENCE = (25, 21, 17, 8)

            candidates: list[tuple[str, int]] = []
            seen_cands: set[str] = set()

            def add_candidate(p):
                if not p or not os.path.isfile(p):
                    return None
                norm = os.path.normpath(p)
                if norm in seen_cands:
                    return None
                seen_cands.add(norm)
                try:
                    major = JavaFinder.get_java_major_version(p)
                except Exception:
                    return None
                if major not in PREFERENCE:
                    return None
                candidates.append((p, major))
                return (p, major)

            if self.java_path and self.java_path != "auto":
                add_candidate(self.java_path)

            jh = os.environ.get("JAVA_HOME")
            if jh:
                jh_bin = os.path.join(jh, "bin", "java.exe" if sys.platform == "win32" else "java")
                add_candidate(jh_bin)

            sys_j = shutil.which("java") or shutil.which("java.exe")
            if sys_j:
                add_candidate(sys_j)

            for _name, jpath in JavaFinder.find_java_installations():
                add_candidate(jpath)

            java_exec = None
            for want in PREFERENCE:
                for c_path, major in candidates:
                    if major == want:
                        java_exec = c_path
                        break
                if java_exec:
                    break

            if not java_exec or not os.path.isfile(java_exec):
                found = ", ".join(
                    f"JDK {m} ({os.path.basename(p)})" for p, m in candidates
                ) or "none"
                err_msg = (
                    f"JDK 25 (Java 25) is required to run a local Minecraft {version} server on NeuraX. "
                    f"It was not found on your PC. Please install JDK 25 (Java 25) and make sure it's on PATH "
                    f"or set the JAVA_HOME environment variable. "
                    f"Detected Java installations: {found}."
                )
                self.progress.emit(f"[LocalServer ERROR] {err_msg}")
                self.logger.error(err_msg)
                raise RuntimeError(err_msg)

            extra_args_file = None
            if user_args_file.exists():
                args_filename = "win_args.txt" if sys.platform == "win32" else "unix_args.txt"
                libraries_dir = self.server_dir / "libraries"
                if libraries_dir.exists():
                    for root, _, files in os.walk(libraries_dir):
                        if args_filename in files:
                            extra_args_file = Path(root) / args_filename
                            break
                        elif "args.txt" in files and not extra_args_file:
                            extra_args_file = Path(root) / "args.txt"

            if user_args_file.exists() and extra_args_file:
                rel_extra = extra_args_file.relative_to(self.server_dir)
                cmd = [
                    java_exec,
                    f"-Xmx{self.max_ram}M",
                    f"-Xms{min(1024, self.max_ram)}M",
                    "@user_jvm_args.txt",
                    f"@{rel_extra}",
                    "nogui"
                ]
            else:
                # Loader-aware launch command.
                #
                # Vanilla / Paper / Purpur / Folia / Velocity / Spigot /
                # Bukkit / Leaf / PumpkinMC: the executable IS
                # ``server.jar`` — ``java -jar server.jar nogui`` works.
                #
                # Forge / NeoForge: handled above via ``user_jvm_args.txt``
                # + ``win_args.txt``.
                #
                # Quilt is special.  Quilt's launcher is a *stub* jar
                # (only ``META-INF/MANIFEST.MF``) that points its
                # ``Main-Class`` at ``org.quiltmc.loader.impl.launch.server
                # .QuiltServerLauncher``, which lives inside
                # ``quilt-loader.jar`` and is loaded via the manifest's
                # ``Class-Path:``.  ``java -jar`` cannot reliably find that
                # Main-Class on Java 21+ (fails with ``Error: An unexpected
                # error occurred while trying to open file …``), so we
                # build the classpath explicitly from every jar under
                # ``libraries/`` plus the stub, and pass the Main-Class
                # directly on the command line.
                if loader_low == "quilt":
                    quilt_launcher = self.server_dir / "quilt-server-launch.jar"
                    if quilt_launcher.exists() and quilt_launcher.stat().st_size > 0:
                        cp_parts = []
                        libs_dir = self.server_dir / "libraries"
                        if libs_dir.exists():
                            for jar_path in libs_dir.rglob("*.jar"):
                                cp_parts.append(str(jar_path.relative_to(self.server_dir)))
                        cp_parts.append("quilt-server-launch.jar")
                        cp_sep = ";" if sys.platform == "win32" else ":"
                        cp_value = cp_sep.join(cp_parts)
                        cmd = [
                            java_exec,
                            f"-Xmx{self.max_ram}M",
                            f"-Xms{min(1024, self.max_ram)}M",
                            "-cp",
                            cp_value,
                            "org.quiltmc.loader.impl.launch.server.QuiltServerLauncher",
                            "nogui",
                        ]
                    else:
                        # Fall back: no stub landed, just try server.jar.
                        cmd = [
                            java_exec,
                            f"-Xmx{self.max_ram}M",
                            f"-Xms{min(1024, self.max_ram)}M",
                            "-jar",
                            "server.jar",
                            "nogui",
                        ]
                else:
                    cmd = [
                        java_exec,
                        f"-Xmx{self.max_ram}M",
                        f"-Xms{min(1024, self.max_ram)}M",
                        "-jar",
                        "server.jar",
                        "nogui"
                    ]

            self.finished.emit(True, "Server launch preparation complete.", cmd, java_exec)
        except Exception as e:
            self.logger.error(f"LocalServerStartWorker error: {e}")
            self.finished.emit(False, str(e), [], "")

class LocalServerRunner(QObject):
    log_output = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    process_finished = pyqtSignal(int)

    def __init__(self, server_folder: str, max_ram: int = 2048, java_path: str = "auto"):
        super().__init__()
        self.server_folder = server_folder
        self.server_dir = get_dot_neurax_dir() / "servers" / server_folder
        self.max_ram = max_ram
        self.java_path = java_path
        self.process = None
        self.logger = Logger.get_instance()
        self.is_running = False
        self.start_worker = None

    def start(self):
        if self.is_running:
            return

        self.status_changed.emit("STARTING")
        self.start_worker = LocalServerStartWorker(self.server_folder, self.max_ram, self.java_path)
        self.start_worker.progress.connect(self.log_output.emit)
        self.start_worker.finished.connect(self._on_start_worker_finished)
        self.start_worker.start()

    def _on_start_worker_finished(self, success: bool, msg: str, cmd: list, java_exec: str):
        if not success or not cmd:
            self.is_running = False
            self.status_changed.emit("OFFLINE")
            self.log_output.emit(f"[LocalServer Startup Failed] {msg}")
            return

        self.log_output.emit(f"[LocalServer] Starting server process: {' '.join(cmd)}")

        try:
            # Spawn the server with CREATE_NO_WINDOW | DETACHED_PROCESS
            # | CREATE_NEW_PROCESS_GROUP so the JVM can never briefly
            # flash a console window. We keep stdin=PIPE so the user can
            # still send console commands (e.g. ``stop``) from the
            # in-launcher console panel, and stdout=PIPE so the launcher
            # keeps streaming the server log into its built-in console.
            self.process = popen_no_window(
                cmd,
                cwd=str(self.server_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                allow_stdin_pipe=True,
            )
            self.is_running = True
            self.status_changed.emit("ONLINE")

            def stream_logs():
                try:
                    for line in iter(self.process.stdout.readline, ''):
                        if line:
                            self.log_output.emit(line.rstrip())
                    self.process.stdout.close()
                    code = self.process.wait()
                except Exception as ex:
                    self.log_output.emit(f"[LocalServer Error] {ex}")
                    code = -1
                finally:
                    self.is_running = False
                    self.status_changed.emit("OFFLINE")
                    self.process_finished.emit(code)

            threading.Thread(target=stream_logs, daemon=True).start()

        except Exception as e:
            self.is_running = False
            self.status_changed.emit("OFFLINE")
            self.log_output.emit(f"[LocalServer Startup Failed] {e}")

    def send_command(self, command: str):
        if self.process and self.is_running and self.process.stdin:
            try:
                self.process.stdin.write(command.strip() + "\n")
                self.process.stdin.flush()
                self.log_output.emit(f"> {command}")
            except Exception as e:
                self.log_output.emit(f"[Error sending command] {e}")

    def stop(self):
        if self.is_running and self.process:
            self.status_changed.emit("STOPPING")
            self.send_command("stop")
            def force_kill():
                if self.is_running and self.process and self.process.poll() is None:
                    kill_server_process_by_folder(self.server_dir)
                    if self.process and self.process.poll() is None:
                        try:
                            self.process.kill()
                        except Exception:
                            pass
            threading.Timer(6.0, force_kill).start()
