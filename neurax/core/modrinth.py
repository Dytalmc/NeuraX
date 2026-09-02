import os
import re
import json
import time
import html
import shutil
import tempfile
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from neurax.core.config import get_dot_neurax_dir
from neurax.core.logger import Logger

MODRINTH_API_BASE = "https://api.modrinth.com/v2"
HEADERS = {
    "User-Agent": "NeuraX-MCL/4.0.0 (https://github.com/Dytalmc/NeuraX-MCL)",
    "Accept": "application/json"
}

PROJECT_TYPES = {
    "All": "",
    "Mods": "mod",
    "Resource Packs": "resourcepack",
    "Shader Packs": "shader",
    "Plugins": "plugin",
    "Data Packs": "datapack",
    "Modpacks": "modpack"
}

LOADERS = [
    "All", "Fabric", "Forge", "NeoForge", "Quilt", "Paper", "Purpur", "Spigot", "Bukkit", "Iris", "OptiFine", "Vanilla"
]

SORT_OPTIONS = {
    "Relevance": "relevance",
    "Most Downloads": "downloads",
    "Most Follows": "follows",
    "Newest": "newest",
    "Recently Updated": "updated"
}

def format_bytes(size_bytes: float) -> str:
    if size_bytes <= 0:
        return "Unknown size"
    elif size_bytes < 1024:
        return f"{size_bytes:.0f} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def render_markdown_to_html(md: str, accent_color: str = "#00F0FF") -> str:
    """Converts Markdown text into clean HTML formatted for Modrinth dark slate and launcher theme."""
    if not md or not md.strip():
        return "<i style='color: #A1A1AA;'>No detailed description provided for this project.</i>"

    try:
        from PyQt6.QtGui import QColor
        qc = QColor(accent_color)
        accent_hex = qc.name()
        bg_rgba = f"rgba({qc.red()}, {qc.green()}, {qc.blue()}, 0.08)"
    except Exception:
        accent_hex = accent_color
        bg_rgba = "rgba(0, 240, 255, 0.08)"

    try:
        import markdown
        raw_html = markdown.markdown(md, extensions=['extra', 'tables', 'fenced_code'])
        return f"""
        <style>
            body {{
                color: #E0E6ED;
                font-family: 'Segoe UI', -apple-system, sans-serif;
                font-size: 13px;
                line-height: 1.6;
                background-color: #111215;
                padding: 10px;
            }}
            a {{ color: {accent_hex}; text-decoration: none; font-weight: bold; }}
            a:hover {{ text-decoration: underline; }}
            h1 {{ color: {accent_hex}; border-bottom: 2px solid {accent_hex}; padding-bottom: 6px; margin-top: 18px; margin-bottom: 10px; font-size: 20px; font-weight: 800; }}
            h2 {{ color: #FFFFFF; border-bottom: 1px solid #2D3139; padding-bottom: 4px; margin-top: 16px; margin-bottom: 8px; font-size: 17px; font-weight: 700; }}
            h3 {{ color: {accent_hex}; margin-top: 14px; margin-bottom: 6px; font-size: 15px; font-weight: 700; }}
            code {{ background-color: #21232A; color: {accent_hex}; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 12px; }}
            pre {{ background-color: #181A1F; color: {accent_hex}; border: 1px solid #2D3139; border-radius: 8px; padding: 12px; font-family: monospace; overflow-x: auto; }}
            img {{ max-width: 100%; border-radius: 8px; margin: 10px 0; display: block; }}
            table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
            th, td {{ border: 1px solid #2D3139; padding: 8px 12px; text-align: left; }}
            th {{ background-color: #181A1F; color: {accent_hex}; font-weight: bold; }}
            blockquote {{ border-left: 4px solid {accent_hex}; background-color: {bg_rgba}; padding: 8px 14px; margin: 10px 0; border-radius: 0 8px 8px 0; color: #D1D5DB; }}
            ul, ol {{ padding-left: 22px; margin: 8px 0; }}
            li {{ margin-bottom: 4px; }}
        </style>
        {raw_html}
        """
    except ImportError:
        pass

    text = md.replace("\r\n", "\n")

    def replace_code_block(match):
        code = html.escape(match.group(1).strip())
        return f'<pre style="background-color: #181A1F; color: {accent_hex}; border: 1px solid #2D3139; border-radius: 8px; padding: 12px; font-family: monospace;">{code}</pre>'
    text = re.sub(r'```(?:[a-zA-Z0-9_+\-]*)\n(.*?)```', replace_code_block, text, flags=re.DOTALL)

    text = re.sub(r'`([^`]+)`', rf'<code style="background-color: #21232A; color: {accent_hex}; padding: 2px 6px; border-radius: 4px; font-family: monospace;">\1</code>', text)

    def replace_img(match):
        alt = html.escape(match.group(1) or "Image")
        url = match.group(2)
        return f'<div align="center" style="margin: 12px 0;"><img src="{url}" alt="{alt}" style="max-width: 100%; border-radius: 8px;"/><br><i style="color: #A1A1AA; font-size: 11px;">{alt}</i></div>'
    text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replace_img, text)

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', rf'<a href="\2" style="color: {accent_hex}; font-weight: bold; text-decoration: none;">\1</a>', text)

    text = re.sub(r'^### (.*?)$', rf'<h3 style="color: {accent_hex}; margin-top: 14px; margin-bottom: 6px;">\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.*?)$', r'<h2 style="color: #FFFFFF; border-bottom: 1px solid #2D3139; padding-bottom: 4px; margin-top: 16px; margin-bottom: 8px;">\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^# (.*?)$', rf'<h1 style="color: {accent_hex}; border-bottom: 2px solid {accent_hex}; padding-bottom: 6px; margin-top: 18px; margin-bottom: 10px;">\1</h1>', text, flags=re.MULTILINE)

    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)
    text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
    text = re.sub(r'_([^_]+)_', r'<i>\1</i>', text)

    text = re.sub(r'^[\*\-] (.*?)$', r'• \1<br>', text, flags=re.MULTILINE)
    text = text.replace("\n\n", "<br><br>").replace("\n", "<br>")

    return f"""
    <style>
        body {{
            color: #E0E6ED;
            font-family: 'Segoe UI', -apple-system, sans-serif;
            font-size: 13px;
            line-height: 1.6;
            background-color: #111215;
            padding: 10px;
        }}
        a {{ color: {accent_hex}; text-decoration: none; font-weight: bold; }}
        a:hover {{ text-decoration: underline; }}
    </style>
    <div style="color: #E0E6ED; font-size: 13px; line-height: 1.6;">{text}</div>
    """

class ModrinthAPI:
    """Modrinth Lab API v2 Client with session connection pooling, instant in-memory caching, and error handling."""

    _session = None
    _cache = {}
    _CACHE_TTL = 300  # 5 minutes in-memory cache

    @classmethod
    def get_session(cls) -> requests.Session:
        if cls._session is None:
            s = requests.Session()
            s.headers.update(HEADERS)
            cls._session = s
        return cls._session

    @classmethod
    def _get_cached(cls, key: str) -> Optional[Any]:
        if key in cls._cache:
            ts, data = cls._cache[key]
            if time.time() - ts < cls._CACHE_TTL:
                return data
        return None

    @classmethod
    def _set_cache(cls, key: str, data: Any):
        cls._cache[key] = (time.time(), data)

    @classmethod
    def search_projects(
        cls,
        query: str = "",
        project_type: str = "",
        loader: str = "",
        version: str = "",
        sort_by: str = "relevance",
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        cache_key = f"search:{query}:{project_type}:{loader}:{version}:{sort_by}:{limit}:{offset}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached

        facets = []
        if project_type and project_type != "All":
            ptype_val = PROJECT_TYPES.get(project_type, project_type.lower())
            if ptype_val:
                facets.append([f"project_type:{ptype_val}"])

        if loader and loader.lower() != "all":
            facets.append([f"categories:{loader.lower()}"])

        if version and version.lower() != "all":
            facets.append([f"versions:{version}"])

        params = {
            "query": query.strip(),
            "index": SORT_OPTIONS.get(sort_by, sort_by),
            "limit": limit,
            "offset": offset
        }
        if facets:
            params["facets"] = json.dumps(facets)

        try:
            resp = cls.get_session().get(f"{MODRINTH_API_BASE}/search", params=params, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                cls._set_cache(cache_key, data)
                return data
            return {"hits": [], "total_hits": 0, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"hits": [], "total_hits": 0, "error": str(e)}

    @classmethod
    def get_project_details(cls, id_or_slug: str) -> Optional[Dict[str, Any]]:
        if not id_or_slug:
            return None
        clean_target = id_or_slug.strip()
        cache_key = f"project:{clean_target}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            resp = cls.get_session().get(f"{MODRINTH_API_BASE}/project/{clean_target}", timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                cls._set_cache(cache_key, data)
                return data
        except Exception:
            pass
        return None

    @classmethod
    def get_project_versions(cls, id_or_slug: str, loaders: list = None, game_versions: list = None) -> List[Dict[str, Any]]:
        if not id_or_slug:
            return []
        clean_target = id_or_slug.strip()
        
        loaders_key = ",".join(sorted(loaders)) if loaders else ""
        gv_key = ",".join(sorted(game_versions)) if game_versions else ""
        cache_key = f"versions:{clean_target}:{loaders_key}:{gv_key}"
        
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached

        params = {}
        if loaders and isinstance(loaders, list) and len(loaders) > 0:
            params["loaders"] = json.dumps(loaders)
        if game_versions and isinstance(game_versions, list) and len(game_versions) > 0:
            params["game_versions"] = json.dumps(game_versions)

        try:
            resp = cls.get_session().get(f"{MODRINTH_API_BASE}/project/{clean_target}/version", params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    cls._set_cache(cache_key, data)
                    return data
        except Exception:
            pass
        return []

    @classmethod
    def get_user_profile(cls, user_id_or_username: str) -> Optional[Dict[str, Any]]:
        if not user_id_or_username:
            return None
        clean_target = user_id_or_username.strip()
        cache_key = f"user:{clean_target}"
        cached = cls._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            resp = cls.get_session().get(f"{MODRINTH_API_BASE}/user/{clean_target}", timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                cls._set_cache(cache_key, data)
                return data
        except Exception:
            pass
        return None

class ModrinthSearchWorker(QThread):
    results_ready = pyqtSignal(dict)

    def __init__(self, query: str, project_type: str, loader: str, version: str, sort_by: str, limit: int = 20, offset: int = 0):
        super().__init__()
        self.query = query
        self.project_type = project_type
        self.loader = loader
        self.version = version
        self.sort_by = sort_by
        self.limit = limit
        self.offset = offset

    def run(self):
        data = ModrinthAPI.search_projects(
            query=self.query,
            project_type=self.project_type,
            loader=self.loader,
            version=self.version,
            sort_by=self.sort_by,
            limit=self.limit,
            offset=self.offset
        )
        self.results_ready.emit(data)

class ModrinthAIRadarWorker(QThread):
    """Real-Time 0-Token AI Monitor detecting newly published projects on Modrinth as soon as they launch."""
    radar_detected = pyqtSignal(list, str)

    def __init__(self, poll_interval: int = 60):
        super().__init__()
        self.poll_interval = poll_interval
        self._running = True
        self._known_ids = set()
        self.logger = Logger.get_instance()

    def run(self):
        while self._running:
            try:
                newest_data = ModrinthAPI.search_projects(sort_by="newest", limit=15)
                updated_data = ModrinthAPI.search_projects(sort_by="updated", limit=15)

                hits = newest_data.get("hits", []) + updated_data.get("hits", [])
                seen = set()
                unique_hits = []
                for h in hits:
                    pid = h.get("project_id") or h.get("id") or h.get("slug")
                    if pid and pid not in seen:
                        seen.add(pid)
                        unique_hits.append(h)

                new_detections = []
                for item in unique_hits:
                    pid = item.get("project_id") or item.get("id") or item.get("slug")
                    if not self._known_ids:
                        self._known_ids.add(pid)
                    elif pid not in self._known_ids:
                        self._known_ids.add(pid)
                        new_detections.append(item)

                summary = ""
                if new_detections:
                    summary = f"AI Radar Alert: {len(new_detections)} fresh release(s) just launched on Modrinth!"
                else:
                    summary = f"AI Radar: Actively scanning Modrinth pipeline. {len(unique_hits)} live projects monitored."

                self.radar_detected.emit(unique_hits[:20], summary)
            except Exception as e:
                self.logger.warning(f"Modrinth AI Radar warning: {e}")

            for _ in range(self.poll_interval * 2):
                if not self._running:
                    break
                time.sleep(0.5)

    def stop(self):
        self._running = False

class ModrinthInstallWorker(QThread):
    """Installs mods, resourcepacks, shaders, plugins, datapacks, or converts modpack .mrpack files into working instances."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(
        self,
        file_url: str,
        file_name: str,
        target_type: str,
        target_folder_name: str,
        project_type: str,
        instance_mgr = None,
        server_mgr = None
    ):
        super().__init__()
        self.file_url = file_url
        self.file_name = file_name
        self.target_type = target_type
        self.target_folder_name = target_folder_name
        self.project_type = project_type.lower()
        self.instance_mgr = instance_mgr
        self.server_mgr = server_mgr
        self.logger = Logger.get_instance()

    def run(self):
        try:
            if self.target_type == "modpack_instance":
                self.progress.emit(10, f"Downloading modpack package '{self.file_name}'...")
                temp_dir = Path(tempfile.mkdtemp(prefix="mrpack_modrinth_"))
                temp_mrpack = temp_dir / self.file_name

                resp = requests.get(self.file_url, headers=HEADERS, stream=True, timeout=30)
                if resp.status_code != 200:
                    raise RuntimeError(f"Download failed with HTTP {resp.status_code}")

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                with open(temp_mrpack, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                pct = min(30, int(10 + (downloaded / total_size) * 20))
                                self.progress.emit(pct, f"Downloading modpack ({downloaded // 1024} KB / {total_size // 1024} KB)...")

                self.progress.emit(30, "Converting modpack into working game instance...")
                from neurax.core.mrpack import MRPackConverterWorker
                
                conv_success = [False]
                conv_msg = [""]

                def on_conv_prog(pct_val, status_str):
                    self.progress.emit(min(99, 30 + int(pct_val * 0.68)), status_str)

                def on_conv_fin(success_val, msg_val):
                    conv_success[0] = success_val
                    conv_msg[0] = msg_val

                converter = MRPackConverterWorker(
                    mrpack_path=str(temp_mrpack),
                    mode="instance",
                    instance_name=self.target_folder_name,
                    instance_mgr=self.instance_mgr
                )
                converter.progress.connect(on_conv_prog)
                converter.finished.connect(on_conv_fin)
                converter.run()

                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

                if not conv_success[0]:
                    raise RuntimeError(conv_msg[0] or "Modpack conversion failed.")

                self.progress.emit(100, f"Successfully created working instance '{self.target_folder_name}'!")
                msg = f"Successfully created working modpack instance '{self.target_folder_name}'!"
                self.logger.info(f"[Modrinth] {msg}")
                self.finished.emit(True, msg)
                return

            self.progress.emit(10, f"Preparing download for {self.file_name}...")

            if self.target_type == "instance":
                inst_data = self.instance_mgr.get_instance(self.target_folder_name) if self.instance_mgr else {}
                game_dir = Path(inst_data.get("game_dir", get_dot_neurax_dir() / "instances" / self.target_folder_name / ".minecraft"))
                
                # Auto-upgrade Vanilla instance loader to Fabric if installing mods
                current_loader = inst_data.get("loader", "Vanilla")
                if self.project_type in ("mod", "mods") and current_loader.lower() in ("vanilla", ""):
                    if self.instance_mgr:
                        self.instance_mgr.update_instance(self.target_folder_name, loader="Fabric")

                if self.project_type in ("mod", "mods"):
                    dest_dir = game_dir / "mods"
                elif self.project_type in ("resourcepack", "resourcepacks", "resource_pack"):
                    dest_dir = game_dir / "resourcepacks"
                elif self.project_type in ("shader", "shaders", "shaderpack", "shaderpacks"):
                    dest_dir = game_dir / "shaderpacks"
                elif self.project_type in ("datapack", "datapacks"):
                    dest_dir = game_dir / "saves" / "datapacks_staging"
                elif self.project_type in ("modpack", "modpacks"):
                    dest_dir = game_dir / "modpacks"
                else:
                    dest_dir = game_dir / "mods"

            elif self.target_type == "server":
                srv_data = self.server_mgr.get_server(self.target_folder_name) if self.server_mgr else {}
                srv_dir = Path(srv_data.get("server_dir", get_dot_neurax_dir() / "servers" / self.target_folder_name))
                
                if self.project_type in ("plugin", "plugins"):
                    dest_dir = srv_dir / "plugins"
                elif self.project_type in ("mod", "mods"):
                    dest_dir = srv_dir / "mods"
                elif self.project_type in ("datapack", "datapacks"):
                    dest_dir = srv_dir / "world" / "datapacks"
                else:
                    dest_dir = srv_dir / "plugins"
            else:
                raise ValueError(f"Invalid target type: {self.target_type}")

            dest_dir.mkdir(parents=True, exist_ok=True)
            target_file = dest_dir / self.file_name

            self.progress.emit(30, f"Downloading from Modrinth: {self.file_name}...")
            resp = requests.get(self.file_url, headers=HEADERS, stream=True, timeout=30)
            if resp.status_code != 200:
                raise RuntimeError(f"Download failed with HTTP {resp.status_code}")

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0

            with open(target_file, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = min(95, int(30 + (downloaded / total_size) * 65))
                            self.progress.emit(pct, f"Downloading {self.file_name} ({downloaded // 1024} KB / {total_size // 1024} KB)...")

            self.progress.emit(100, f"Successfully installed {self.file_name}!")
            msg = f"Successfully installed '{self.file_name}' to {self.target_type.title()} '{self.target_folder_name}'"
            self.logger.info(f"[Modrinth] {msg}")
            self.finished.emit(True, msg)

        except Exception as e:
            err_msg = f"Failed to install {self.file_name}: {e}"
            self.logger.error(f"[Modrinth Error] {err_msg}")
            self.finished.emit(False, err_msg)
