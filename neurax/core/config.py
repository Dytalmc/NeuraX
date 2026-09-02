import json
import os
import sys
import ctypes
import subprocess
<<<<<<< HEAD
import logging
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal

def get_neurax_dir() -> Path:
    """Resolves cross-platform root storage folder 'neurax' in current user's AppData Roaming directory."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        base = Path.home()
    return base / "neurax"

def get_dot_neurax_dir() -> Path:
    """Resolves cross-platform root storage folder '.neurax' in current user's AppData Roaming directory."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    else:
        base = Path.home()
    return base / ".neurax"

<<<<<<< HEAD

def get_shared_libraries_dir() -> Path:
    """Shared library cache under `%APPDATA%/neurax/libraries`. All instances
    read loader JARs / assets from here so we never re-download the same
    file twice when multiple instances use the same loader version."""
    return get_neurax_dir() / "libraries"


def get_logo_dir() -> Path:
    """Centralised logo library under `%APPDATA%/neurax/logos/`.

    Every launcher surface (Discord RPC, window icon, tray, splash, splash
    hero, news thumbnails) should pull assets from here so the user can drop
    replacement art in one place and have it picked up automatically.
    """
    return get_neurax_dir() / "logos"


def get_discord_asset_dir() -> Path:
    """Cached copy of the assets we ship to Discord as `large_image` /
    `small_image`. Lives next to the logo dir but is owned by the Discord
    subsystem so custom logos in `get_logo_dir()` are not overwritten when
    the RPC layer refreshes its cache."""
    return get_neurax_dir() / "cache" / "discord_assets"


def _resolve_bundled_logo_candidates(filename: str):
    """Return an ordered list of absolute paths where a bundled copy of
    `filename` (e.g. `nx.ico`, `nx.png`) might be located, in priority
    order: PyInstaller bundle first, frozen exe dir next, then the on-disk
    project tree, then the cwd."""
    candidates = []

    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(sys._MEIPASS, "n2", filename))
        candidates.append(os.path.join(sys._MEIPASS, filename))

    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "n2", filename))
        candidates.append(os.path.join(exe_dir, filename))

    project_root = Path(__file__).resolve().parent.parent.parent
    candidates.append(str(project_root / "n2" / filename))
    candidates.append(str(project_root / filename))
    candidates.append(str(project_root / "neurax" / "gui" / "assets" / filename))

    candidates.append(os.path.abspath(os.path.join(os.getcwd(), "n2", filename)))
    candidates.append(os.path.abspath(os.path.join(os.getcwd(), filename)))

    return candidates


def seed_default_logos(force: bool = False):
    """On first launch, copy the bundled `nx.ico` / `nx.png` into
    `neurax/logos/` so the launcher always has at least one copy of its
    brand assets cached locally. After seeding, subsequent calls are
    no-ops unless `force=True`.

    Returns a dict mapping canonical name (`nx_ico`, `nx_png`) to the
    resolved path on disk (or `None` if no bundled copy was found).
    """
    import shutil

    logo_dir = get_logo_dir()
    logo_dir.mkdir(parents=True, exist_ok=True)

    seeds = {
        "nx_ico": "nx.ico",
        "nx_png": "nx.png",
    }
    resolved = {}
    for key, fname in seeds.items():
        target = logo_dir / fname
        if target.exists() and target.stat().st_size > 0 and not force:
            resolved[key] = str(target)
            continue
        for src in _resolve_bundled_logo_candidates(fname):
            if os.path.exists(src) and os.path.getsize(src) > 0:
                try:
                    shutil.copy2(src, target)
                    resolved[key] = str(target)
                    break
                except Exception:
                    continue
        else:
            resolved[key] = str(target) if target.exists() else None

    return resolved


def get_cached_logo_path(filename: str) -> str:
    """Return the absolute path of a logo file in `neurax/logos/`. If the
    file does not exist yet, seed it from the bundled asset and return
    the cached path. Returns an empty string if no source is available."""
    logo_dir = get_logo_dir()
    logo_dir.mkdir(parents=True, exist_ok=True)
    target = logo_dir / filename

    if target.exists() and target.stat().st_size > 0:
        return str(target)

    import shutil
    for src in _resolve_bundled_logo_candidates(filename):
        if os.path.exists(src) and os.path.getsize(src) > 0:
            try:
                shutil.copy2(src, target)
                return str(target)
            except Exception:
                continue

    return str(target) if target.exists() else ""


def get_logo_url(filename: str) -> str:
    """Return a `file://` URL for a cached logo so callers that need a
    URL-shaped string (e.g. Discord RPC `large_image`) can consume our
    local cache. Falls back to `file:///absolute/path` style."""
    p = get_cached_logo_path(filename)
    if not p:
        return ""
    p = p.replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + p

=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
def get_icon_path() -> str:
    """Resolves and caches nx.ico inside the user's AppData Roaming neurax cache folder.
    Ensures the main window and application always retrieve the icon directly from the cache folder.
    """
    neurax_dir = get_neurax_dir()
    cache_dir = neurax_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_icon = cache_dir / "nx.ico"

    candidates = []

    if hasattr(sys, '_MEIPASS'):
        candidates.append(os.path.join(sys._MEIPASS, "n2", "nx.ico"))
        candidates.append(os.path.join(sys._MEIPASS, "nx.ico"))

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "n2", "nx.ico"))
        candidates.append(os.path.join(exe_dir, "nx.ico"))

    project_root = Path(__file__).resolve().parent.parent.parent
    candidates.append(str(project_root / "n2" / "nx.ico"))
    candidates.append(str(project_root / "nx.ico"))

    candidates.append(os.path.abspath(os.path.join(os.getcwd(), "n2", "nx.ico")))
    candidates.append(os.path.abspath(os.path.join(os.getcwd(), "nx.ico")))

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, ".neurax", "n2", "nx.ico"))
        candidates.append(os.path.join(appdata, "neurax", "n2", "nx.ico"))

    if not cached_icon.exists() or cached_icon.stat().st_size == 0:
        for src in candidates:
            if os.path.exists(src) and os.path.getsize(src) > 0:
                try:
                    if sys.platform == "win32" and cached_icon.exists():
                        try:
                            ctypes.windll.kernel32.SetFileAttributesW(str(cached_icon), 0x80)
                        except Exception:
                            pass
                    import shutil
                    shutil.copy2(src, cached_icon)
                    break
                except Exception:
                    pass

    if cached_icon.exists() and sys.platform == "win32":
        try: 
            ctypes.windll.kernel32.SetFileAttributesW(str(cached_icon), 0x01)
        except Exception:
            pass

    return str(cached_icon)

def get_system_ram_info():
    """Detects installed total physical RAM and calculates allocable memory considering OS overhead."""
    total_mb = 16384
    try:
        if sys.platform == "win32":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_mb = int(stat.ullTotalPhys // (1024 * 1024))
        elif sys.platform == "darwin":
<<<<<<< HEAD
            try:
                from neurax.core._silent_proc import check_output_silent
                out = check_output_silent(["sysctl", "-n", "hw.memsize"], timeout=2)
            except Exception:
                out = b""
            total_mb = int(int(out.strip()) // (1024 * 1024)) if out else 0
=======
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], timeout=2)
            total_mb = int(int(out.strip()) // (1024 * 1024))
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        else:
            if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names and "SC_PHYS_PAGES" in os.sysconf_names:
                pagesize = os.sysconf("SC_PAGE_SIZE")
                physpages = os.sysconf("SC_PHYS_PAGES")
                total_mb = int((pagesize * physpages) // (1024 * 1024))
    except Exception:
        pass

    if sys.platform == "win32":
        os_overhead = max(2048, int(total_mb * 0.25))
    elif sys.platform == "darwin":
        os_overhead = max(2048, int(total_mb * 0.25))
    else:
        os_overhead = max(1024, int(total_mb * 0.15))

    max_allocable = max(1024, total_mb - os_overhead)
    max_allocable = (max_allocable // 256) * 256
    return total_mb, max_allocable

class ConfigManager(QObject):
    """Thread-safe, instant auto-saving configuration store."""
    config_changed = pyqtSignal(str, object)

    _total_ram, _max_allocable_ram = get_system_ram_info()

    _DEFAULT_CONFIG = {
        "accent_color": "#00F0FF",   # Cyan — default theme color
        "theme_mode": "dark",        # Default theme mode
        "selected_instance": "Default",
        "auth_mode": "microsoft",
        "username": "NeuraPlayer",
        "uuid": "00000000-0000-0000-0000-000000000000",
        "access_token": "0",
        "refresh_token": "",
        "ms_client_id": "",
        "ms_tenant": "consumers",
        "max_ram_mb": min(8192 if _total_ram >= 16384 else (6144 if _total_ram >= 12288 else 4096), _max_allocable_ram),
        "java_path": "auto",
        "jvm_args": "-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:MaxGCPauseMillis=20 -XX:+UnlockExperimentalVMOptions -XX:G1NewSizePercent=20 -XX:G1MaxNewSizePercent=40 -XX:G1ReservePercent=15 -XX:G1HeapWastePercent=5 -XX:G1MixedGCCountTarget=4 -XX:InitiatingHeapOccupancyPercent=45 -XX:G1MixedGCLiveThresholdPercent=90 -XX:G1RSetUpdatingPauseTimePercent=5 -XX:SurvivorRatio=8 -Dsun.rmi.dgc.client.gcInterval=3600000 -Dsun.rmi.dgc.server.gcInterval=3600000 -Djava.net.preferIPv4Stack=true -Dfile.encoding=UTF-8",
        "window_width": 1180,
        "window_height": 1080,
        "close_on_launch": False,
        "global_sync_enabled": False,
        "global_sync_settings": True,
        "global_sync_saves": True,
        "global_sync_servers": True,
        "global_sync_source": "auto",
        "global_sync_target": "all",
        "discord_rpc": True,
<<<<<<< HEAD
        "discord_client_id": "",
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        "discord_launcher_activity": True,
        "discord_mc_activity": True,
        "discord_show_version": True,
        "discord_show_loader": True,
        "discord_show_instance": True,
        "discord_show_server": True,
        "discord_show_time": True,
        "discord_show_private_servers": False,
        "discord_show_buttons": True,
        "discord_mode": "Full",
        "show_releases": True,
        "show_snapshots": False,
        "show_beta": False,
        "show_alpha": False,
        "show_indev": False,
        "show_aprilfools": False,
        "show_historic": False,
        "skin_model": "classic",
        "skin_second_layer": True,
        "custom_skin_path": "",
        "cape_enabled": False,
        "analytics": {},
        "servers": [],
        "modrinth_target_type": "Instance (Client)",
        "modrinth_target_instance": "",
        "modrinth_target_server": ""
    }

    def __init__(self, neurax_dir: Path = None):
        super().__init__()
        self.neurax_dir = neurax_dir or get_neurax_dir()
        self.config_file = self.neurax_dir / "config.json"
        self._config = {}
        self.ensure_dirs()
        self.load()

    def ensure_dirs(self):
<<<<<<< HEAD
        """Guarantees root filesystem architecture on boot.

        Persistent launcher state lives under `neurax/`:
            config.json, cache/, logs/, libraries/

        Per-instance game data lives under `.neurax/`:
            instances/, global/, servers/, screenshots/
        """
=======
        """Guarantees root filesystem architecture on boot."""
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.neurax_dir.mkdir(parents=True, exist_ok=True)
        get_dot_neurax_dir().mkdir(parents=True, exist_ok=True)
        (get_dot_neurax_dir() / "instances").mkdir(exist_ok=True)
        (get_dot_neurax_dir() / "global").mkdir(exist_ok=True)
        (get_dot_neurax_dir() / "global" / ".minecraft").mkdir(parents=True, exist_ok=True)
        (get_dot_neurax_dir() / "servers").mkdir(exist_ok=True)
<<<<<<< HEAD
        (get_dot_neurax_dir() / "screenshots").mkdir(exist_ok=True)
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        (self.neurax_dir / "cache").mkdir(exist_ok=True)
        (self.neurax_dir / "cache" / "skins").mkdir(exist_ok=True)
        (self.neurax_dir / "cache" / "capes").mkdir(exist_ok=True)
        (self.neurax_dir / "cache" / "icons").mkdir(exist_ok=True)
<<<<<<< HEAD
        (self.neurax_dir / "cache" / "discord_assets").mkdir(exist_ok=True)
        (self.neurax_dir / "logs").mkdir(exist_ok=True)
        # Shared loader library cache — populated lazily by the launcher and
        # referenced by every instance's classpath so re-installs across
        # instances never re-download the same JAR.
        (self.neurax_dir / "libraries").mkdir(exist_ok=True)
        # Centralised brand asset library. Discord RPC, splash screen,
        # window icon and tray all read from here so the user only needs
        # to drop replacement art in one folder.
        get_logo_dir().mkdir(exist_ok=True)
        get_discord_asset_dir().mkdir(parents=True, exist_ok=True)
        try:
            seed_default_logos()
        except Exception:
            pass
=======
        (self.neurax_dir / "logs").mkdir(exist_ok=True)
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        get_icon_path()

    def load(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._config = {**self._DEFAULT_CONFIG, **loaded}
                    jvm = str(self._config.get("jvm_args", ""))
                    if "AlwaysPreTouch" in jvm or "MaxTenuringThreshold=1" in jvm or "InitiatingHeapOccupancyPercent=15" in jvm or "allocator=system" in jvm:
                        self._config["jvm_args"] = self._DEFAULT_CONFIG["jvm_args"]
                        self.save()
            except Exception as e:
<<<<<<< HEAD
                logging.getLogger("NeuraX").error(f"[Config] Error reading config.json: {e}")
=======
                print(f"[Config] Error reading config.json: {e}")
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                self._config = dict(self._DEFAULT_CONFIG)
        else: 
            self._config = dict(self._DEFAULT_CONFIG)
            self.save()

    def save(self):
        """Instant atomic save to config.json."""
        try:
            temp_file = self.config_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2)
            try:
                temp_file.replace(self.config_file)
            except Exception:
                if self.config_file.exists():
                    self.config_file.unlink()
                temp_file.rename(self.config_file)
        except Exception as e:
<<<<<<< HEAD
            logging.getLogger("NeuraX").error(f"[Config] Save failed: {e}")
=======
            print(f"[Config] Save failed: {e}")
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    def get(self, key: str, default=None):
        return self._config.get(key, default if default is not None else self._DEFAULT_CONFIG.get(key))

    def set(self, key: str, value):
        if self._config.get(key) != value or key == "analytics":
            self._config[key] = value
            self.save()
            self.config_changed.emit(key, value)
