import json
<<<<<<< HEAD
import logging
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
import requests
import time
import re
import threading
from pathlib import Path
from typing import List, Dict, Any
from PyQt6.QtCore import QObject, QThread, pyqtSignal

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
HEADERS = {
    "User-Agent": "NeuraX-MCL/4.0.0",
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache"
}

APRIL_FOOLS_IDS = {
    "24w14a", "23w13a_or_a", "22w13oneblockatATime", "20w14infinite",
    "1.14.4-Combat-3", "3D Shareware v1.34", "15w14a", "2.0"
}

def fetch_latest_loader_versions() -> Dict[str, str]:
    loaders = {
        "Fabric": "Latest",
        "Forge": "Latest",
        "NeoForge": "Latest",
        "Quilt": "Latest",
        "Paper": "Latest",
        "Purpur": "Latest"
    }
<<<<<<< HEAD

    # Try the disk-backed cache first so a slow or missing internet
    # connection still surfaces the last known loader versions. This
    # matches the same offline-tolerant pattern the version manifest
    # uses below. A separate ``loader_versions.json`` keeps loader
    # results isolated so a malformed Mojang cache never bleeds into
    # loader UI labels.
    try:
        from neurax.core.config import get_neurax_dir
        cache_file = get_neurax_dir() / "cache" / "loader_versions.json"
        if cache_file.exists():
            with cache_file.open("r", encoding="utf-8") as fh:
                cached = json.load(fh)
                if isinstance(cached, dict):
                    loaders.update({k: str(v) for k, v in cached.items() if v})
    except Exception:
        pass

    def _save():
        try:
            from neurax.core.config import get_neurax_dir
            cache_file = get_neurax_dir() / "cache" / "loader_versions.json"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_file.with_suffix(cache_file.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(loaders, fh, indent=2)
            import os
            os.replace(tmp, cache_file)
        except Exception:
            pass

=======
    
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    # 1. Fabric
    try:
        r = requests.get("https://meta.fabricmc.net/v2/versions/loader", headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                loaders["Fabric"] = str(data[0].get("version", "Latest"))
    except Exception:
        pass

    # 2. Quilt
    try:
        r = requests.get("https://meta.quiltmc.org/v2/versions/loader", headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                loaders["Quilt"] = str(data[0].get("version", "Latest"))
    except Exception:
        pass

    # 3. Paper
    try:
        r = requests.get("https://api.papermc.io/v2/projects/paper", headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json()
            versions = data.get("versions", [])
            if versions:
                loaders["Paper"] = str(versions[-1])
    except Exception:
        pass

    # 4. Purpur
    try:
        r = requests.get("https://api.purpurmc.org/v2/purpur", headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json()
            versions = data.get("versions", [])
            if versions:
                loaders["Purpur"] = str(versions[-1])
    except Exception:
        pass

    # 5. NeoForge
    try:
        r = requests.get("https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml", headers=HEADERS, timeout=4)
        if r.status_code == 200:
            matches = re.findall(r'<version>([^<]+)</version>', r.text)
            if matches:
                loaders["NeoForge"] = str(matches[-1])
    except Exception:
        pass

    # 6. Forge
    try:
        r = requests.get("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json", headers=HEADERS, timeout=4)
        if r.status_code == 200:
            data = r.json().get("promos", {})
            if "latest" in data:
                loaders["Forge"] = str(data["latest"])
            elif "1.20.4-latest" in data:
                loaders["Forge"] = str(data["1.20.4-latest"])
    except Exception:
        pass

<<<<<<< HEAD
    _save()
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    return loaders

class VersionMonitorThread(QThread):
    versions_updated = pyqtSignal(dict)

    def __init__(self, version_mgr: 'VersionManager', poll_interval: int = 300):
        super().__init__()
        self.version_mgr = version_mgr
        self.poll_interval = poll_interval
        self._running = True

    def run(self):
        while self._running:
            try:
                info = self.version_mgr.check_all_latest_versions()
                self.versions_updated.emit(info)
            except Exception:
                pass

            for _ in range(self.poll_interval * 2):
                if not self._running:
                    break
                time.sleep(0.5)

    def stop(self):
        self._running = False

class VersionManager(QObject):
    """Fetches, caches, and continuously monitors Mojang version manifests and loader APIs."""
    versions_updated = pyqtSignal(dict)
    _instance = None
    _lock = threading.Lock()
    _monitor_thread = None

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.cache_dir = cache_dir
        self.manifest_file = cache_dir / "version_manifest.json"
        self.latest_info = {}
        self.last_snapshot = ""
        self.last_release = ""

    @classmethod
    def get_instance(cls, cache_dir: Path = None):
        with cls._lock:
            if cls._instance is None:
                if cache_dir is None:
                    from neurax.core.config import get_neurax_dir
                    cache_dir = get_neurax_dir() / "cache"
                cls._instance = VersionManager(cache_dir)
            return cls._instance

    def start_monitoring(self, poll_interval: int = 300):
        if VersionManager._monitor_thread is None or not VersionManager._monitor_thread.isRunning():
            VersionManager._monitor_thread = VersionMonitorThread(self, poll_interval)
            VersionManager._monitor_thread.versions_updated.connect(self._on_monitor_updated)
            VersionManager._monitor_thread.start()

    def _on_monitor_updated(self, info: dict):
        self.latest_info = info
        self.versions_updated.emit(info)

    def check_all_latest_versions(self) -> Dict[str, Any]:
        manifest = self.fetch_manifest(force_refresh=False)
        latest_meta = manifest.get("latest", {})
        latest_release = latest_meta.get("release", "1.21.4")
        latest_snapshot = latest_meta.get("snapshot", "26.3-Snapshot.10")

        latest_af = "24w14a"
        for v in manifest.get("versions", []):
            v_id = v.get("id", "")
            v_id_lower = v_id.lower()
            if (
                v_id in APRIL_FOOLS_IDS or
                "april" in v_id_lower or
                "combat" in v_id_lower or
                "shareware" in v_id_lower or
                "oneblock" in v_id_lower or
                "infinite" in v_id_lower or
                v_id_lower.startswith("24w14") or
                v_id_lower.startswith("23w13") or
                v_id_lower.startswith("22w13") or
                v_id_lower.startswith("20w14") or
                v_id_lower.startswith("15w14")
            ):
                latest_af = v_id
                break

        loaders = fetch_latest_loader_versions()
        new_snapshot_detected = False
        if self.last_snapshot and self.last_snapshot != latest_snapshot:
            new_snapshot_detected = True
        self.last_snapshot = latest_snapshot
        self.last_release = latest_release

        info = {
            "latest_release": latest_release,
            "latest_snapshot": latest_snapshot,
            "latest_aprilfools": latest_af,
            "loaders": loaders,
            "new_snapshot_detected": new_snapshot_detected,
            "timestamp": int(time.time())
        }
        return info

    def fetch_manifest(self, force_refresh: bool = False) -> Dict[str, Any]:
        if not force_refresh and hasattr(self, "_cached_manifest") and self._cached_manifest is not None:
            return self._cached_manifest

        if not force_refresh and self.manifest_file.exists():
            try:
                if time.time() - self.manifest_file.stat().st_mtime < 3600:
                    with open(self.manifest_file, "r", encoding="utf-8") as f:
                        self._cached_manifest = json.load(f)
                        return self._cached_manifest
            except Exception:
                pass

        try:
            resp = requests.get(MANIFEST_URL, timeout=8, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()
            with open(self.manifest_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._cached_manifest = data
            return data
        except Exception as e:
<<<<<<< HEAD
            logging.getLogger("NeuraX").warning(f"[Versions] Network fetch failed ({e}). Using cached fallback.")
=======
            print(f"[Versions] Warning: Network fetch failed ({e}). Using cached fallback.")
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
            if self.manifest_file.exists():
                try:
                    with open(self.manifest_file, "r", encoding="utf-8") as f:
                        self._cached_manifest = json.load(f)
                        return self._cached_manifest
                except Exception:
                    pass
            fallback = {
                "latest": {"release": "26.2", "snapshot": "26.3-Snapshot.10"},
                "versions": [
                    {"id": "26.3-Snapshot.10", "type": "snapshot"},
                    {"id": "26.2", "type": "release"},
                    {"id": "26.1.2", "type": "release"},
                    {"id": "1.21.11", "type": "release"},
                    {"id": "1.20.4", "type": "release"},
                    {"id": "1.19.4", "type": "release"},
                    {"id": "1.16.5", "type": "release"},
                    {"id": "1.12.2", "type": "release"},
                    {"id": "1.8.9", "type": "release"}
                ]
            }
            self._cached_manifest = fallback
            return fallback

    def get_filtered_versions(
        self,
        show_releases: bool = True,
        show_snapshots: bool = False,
        show_beta: bool = False,
        show_alpha: bool = False,
        show_indev: bool = False,
        show_aprilfools: bool = False,
        show_historic: bool = False
    ) -> List[str]:
        manifest = self.fetch_manifest()
        results = []

        for v in manifest.get("versions", []):
            v_type = v.get("type", "")
            v_id = v.get("id", "")
            v_id_lower = v_id.lower()

            is_aprilfools = (
                v_id in APRIL_FOOLS_IDS or
                "april" in v_id_lower or
                "combat" in v_id_lower or
                "shareware" in v_id_lower or
                "oneblock" in v_id_lower or
                "infinite" in v_id_lower or
                v_id_lower.startswith("24w14") or
                v_id_lower.startswith("23w13") or
                v_id_lower.startswith("22w13") or
                v_id_lower.startswith("20w14") or
                v_id_lower.startswith("15w14")
            )
            is_indev = "indev" in v_id_lower or "infdev" in v_id_lower or v_id_lower.startswith("in-") or v_id_lower.startswith("inf-")
            is_alpha = v_type == "old_alpha" or v_id_lower.startswith("a1.") or v_id_lower.startswith("c0.")
            is_beta = v_type == "old_beta" or v_id_lower.startswith("b1.")
            is_snapshot = v_type == "snapshot" and not is_aprilfools and not is_indev
            is_release = v_type == "release" and not is_aprilfools
            is_historic = v_type in ("old_beta", "old_alpha") or v_id_lower.startswith("rd-") or v_id_lower.startswith("c0.")

            include = False
            if show_releases and is_release:
                include = True
            elif show_snapshots and is_snapshot:
                include = True
            elif show_beta and is_beta:
                include = True
            elif show_alpha and is_alpha:
                include = True
            elif show_indev and is_indev:
                include = True
            elif show_aprilfools and is_aprilfools:
                include = True
            elif show_historic and is_historic:
                include = True

            if include:
                results.append(v_id)

        return results if results else ["26.3-Snapshot.10", "26.2", "26.1.2", "1.21.11", "1.20.4", "1.19.4", "1.16.5", "1.12.2", "1.8.9"]
