import time
import requests
from typing import Dict, Any, List, Optional
from PyQt6.QtCore import QThread, pyqtSignal
from neurax.core.logger import Logger


def _fetch_latest_loader_versions(timeout: int = 6) -> Dict[str, str]:
    """Best-effort fetch of the newest available version for each loader.
    Returns a dict like {"fabric": "0.16.10", "quilt": "0.26.0",
    "forge": "1.20.4-49.0.30", "neoforge": "21.0.167"}. Missing keys mean
    the upstream call failed and the UI should keep the previous value."""
    out: Dict[str, str] = {}
    try:
        r = requests.get("https://meta.fabricmc.net/v2/versions/loader", timeout=timeout)
        if r.status_code == 200:
            data = r.json() or []
            if data:
                v = str(data[0].get("version", "")).strip()
                if v:
                    out["fabric"] = v
    except Exception:
        pass
    try:
        r = requests.get("https://meta.quiltmc.org/v2/versions/loader", timeout=timeout)
        if r.status_code == 200:
            data = r.json() or []
            if data:
                v = str(data[0].get("version", "")).strip()
                if v:
                    out["quilt"] = v
    except Exception:
        pass
    try:
        # Newest Forge: ask the maven feed for the last <version> entry.
        r = requests.get(
            "https://maven.minecraftforge.net/net/minecraftforge/forge/maven-metadata.xml",
            timeout=timeout,
        )
        if r.status_code == 200:
            versions = re.findall(r"<version>([^<]+)</version>", r.text)
            if versions:
                # maven-metadata is usually oldest->newest; take the tail.
                out["forge"] = str(versions[-1]).strip()
    except Exception:
        pass
    try:
        r = requests.get(
            "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml",
            timeout=timeout,
        )
        if r.status_code == 200:
            versions = re.findall(r"<version>([^<]+)</version>", r.text)
            if versions:
                out["neoforge"] = str(versions[-1]).strip()
    except Exception:
        pass
    return out


class AIVersionRadar:
    """
    Enhanced AI Version Radar & Release Pipeline Intelligence Engine.
    Monitors Mojang piston-meta for new releases, snapshots and loader readiness.
    Emits full version list diffs so the UI can auto-add new versions.
    """

    @staticmethod
    def calculate_stability_index(version_id: str, version_type: str) -> Dict[str, Any]:
        """Compute version stability score (0–100) and risk factors."""
        v_type = version_type.lower()
        vid_low = version_id.lower()

        if v_type == "release":
            stability = 100
            status = "Production Stable"
            risk = "None — Fully Tested Release"
        elif "rc" in vid_low:
            stability = 92
            status = "Release Candidate"
            risk = "Very Low — Final Testing Stage"
        elif "pre" in vid_low:
            stability = 82
            status = "Pre-Release"
            risk = "Low — Feature Complete, Bug Fixes Only"
        elif "snapshot" in v_type or re.match(r"^\d{2}w\d{2}\w$", vid_low):
            stability = 70
            status = "Weekly Snapshot"
            risk = "Medium — World Gen / Block Format Changes Possible"
        elif v_type in ("old_beta", "beta"):
            stability = 58
            status = "Legacy Beta"
            risk = "Low — Immutable Legacy Build"
        elif v_type in ("old_alpha", "alpha"):
            stability = 48
            status = "Legacy Alpha"
            risk = "Low — Immutable Historic Build"
        else:
            stability = 45
            status = "Special / Custom"
            risk = "Moderate — Non-Standard Features"

        return {
            "stability_index": stability,
            "status": status,
            "risk_assessment": risk
        }

    @staticmethod
    def check_loader_readiness(mc_version: str) -> Dict[str, str]:
        """Estimate loader availability status for a Minecraft version."""
        readiness = {}
        vid_low = mc_version.lower()

        # Fabric supports snapshots almost instantly
        readiness["Fabric"] = "Instant Support"

        # Quilt follows Fabric closely
        readiness["Quilt"] = "Near-Instant Support" if "." in mc_version else "Preview Compatible"

        # NeoForge/Forge typically lag behind by a few days on releases, preview on snapshots
        if re.match(r"^\d{2}w\d{2}\w$", vid_low) or "rc" in vid_low or "pre" in vid_low:
            readiness["NeoForge"] = "Preview / Experimental"
            readiness["Forge"] = "Pending"
        else:
            readiness["NeoForge"] = "Active Support"
            readiness["Forge"] = "Active Support"

        readiness["Paper"] = "Active Support" if "." in mc_version else "Preview Only"

        return readiness


# Keep re import for stability checks above
import re


class AIVersionRadarWorker(QThread):
    """
    Polling worker that monitors Mojang piston-meta every poll_interval seconds.
    Emits:
      - versions_updated(dict) — full radar info including new release/snapshot flags
      - new_version_detected(str, str) — (version_id, version_type) for auto-add to UI list
    """
    versions_updated = pyqtSignal(dict)
    new_version_detected = pyqtSignal(str, str)   # version_id, version_type

    def __init__(self, poll_interval: int = 300):
        super().__init__()
        self.poll_interval = poll_interval
        self._running = True
        self.logger = Logger.get_instance()
        self._last_snapshot: Optional[str] = None
        self._last_release: Optional[str] = None

    def run(self):
        while self._running:
            try:
                data = self._fetch_radar_info()
                if data:
                    self.versions_updated.emit(data)
            except Exception as e:
                self.logger.warning(f"AI Version Radar polling notice: {e}")

            for _ in range(self.poll_interval):
                if not self._running:
                    break
                time.sleep(1)

    def stop(self):
        self._running = False
        self.quit()

    def _fetch_radar_info(self) -> Dict[str, Any]:
        url = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            return {}

        manifest = res.json()
        latest = manifest.get("latest", {})
        latest_rel = latest.get("release", "1.21.4")
        latest_snap = latest.get("snapshot", "")

        # Detect new snapshot (only after first poll — avoids false alert on startup)
        is_new_snap = (self._last_snapshot is not None and latest_snap != self._last_snapshot)
        is_new_rel = (self._last_release is not None and latest_rel != self._last_release)

        if is_new_snap and latest_snap:
            self.logger.info(f"AI Version Radar: New snapshot detected — {latest_snap}")
            self.new_version_detected.emit(latest_snap, "snapshot")
        if is_new_rel and latest_rel:
            self.logger.info(f"AI Version Radar: New release detected — {latest_rel}")
            self.new_version_detected.emit(latest_rel, "release")

        self._last_snapshot = latest_snap
        self._last_release = latest_rel

        readiness = AIVersionRadar.check_loader_readiness(latest_rel)
        stability = AIVersionRadar.calculate_stability_index(latest_rel, "release")
        snap_stability = AIVersionRadar.calculate_stability_index(latest_snap, "snapshot") if latest_snap else {}
        loader_versions = _fetch_latest_loader_versions()

        return {
            "latest_release": latest_rel,
            "latest_snapshot": latest_snap,
            "latest_aprilfools": "24w14a",
            "new_snapshot_detected": is_new_snap,
            "new_release_detected": is_new_rel,
            "stability_index": stability["stability_index"],
            "release_status": stability["status"],
            "risk_assessment": stability["risk_assessment"],
            "snapshot_status": snap_stability.get("status", ""),
            "snapshot_stability": snap_stability.get("stability_index", 0),
            "loaders": readiness,
            "loader_versions": loader_versions,
            "timestamp": int(time.time())
        }


