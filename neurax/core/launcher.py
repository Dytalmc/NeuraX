import sys
import os
import json
import math
import time
import shutil
import zipfile
import requests
import subprocess
import threading
import re
import copy
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QBuffer, QIODevice
from neurax.core.java_finder import JavaFinder
from neurax.core.logger import Logger
from neurax.core.discord_rpc import DiscordManager
from neurax.core.config import get_dot_neurax_dir, get_neurax_dir

try:
    import minecraft_launcher_lib
    MCLIB_AVAILABLE = True
except ImportError:
    MCLIB_AVAILABLE = False


def is_valid_jar(file_path) -> bool:
    if not file_path:
        return False
    p = Path(file_path)
    if not p.exists() or p.stat().st_size == 0:
        return False
    try:
        with zipfile.ZipFile(p, "r") as zf:
            return zf.testzip() is None
    except Exception:
        return False


def format_bytes(size_bytes: float) -> str:
    if size_bytes < 1024:
        return f" {size_bytes:.0f} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def format_eta(seconds: float) -> str:
    if seconds <= 0 or math.isinf(seconds) or math.isnan(seconds):
        return "00:00"
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def name_to_path(name: str) -> str:
    ext = "jar"
    if "@" in name:
        name, ext = name.split("@", 1)
    parts = name.split(":")
    if len(parts) < 3:
        return ""
    group = parts[0].replace(".", "/")
    artifact = parts[1]
    version = parts[2]
    classifier = parts[3] if len(parts) > 3 else ""
    if classifier:
        filename = f"{artifact}-{version}-{classifier}.{ext}"
    else:
        filename = f"{artifact}-{version}.{ext}"
    return f"{group}/{artifact}/{version}/{filename}"


def get_required_java_major(mc_version: str) -> int:
    try:
        parts = [int(p) for p in re.findall(r'\d+', str(mc_version))]
        if parts:
            major = parts[0]
            if major == 1 and len(parts) >= 2:
                minor = parts[1]
                if minor >= 20:
                    patch = parts[2] if len(parts) >= 3 else 0
                    if minor == 20 and patch >= 5:
                        return 21
                    elif minor == 20:
                        return 17
                    else:
                        return 21
                elif minor >= 18:
                    return 17
                elif minor == 17:
                    return 16
                else:
                    return 8
            elif major >= 26 or major > 1:
                return 25
        return 21
    except Exception:
        pass
    return 21


def ensure_launcher_profiles(game_dir: Path):
    try:
        p = Path(game_dir)
        p.mkdir(parents=True, exist_ok=True)
        profiles_file = p / "launcher_profiles.json"
        if not profiles_file.exists():
            with open(profiles_file, "w", encoding="utf-8") as f:
                json.dump({"profiles": {}}, f, indent=2)
    except Exception:
        pass


def optimize_game_options(game_dir: Path):
    ensure_launcher_profiles(game_dir)
    options_txt = Path(game_dir) / "options.txt"
    # Settings the launcher auto-applies when the user hasn't explicitly
    # set them. Merge logic (below):
    #   * if the key already has a non-empty value in options.txt, that
    #     user-chosen value is kept (so this block NEVER clobbers the
    #     user's settings, it only fills in missing defaults);
    #   * if the key is missing or empty, the perf value here is written.
    # FPS notes:
    #   * maxFps = 0 means "uncapped" in Minecraft. 260 was a conservative
    #     cap that prevented high-end rigs (Sodium + Fabric + mods) from
    #     reaching their natural 500-1000 FPS headroom.
    #   * fullscreen = true (real fullscreen) bypasses the Windows DWM
    #     compositor and is a major FPS win vs borderless / windowed. We
    #     still respect the user's choice if they explicitly set
    #     fullscreen:false.
    perf_settings = {
        "maxFps": "0",
        "enableVsync": "false",
        "renderClouds": "false",
        "pauseOnLostFocus": "false",
        "prioritizeChunkUpdates": "2",
        "chunkBuilderMode": "1",
        "entityShadows": "false",
        "graphicsMode": "1",   # 0=fast, 1=fancy, 2=fabulous. "1" keeps the old default; set "0" in-game for max FPS.
        "fullscreen": "true",
    }
    # Migration: if an older launcher version wrote one of these known
    # bad values into the user's options.txt, blank it out so the new
    # perf value above takes effect on this launch. The merge logic only
    # overwrites empty values, so without this step an existing user's
    # `maxFps:260` line would block the upgrade to `0` (uncapped).
    legacy_value_migration = {
        "maxFps": {"260", "120", "60"},
    }
    lines = []
    existing_keys = set()
    if options_txt.exists():
        try:
            with open(options_txt, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if ":" in line:
                        k, v = line.split(":", 1)
                        k_str = k.strip()
                        existing_keys.add(k_str)
                        v_stripped = v.strip()
                        # Apply migration: known-bad legacy values get blanked
                        # so the new perf default below takes effect.
                        if k_str in legacy_value_migration and v_stripped in legacy_value_migration[k_str]:
                            v_stripped = ""
                        if k_str in perf_settings and v_stripped == "":
                            lines.append(f"{k_str}:{perf_settings[k_str]}\n")
                        else:
                            lines.append(line)
                    else:
                        lines.append(line)
        except Exception:
            lines = []

    for k, v in perf_settings.items():
        if k not in existing_keys:
            lines.append(f"{k}:{v}\n")

    try:
        with open(options_txt, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except Exception:
        pass


def resolve_neoforge_version(mc_version: str) -> str:
    """Resolves the exact NeoForge version string for a given Minecraft version."""
    mc_ver_clean = str(mc_version).strip()
    if hasattr(minecraft_launcher_lib, "neoforge") and hasattr(minecraft_launcher_lib.neoforge, "find_neoforge_version"):
        try:
            res = minecraft_launcher_lib.neoforge.find_neoforge_version(mc_ver_clean)
            if res and isinstance(res, str) and res != mc_ver_clean:
                return res
        except Exception:
            pass

    all_versions = []
    if hasattr(minecraft_launcher_lib, "neoforge") and hasattr(minecraft_launcher_lib.neoforge, "get_neoforge_versions"):
        try:
            raw_list = minecraft_launcher_lib.neoforge.get_neoforge_versions()
            for item in raw_list:
                if isinstance(item, str):
                    all_versions.append(item)
                elif isinstance(item, dict):
                    v_str = str(item.get("version") or item.get("name") or item.get("raw_target") or "")
                    if v_str:
                        all_versions.append(v_str)
        except Exception:
            pass

    if not all_versions:
        try:
            resp = requests.get("https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml", timeout=8)
            if resp.status_code == 200:
                all_versions = re.findall(r'<version>([^<]+)</version>', resp.text)
        except Exception:
            pass

    prefix_candidates = []
    parts = [int(p) for p in re.findall(r'\d+', mc_ver_clean)]
    if len(parts) >= 2:
        major = parts[0]
        minor = parts[1]
        patch = parts[2] if len(parts) >= 3 else 0
        if major == 1:
            if minor == 20 and patch == 1:
                prefix_candidates = ["47.1.", "1.20.1-"]
            elif minor >= 20:
                prefix_candidates = [f"{minor}.{patch}.", f"{mc_ver_clean}-", f"-{mc_ver_clean}"]
        elif major >= 20:
            prefix_candidates = [f"{major}.{minor}.", f"{mc_ver_clean}-"]

    matching_versions = []
    for v in all_versions:
        v_clean = str(v).strip()
        if not v_clean:
            continue
        matches = False
        if mc_ver_clean in v_clean:
            matches = True
        elif prefix_candidates:
            for pref in prefix_candidates:
                if pref in v_clean or v_clean.startswith(pref):
                    matches = True
                    break
        if matches:
            matching_versions.append(v_clean)

    if matching_versions:
        def version_key(v_str):
            nums = [int(n) for n in re.findall(r'\d+', v_str)]
            return nums if nums else [0]
        matching_versions.sort(key=version_key, reverse=True)
        return matching_versions[0]

    return ""


def resolve_forge_version(mc_version: str) -> str:
    """Resolves the exact Forge version string for a given Minecraft version."""
    mc_ver_clean = str(mc_version).strip()
    if hasattr(minecraft_launcher_lib, "forge") and hasattr(minecraft_launcher_lib.forge, "find_forge_version"):
        try:
            res = minecraft_launcher_lib.forge.find_forge_version(mc_ver_clean)
            if res and isinstance(res, str) and res != mc_ver_clean:
                return res
        except Exception:
            pass

    all_versions = []
    if hasattr(minecraft_launcher_lib, "forge") and hasattr(minecraft_launcher_lib.forge, "get_forge_versions"):
        try:
            raw_list = minecraft_launcher_lib.forge.get_forge_versions()
            for item in raw_list:
                if isinstance(item, str):
                    all_versions.append(item)
                elif isinstance(item, dict):
                    v_str = str(item.get("version") or item.get("name") or "")
                    if v_str:
                        all_versions.append(v_str)
        except Exception:
            pass

    if not all_versions:
        try:
            resp = requests.get("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json", timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                promos = data.get("promos", {})
                for key in (f"{mc_ver_clean}-recommended", f"{mc_ver_clean}-latest"):
                    if key in promos:
                        return f"{mc_ver_clean}-{promos[key]}"
        except Exception:
            pass

    matching_versions = []
    for v in all_versions:
        v_clean = str(v).strip()
        if mc_ver_clean in v_clean:
            matching_versions.append(v_clean)

    if matching_versions:
        def version_key(v_str):
            nums = [int(n) for n in re.findall(r'\d+', v_str)]
            return nums if nums else [0]
        matching_versions.sort(key=version_key, reverse=True)
        return matching_versions[0]

    return ""


def install_fabric_fallback(mc_version: str, game_dir: Path, logger) -> str:
    try:
        meta_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}"
        res = requests.get(meta_url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                loader_ver = data[0].get("loader", {}).get("version", "0.16.10")
                profile_url = f"https://meta.fabricmc.net/v2/versions/loader/{mc_version}/{loader_ver}/profile/json"
                p_res = requests.get(profile_url, timeout=10)
                if p_res.status_code == 200:
                    v_id = f"fabric-loader-{loader_ver}-{mc_version}"
                    v_dir = Path(game_dir) / "versions" / v_id
                    v_dir.mkdir(parents=True, exist_ok=True)
                    with open(v_dir / f"{v_id}.json", "w", encoding="utf-8") as f:
                        f.write(p_res.text)
                    return v_id
    except Exception as e:
        logger.warning(f"Fabric fallback install notice: {e}")
    return ""


def install_quilt_fallback(mc_version: str, game_dir: Path, logger) -> str:
    try:
        meta_url = f"https://meta.quiltmc.org/v2/versions/loader/{mc_version}"
        res = requests.get(meta_url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list) and len(data) > 0:
                loader_ver = data[0].get("loader", {}).get("version", "0.26.0")
                profile_url = f"https://meta.quiltmc.org/v2/versions/loader/{mc_version}/{loader_ver}/profile/json"
                p_res = requests.get(profile_url, timeout=10)
                if p_res.status_code == 200:
                    v_id = f"quilt-loader-{loader_ver}-{mc_version}"
                    v_dir = Path(game_dir) / "versions" / v_id
                    v_dir.mkdir(parents=True, exist_ok=True)
                    with open(v_dir / f"{v_id}.json", "w", encoding="utf-8") as f:
                        f.write(p_res.text)
                    return v_id
    except Exception as e:
        logger.warning(f"Quilt fallback install notice: {e}")
    return ""


def install_neoforge_loader(nf_ver: str, mc_ver: str, game_dir: Path, java_exec: str, callback: dict, logger) -> bool:
    if not nf_ver:
        return False

    ensure_launcher_profiles(game_dir)
    v_dir_path = Path(game_dir) / "versions"
    existing_versions = set(d.name for d in v_dir_path.iterdir() if d.is_dir()) if v_dir_path.exists() else set()

    success = False

    if hasattr(minecraft_launcher_lib, "neoforge") and hasattr(minecraft_launcher_lib.neoforge, "install_neoforge_version"):
        try:
            minecraft_launcher_lib.neoforge.install_neoforge_version(
                nf_ver,
                str(game_dir),
                callback=callback,
                java=java_exec if (java_exec and os.path.isfile(java_exec)) else None
            )
            if find_installed_loader_version(game_dir, "neoforge", mc_ver) != mc_ver:
                return True
        except TypeError:
            try:
                minecraft_launcher_lib.neoforge.install_neoforge_version(
                    nf_ver,
                    str(game_dir),
                    callback=callback
                )
                if find_installed_loader_version(game_dir, "neoforge", mc_ver) != mc_ver:
                    return True
            except Exception as e2:
                logger.warning(f"minecraft_launcher_lib neoforge install error: {e2}")
        except Exception as e:
            logger.warning(f"minecraft_launcher_lib neoforge install error: {e}")

    urls = [
        f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{nf_ver}/neoforge-{nf_ver}-installer.jar",
        f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{mc_ver}-{nf_ver}/neoforge-{mc_ver}-{nf_ver}-installer.jar"
    ]
    for url in urls:
        try:
            logger.info(f"Downloading NeoForge installer from {url}...")
            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                temp_jar = game_dir / "neoforge-installer.jar"
                with open(temp_jar, "wb") as f:
                    f.write(resp.content)

                cmd = [java_exec or "java", "-Djava.awt.headless=true", "-jar", str(temp_jar), "--installClient", str(game_dir)]
                creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                logger.info(f"Executing NeoForge installer: {' '.join(cmd)}")
                res = subprocess.run(cmd, cwd=str(game_dir), stdin=subprocess.DEVNULL, timeout=180, creationflags=creationflags, capture_output=True, text=True)
                if temp_jar.exists():
                    try:
                        temp_jar.unlink()
                    except Exception:
                        pass
                logger.info(f"NeoForge installer result code: {res.returncode}")
                if res.returncode == 0:
                    success = True
                    break
                else:
                    logger.warning(f"NeoForge installer failed with code {res.returncode}: {res.stdout} {res.stderr}")
        except Exception as ex:
            logger.warning(f"Direct NeoForge installer download/execution error: {ex}")

    if not success:
        if v_dir_path.exists():
            for d in v_dir_path.iterdir():
                if d.is_dir() and d.name not in existing_versions:
                    if "neoforge" in d.name.lower():
                        try:
                            shutil.rmtree(d)
                        except Exception:
                            pass

    return success


def install_forge_loader(forge_ver: str, game_dir: Path, java_exec: str, callback: dict, logger) -> bool:
    if not forge_ver:
        return False

    ensure_launcher_profiles(game_dir)
    v_dir_path = Path(game_dir) / "versions"
    existing_versions = set(d.name for d in v_dir_path.iterdir() if d.is_dir()) if v_dir_path.exists() else set()

    success = False
    mc_ver = forge_ver.split("-")[0] if "-" in forge_ver else forge_ver

    if hasattr(minecraft_launcher_lib, "forge") and hasattr(minecraft_launcher_lib.forge, "install_forge_version"):
        try:
            minecraft_launcher_lib.forge.install_forge_version(
                forge_ver,
                str(game_dir),
                callback=callback,
                java=java_exec if (java_exec and os.path.isfile(java_exec)) else None
            )
            if find_installed_loader_version(game_dir, "forge", mc_ver) != mc_ver:
                return True
        except TypeError:
            try:
                minecraft_launcher_lib.forge.install_forge_version(
                    forge_ver,
                    str(game_dir),
                    callback=callback
                )
                if find_installed_loader_version(game_dir, "forge", mc_ver) != mc_ver:
                    return True
            except Exception as e2:
                logger.warning(f"minecraft_launcher_lib forge install error: {e2}")
        except Exception as e:
            logger.warning(f"minecraft_launcher_lib forge install error: {e}")

    url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{forge_ver}/forge-{forge_ver}-installer.jar"
    try:
        logger.info(f"Downloading Forge installer from {url}...")
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200:
            temp_jar = game_dir / "forge-installer.jar"
            with open(temp_jar, "wb") as f:
                f.write(resp.content)

            cmd = [java_exec or "java", "-Djava.awt.headless=true", "-jar", str(temp_jar), "--installClient", str(game_dir)]
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            logger.info(f"Executing Forge installer: {' '.join(cmd)}")
            res = subprocess.run(cmd, cwd=str(game_dir), stdin=subprocess.DEVNULL, timeout=180, creationflags=creationflags, capture_output=True, text=True)
            if temp_jar.exists():
                try:
                    temp_jar.unlink()
                except Exception:
                    pass
            logger.info(f"Forge installer result code: {res.returncode}")
            if res.returncode == 0:
                success = True
            else:
                logger.warning(f"Forge installer failed with code {res.returncode}: {res.stdout} {res.stderr}")
    except Exception as ex:
        logger.warning(f"Direct Forge installer download/execution error: {ex}")

    if not success:
        if v_dir_path.exists():
            for d in v_dir_path.iterdir():
                if d.is_dir() and d.name not in existing_versions:
                    if "forge" in d.name.lower():
                        try:
                            shutil.rmtree(d)
                        except Exception:
                            pass

    return success


def find_installed_loader_version(game_dir: Path, loader: str, mc_version: str) -> str:
    search_dirs = [
        Path(game_dir) / "versions"
    ]

    loader_l = loader.lower().strip()
    if loader_l in ("vanilla", ""):
        return mc_version

    candidates = []
    mc_ver_clean = mc_version.strip()

    nf_prefix = ""
    parts = [int(p) for p in re.findall(r'\d+', mc_ver_clean)]
    if len(parts) >= 2:
        if parts[0] == 1:
            if parts[1] == 20:
                patch = parts[2] if len(parts) >= 3 else 0
                if patch == 1:
                    nf_prefix = "47.1"
                else:
                    nf_prefix = f"20.{patch}"
            elif parts[1] >= 21:
                patch = parts[2] if len(parts) >= 3 else 0
                nf_prefix = f"{parts[1]}.{patch}"
        elif parts[0] >= 20:
            nf_prefix = f"{parts[0]}.{parts[1]}"

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for v_dir in s_dir.iterdir():
            if v_dir.is_dir():
                v_id = v_dir.name
                json_file = v_dir / f"{v_id}.json"
                if not json_file.exists() or json_file.stat().st_size == 0:
                    continue
                v_id_l = v_id.lower()

                v_data = {}
                v_data_str = ""
                try:
                    with open(json_file, "r", encoding="utf-8", errors="ignore") as f:
                        v_data = json.load(f)
                        if not isinstance(v_data, dict) or "id" not in v_data:
                            continue
                        v_data_str = json.dumps(v_data).lower()
                except Exception:
                    continue

                matches_loader = False
                if loader_l == "fabric":
                    if "fabric" in v_id_l or "fabricmc" in v_data_str or "net.fabricmc" in v_data_str:
                        matches_loader = True
                elif loader_l == "quilt":
                    if "quilt" in v_id_l or "quiltmc" in v_data_str or "org.quiltmc" in v_data_str:
                        matches_loader = True
                elif loader_l == "forge":
                    if ("forge" in v_id_l and "neoforge" not in v_id_l) or ("minecraftforge" in v_data_str and "neoforge" not in v_id_l) or ("net.minecraftforge" in v_data_str and "neoforge" not in v_id_l) or ("forge" in v_data_str and "neoforge" not in v_id_l):
                        matches_loader = True
                elif loader_l == "neoforge":
                    if "neoforge" in v_id_l or "neoforged" in v_data_str or "net.neoforged" in v_data_str or "neoforge" in v_data_str:
                        matches_loader = True

                if matches_loader:
                    score = json_file.stat().st_mtime
                    is_mc_match = False
                    if mc_ver_clean in v_id:
                        is_mc_match = True
                    elif loader_l == "neoforge" and nf_prefix and (nf_prefix in v_id_l or nf_prefix in v_data_str):
                        is_mc_match = True
                    elif v_data:
                        inherits = str(v_data.get("inheritsFrom", "")).strip()
                        client_v = str(v_data.get("clientVersion", "")).strip()
                        mc_v = str(v_data.get("minecraftVersion", "")).strip()
                        ver_v = str(v_data.get("version", "")).strip()
                        if (
                            (inherits and (inherits == mc_ver_clean or mc_ver_clean in inherits)) or
                            (client_v and (client_v == mc_ver_clean or mc_ver_clean in client_v)) or
                            (mc_v and (mc_v == mc_ver_clean or mc_ver_clean in mc_v)) or
                            (ver_v and ver_v == mc_ver_clean)
                        ):
                            is_mc_match = True

                    if is_mc_match:
                        score += 10000000
                        candidates.append((score, v_id))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return mc_version


class LaunchWorker(QThread):
    progress = pyqtSignal(int, str, str)
    finished = pyqtSignal(bool, str)
    game_started = pyqtSignal()
    game_exited = pyqtSignal(int)
    error_occurred = pyqtSignal(str)

    def __init__(
        self, 
        neurax_dir: Path = None,
        instance_data: dict = None,
        session: dict = None,
        custom_java: str = "auto",
        jvm_args: str = "",
        max_ram: int = 4096,
        auth_mgr = None,
        config_mgr = None,
        server_ip: str = "",
        server_port: int = 25565,
        config = None,
        instance_mgr = None,
        server_host: str = None
    ):
        super().__init__()
        
        cfg = config or config_mgr
        self.config_mgr = cfg
        self.auth_mgr = auth_mgr

        if cfg is not None:
            self.neurax_dir = Path(cfg.neurax_dir)
            inst_name = cfg.get("selected_instance", "Default")
            if instance_mgr:
                self.instance_data = instance_mgr.get_instance(inst_name) or {"name": inst_name}
            else:
                self.instance_data = instance_data or {"name": inst_name}
            if auth_mgr:
                self.session = auth_mgr.get_session()
            else:
                self.session = session or {}
            self.custom_java = cfg.get("custom_java", "auto")
            self.jvm_args = cfg.get("jvm_args", "")
            self.max_ram = cfg.get("max_ram", 4096)
            self.server_ip = server_host or server_ip or ""
            self.server_port = server_port
        else:
            self.neurax_dir = Path(neurax_dir) if neurax_dir else get_dot_neurax_dir()
            self.instance_data = instance_data or {}
            self.session = session or {}
            self.custom_java = custom_java
            self.jvm_args = jvm_args
            self.max_ram = max_ram
            self.server_ip = server_host or server_ip or ""
            self.server_port = server_port

        self.logger = Logger.get_instance()
        self.process = None

    def run(self):
        try:
            mode = self.session.get("mode", "microsoft")
            token = self.session.get("access_token", "0")
            if mode == "microsoft" and (not token or token == "0"):
                raise RuntimeError("Microsoft account authentication required. Please log in with your Microsoft account in Launcher Settings to play.")

            version = self.instance_data.get("version", "1.20.4")
            loader = self.instance_data.get("loader", "Vanilla")
            inst_name = self.instance_data.get("name", "Default")
            game_dir = Path(self.instance_data.get("game_dir", get_dot_neurax_dir() / "instances" / inst_name / ".minecraft"))
            game_dir.mkdir(parents=True, exist_ok=True)
            (game_dir / "mods").mkdir(parents=True, exist_ok=True)
            ensure_launcher_profiles(game_dir)

            self.progress.emit(10, f"Preparing {inst_name} ({loader} {version})...", "")
            optimize_game_options(game_dir)

            max_val = [100]

            def set_status(status: str):
                self.progress.emit(50, status, "")

            def set_max(val: int):
                try:
                    v = int(val)
                    if v > 0:
                        max_val[0] = v
                except (ValueError, TypeError):
                    pass

            def set_progress(val: int):
                try:
                    prog = int(val)
                except (ValueError, TypeError):
                    prog = 0

                m = max_val[0]
                if prog > m:
                    m = prog
                    max_val[0] = m

                if m > 0:
                    pct = int((prog / m) * 100)
                else:
                    pct = 0
                pct = max(0, min(100, pct))

                overall = min(90, 25 + int(pct * 0.65))
                if m > 100:
                    display_text = f"Downloading files... {prog}/{m} ({pct}%)"
                else:
                    display_text = f"Downloading files... {pct}%"

                self.progress.emit(overall, display_text, "")

            callback = {
                "setStatus": set_status,
                "setMax": set_max,
                "setProgress": set_progress
            }

            if MCLIB_AVAILABLE:
                self.progress.emit(20, "Resolving Java runtime...", "")

                req_major = get_required_java_major(version)
                java_exec = None

                candidates = []
                seen_cands = set()

                def add_candidate(p):
                    if p and os.path.isfile(p):
                        norm = os.path.normpath(p)
                        if norm not in seen_cands:
                            seen_cands.add(norm)
                            candidates.append(norm)

                if self.custom_java and self.custom_java != "auto":
                    add_candidate(self.custom_java)

                jh = os.environ.get("JAVA_HOME")
                if jh:
                    jh_bin = os.path.join(jh, "bin", "java.exe" if sys.platform == "win32" else "java")
                    add_candidate(jh_bin)

                sys_java = shutil.which("java") or shutil.which("java.exe")
                if sys_java:
                    add_candidate(sys_java)

                for _name, jpath in JavaFinder.find_java_installations():
                    add_candidate(jpath)

                for c_path in candidates:
                    if JavaFinder.get_java_major_version(c_path) == req_major:
                        java_exec = c_path
                        break

                if not java_exec or not os.path.isfile(java_exec):
                    try:
                        req_jvm = "java-runtime-gamma" if req_major == 21 else ("java-runtime-delta" if req_major == 25 else "java-runtime-alpha")
                        if hasattr(minecraft_launcher_lib, "runtime"):
                            if hasattr(minecraft_launcher_lib.runtime, "get_executable_path"):
                                cand = minecraft_launcher_lib.runtime.get_executable_path(req_jvm, str(game_dir))
                                if cand and os.path.isfile(cand) and JavaFinder.get_java_major_version(cand) == req_major:
                                    java_exec = cand

                            if (not java_exec or not os.path.isfile(java_exec)) and hasattr(minecraft_launcher_lib.runtime, "install_jvm_runtime"):
                                self.progress.emit(22, f"Downloading Java Runtime ({req_jvm})...", "")
                                minecraft_launcher_lib.runtime.install_jvm_runtime(req_jvm, str(game_dir), callback=callback)
                                cand = minecraft_launcher_lib.runtime.get_executable_path(req_jvm, str(game_dir))
                                if cand and os.path.isfile(cand) and JavaFinder.get_java_major_version(cand) == req_major:
                                    java_exec = cand
                    except Exception as je:
                        self.logger.warning(f"Failed to auto-install JVM runtime: {je}")

                if not java_exec or not os.path.isfile(java_exec):
                    req_name = "Java 21" if req_major == 21 else "JDK 25 (Java 25)"
                    ver_desc = "1.21.11 or below" if req_major == 21 else "26.1+"
                    err_msg = (
                        f"Java {req_major} is required for Minecraft {version} ({ver_desc}), "
                        f"but Java {req_major} was not found on your PC. Please install {req_name}."
                    )
                    self.logger.error(err_msg)
                    raise RuntimeError(err_msg)

                vanilla_json = game_dir / "versions" / version / f"{version}.json"
                vanilla_jar = game_dir / "versions" / version / f"{version}.jar"
                if not vanilla_json.exists() or not vanilla_jar.exists() or vanilla_jar.stat().st_size == 0:
                    self.progress.emit(25, f"Installing base Minecraft {version}...", "")
                    try:
                        minecraft_launcher_lib.install.install_minecraft_version(version, str(game_dir), callback=callback)
                    except Exception as ie:
                        self.logger.warning(f"Base Minecraft install notice: {ie}")

                loader_low = loader.lower().strip()
                
                # If Vanilla loader selected, check if mods exist in game_dir/mods and auto-detect loader
                if loader_low in ("vanilla", ""):
                    mods_dir = game_dir / "mods"
                    has_mods = mods_dir.exists() and any(p.suffix.lower() == ".jar" for p in mods_dir.iterdir() if p.is_file())
                    if has_mods:
                        installed_loader = find_installed_loader_version(game_dir, "fabric", version)
                        if installed_loader == version:
                            installed_loader = find_installed_loader_version(game_dir, "forge", version)
                        if installed_loader == version:
                            installed_loader = find_installed_loader_version(game_dir, "neoforge", version)
                        if installed_loader == version:
                            installed_loader = find_installed_loader_version(game_dir, "quilt", version)
                        
                        if installed_loader != version:
                            loader_low = "modded"
                            version_id = installed_loader
                            self.logger.info(f"Mods detected in instance mods folder. Using installed loader: '{version_id}'")
                        else:
                            loader_low = "fabric"
                            loader = "Fabric"

                version_id = find_installed_loader_version(game_dir, loader, version)

                need_loader_install = False
                if loader_low not in ("vanilla", ""):
                    if version_id == version:
                        need_loader_install = True
                    else:
                        loader_json = game_dir / "versions" / version_id / f"{version_id}.json"
                        if not loader_json.exists():
                            need_loader_install = True

                if need_loader_install:
                    if loader_low == "fabric":
                        try:
                            self.progress.emit(35, f"Installing Fabric Loader for {version}...", "")
                            if hasattr(minecraft_launcher_lib, "fabric"):
                                try:
                                    minecraft_launcher_lib.fabric.install_fabric(
                                        version,
                                        str(game_dir),
                                        callback=callback,
                                        java=java_exec if (java_exec and os.path.isfile(java_exec)) else None
                                    )
                                except TypeError:
                                    minecraft_launcher_lib.fabric.install_fabric(
                                        version,
                                        str(game_dir),
                                        callback=callback
                                    )
                        except Exception as fe:
                            self.logger.warning(f"Fabric installation warning: {fe}")
                        version_id = find_installed_loader_version(game_dir, "fabric", version)
                        if version_id == version:
                            fallback_v = install_fabric_fallback(version, game_dir, self.logger)
                            if fallback_v:
                                version_id = fallback_v

                    elif loader_low == "forge":
                        try:
                            self.progress.emit(35, f"Installing Forge Loader for {version}...", "")
                            forge_ver = resolve_forge_version(version)
                            if forge_ver:
                                install_forge_loader(forge_ver, game_dir, java_exec, callback, self.logger)
                        except Exception as fe:
                            self.logger.warning(f"Forge installation warning: {fe}")
                        version_id = find_installed_loader_version(game_dir, "forge", version)

                    elif loader_low == "quilt":
                        try:
                            self.progress.emit(35, f"Installing Quilt Loader for {version}...", "")
                            if hasattr(minecraft_launcher_lib, "quilt"):
                                try:
                                    minecraft_launcher_lib.quilt.install_quilt(
                                        version,
                                        str(game_dir),
                                        callback=callback,
                                        java=java_exec if (java_exec and os.path.isfile(java_exec)) else None
                                    )
                                except TypeError:
                                    minecraft_launcher_lib.quilt.install_quilt(
                                        version,
                                        str(game_dir),
                                        callback=callback
                                    )
                        except Exception as fe:
                            self.logger.warning(f"Quilt installation warning: {fe}")
                        version_id = find_installed_loader_version(game_dir, "quilt", version)
                        if version_id == version:
                            fallback_v = install_quilt_fallback(version, game_dir, self.logger)
                            if fallback_v:
                                version_id = fallback_v

                    elif loader_low == "neoforge":
                        try:
                            self.progress.emit(35, f"Installing NeoForge Loader for {version}...", "")
                            nf_ver = resolve_neoforge_version(version)
                            if nf_ver:
                                install_neoforge_loader(nf_ver, version, game_dir, java_exec, callback, self.logger)
                        except Exception as nfe:
                            self.logger.warning(f"NeoForge installation warning: {nfe}")
                        version_id = find_installed_loader_version(game_dir, "neoforge", version)

                if loader_low not in ("vanilla", "") and version_id == version:
                    raise RuntimeError(
                        f"Failed to install or resolve {loader} loader version for Minecraft {version}. "
                        "Please check your internet connection and Java installation."
                    )

                self.progress.emit(85, "Building launch arguments...", "")

                ram_args = [f"-Xmx{self.max_ram}M", f"-Xms{min(1024, self.max_ram)}M"]
                user_jvm = self.jvm_args.split() if self.jvm_args else []
                jvm_args_list = ram_args + user_jvm

                options = {
                    "username": self.session.get("username", "NeuraPlayer"),
                    "uuid": self.session.get("uuid", "00000000-0000-0000-0000-000000000000"),
                    "token": self.session.get("access_token", "0"),
                    "executablePath": java_exec,
                    "gameDirectory": str(game_dir),
                    "jvmArguments": jvm_args_list,
                }

                if self.server_ip:
                    options["server"] = self.server_ip
                    options["port"] = str(self.server_port)
                    try:
                        v_parts = [int(p) for p in re.findall(r'\d+', version)]
                        if len(v_parts) >= 2 and (v_parts[0] > 1 or (v_parts[0] == 1 and v_parts[1] >= 20)):
                            options["quickPlayMultiplayer"] = f"{self.server_ip}:{self.server_port}"
                    except Exception:
                        pass

                if self.session.get("xuid"):
                    options["xuid"] = self.session.get("xuid")

                cmd = minecraft_launcher_lib.command.get_minecraft_command(version_id, str(game_dir), options)

                java_major = JavaFinder.get_java_major_version(java_exec)
                if java_major < 24:
                    cmd = [arg for arg in cmd if not arg.startswith("--sun-misc-unsafe-memory-access")]

                self.progress.emit(95, "Launching Minecraft...", "")

                creationflags = 0
                if sys.platform == "win32":
                    creationflags = subprocess.CREATE_NO_WINDOW

                self.logger.info(f"Executing command: {' '.join(cmd)}")

                DiscordManager.get_instance().set_game_activity(
                    version=version,
                    instance_name=inst_name,
                    loader=loader,
                    server_ip=self.server_ip,
                    server_port=self.server_port
                )

                self.process = subprocess.Popen(
                    cmd,
                    cwd=str(game_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags
                )

                self.progress.emit(100, "Minecraft is running!", "")
                self.game_started.emit()
                self.finished.emit(True, f"Launched {inst_name} ({version_id}) successfully.")

                start_time = time.time()

                def monitor_process():
                    try:
                        for line in iter(self.process.stdout.readline, ''):
                            if line:
                                cleaned_line = line.rstrip()
                                self.logger.info(f"[Minecraft] {cleaned_line}")
                        self.process.stdout.close()
                        return_code = self.process.wait()
                    except Exception as ex:
                        self.logger.warning(f"Process monitor notice: {ex}")
                        return_code = -1

                    elapsed_seconds = int(time.time() - start_time)
                    self.logger.info(f"Minecraft process exited with code {return_code}. Session duration: {elapsed_seconds}s")

                    DiscordManager.get_instance().clear_game_activity()

                    if self.config_mgr:
                        try:
                            analytics = copy.deepcopy(self.config_mgr.get("analytics", {}))
                            if not isinstance(analytics, dict):
                                analytics = {}

                            inst_key = inst_name
                            inst_data = analytics.get(inst_key, {})
                            if not isinstance(inst_data, dict):
                                inst_data = {}

                            prev_total = inst_data.get("total_seconds", 0)
                            inst_data["total_seconds"] = prev_total + elapsed_seconds
                            inst_data["last_session_seconds"] = elapsed_seconds
                            inst_data["last_played"] = int(time.time())

                            analytics[inst_key] = inst_data
                            self.config_mgr.set("analytics", analytics)
                        except Exception as ae:
                            self.logger.warning(f"Failed to update playtime analytics: {ae}")

                    self.game_exited.emit(return_code)

                threading.Thread(target=monitor_process, daemon=True).start()

            else:
                raise RuntimeError("minecraft-launcher-lib is not available in environment.")

        except Exception as e:
            self.logger.error(f"LaunchWorker Error: {e}")
            self.error_occurred.emit(str(e))
            self.finished.emit(False, str(e))
