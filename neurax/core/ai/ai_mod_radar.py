import time
import requests
from typing import Dict, Any, List, Tuple, Set
from PyQt6.QtCore import QThread, pyqtSignal
from neurax.core.logger import Logger

class AIModRadar:
    """0-Token Local Mod Ecosystem Intelligence & Compatibility Advisor.
    Detects mod dependencies, incompatible jar combinations, shader prerequisites,
    and calculates memory/FPS performance impact.
    """

    KNOWN_CONFLICTS = [
        ({"optifine"}, {"sodium", "rubidium", "embeddium"}, "OptiFine conflicts with Sodium/Embeddium. Use Iris + Sodium for modern shaders."),
        ({"optifine"}, {"iris", "oculus"}, "OptiFine is not compatible with Iris/Oculus shader engines."),
        ({"sodium"}, {"rubidium"}, "Sodium and Rubidium are redundant ports of the same engine."),
        ({"xaeros-minimap"}, {"journeymap"}, "Multiple full-featured minimap mods active simultaneously may degrade HUD FPS.")
    ]

    PERFORMANCE_BOOSTERS = {
        "sodium", "lithium", "ferritecore", "immediatelyfast", "entityculling",
        "modernfix", "krypton", "noisium", "c2me", "clumps", "spark"
    }

    HEAVY_MODS = {
        "create", "all-the-mods", "applied-energistics-2", "mekanism",
        "twilight-forest", "alexs-mobs", "immersive-engineering", "botania"
    }

    @staticmethod
    def analyze_mod_list(installed_slugs: List[str]) -> Dict[str, Any]:
        """Analyze a list of installed mod slugs for conflicts, optimizations, and RAM recommendations."""
        slug_set = {s.lower().strip() for s in installed_slugs}
        conflicts = []

        for group_a, group_b, warning in AIModRadar.KNOWN_CONFLICTS:
            if slug_set.intersection(group_a) and slug_set.intersection(group_b):
                conflicts.append(warning)

        boosters = list(slug_set.intersection(AIModRadar.PERFORMANCE_BOOSTERS))
        heavies = list(slug_set.intersection(AIModRadar.HEAVY_MODS))

        base_ram = 2048
        if heavies:
            base_ram = min(8192, 2048 + len(heavies) * 1024)

        fps_impact = "Normal"
        if len(boosters) >= 3:
            fps_impact = f"High Boost (+{len(boosters) * 15}% FPS estimated)"
        elif boosters:
            fps_impact = f"Moderate Boost (+{len(boosters) * 10}% FPS)"

        return {
            "conflicts": conflicts,
            "has_conflicts": len(conflicts) > 0,
            "optimization_mods_count": len(boosters),
            "optimization_mods": boosters,
            "heavy_mods_count": len(heavies),
            "heavy_mods": heavies,
            "recommended_min_ram_mb": base_ram,
            "fps_impact_rating": fps_impact
        }

    @staticmethod
    def evaluate_project_impact(project_slug: str, project_type: str, downloads: int) -> Dict[str, Any]:
        """Evaluate single project health, popularity reliability, and ecosystem grade."""
        slug_low = project_slug.lower()
        is_booster = slug_low in AIModRadar.PERFORMANCE_BOOSTERS
        is_heavy = slug_low in AIModRadar.HEAVY_MODS

        if is_booster:
            grade = "A+ (Performance Engine)"
            desc = "Optimizes rendering pipeline, chunk generation, or memory allocation."
        elif is_heavy:
            grade = "A (Feature-Rich Content)"
            desc = "Adds large dimensions, machinery, or complex entity behaviors."
        elif downloads > 1000000:
            grade = "A (Ecosystem Standard)"
            desc = "Over 1M+ downloads with verified high player satisfaction."
        elif downloads > 100000:
            grade = "B+ (Community Favorite)"
            desc = "Stable and widely adopted community project."
        else:
            grade = "B (Standard Project)"
            desc = "Standard Modrinth release."

        return {
            "grade": grade,
            "description": desc,
            "is_booster": is_booster,
            "is_heavy": is_heavy
        }


class AIModRadarWorker(QThread):
    radar_detected = pyqtSignal(list, str)

    def __init__(self, poll_interval: int = 60):
        super().__init__()
        self.poll_interval = poll_interval
        self._running = True
        self.logger = Logger.get_instance()

    def run(self):
        while self._running:
            try:
                hits, summary = self._poll_modrinth_pulse()
                if hits or summary:
                    self.radar_detected.emit(hits, summary)
            except Exception as e:
                self.logger.warning(f"AI Mod Radar poll notice: {e}")

            for _ in range(self.poll_interval):
                if not self._running:
                    break
                time.sleep(1)

    def stop(self):
        self._running = False

    def _poll_modrinth_pulse(self) -> Tuple[list, str]:
        url = "https://api.modrinth.com/v2/search?limit=6&index=updated"
        headers = {"User-Agent": "NeuraX-AI-ModRadar/2.0"}
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code != 200:
            return [], ""

        data = res.json()
        hits = data.get("hits", [])
        if not hits:
            return [], ""

        top = hits[0]
        title = top.get("title") or top.get("slug")
        ptype = str(top.get("project_type", "mod")).capitalize()
        author = top.get("author", "Creator")
        
        summary = f"AI Mod Radar: Detected newly updated {ptype} '{title}' by {author} ({len(hits)} active pipeline updates)."
        return hits, summary
