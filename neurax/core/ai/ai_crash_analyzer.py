import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class CrashDiagnosticResult:
    is_crash: bool
    title: str
    root_cause: str
    offending_component: str
    severity: str  # "CRITICAL", "WARNING", "INFO"
    solution_steps: List[str]
    raw_snippet: str


class AICrashAnalyzer:
    """Intelligent 0-Token Local Crash Diagnostic & Root-Cause Analysis Engine.
    Parses live Minecraft game output, crash-reports, and JVM exceptions to identify
    the exact offending mod, memory bottleneck, or driver mismatch with instant step-by-step fix recommendations.
    """

    @staticmethod
    def analyze_log(log_text: str) -> CrashDiagnosticResult:
        """Analyze text log or console stream for crash patterns and generate intelligent solutions."""
        if not log_text:
            return CrashDiagnosticResult(
                is_crash=False,
                title="No Crash Detected",
                root_cause="Log is clean.",
                offending_component="None",
                severity="INFO",
                solution_steps=["The game closed normally without fatal exceptions."],
                raw_snippet=""
            )

        # 1. Out of Memory Error (OOM)
        if "java.lang.OutOfMemoryError" in log_text or "out of memory" in log_text.lower():
            return CrashDiagnosticResult(
                is_crash=True,
                title="Java Out of Memory (OOM) Exhaustion",
                root_cause="The game process ran out of allocated RAM heap space while loading mods/textures.",
                offending_component="JVM Memory Allocation",
                severity="CRITICAL",
                solution_steps=[
                    "Open Launcher Settings or Instance Settings.",
                    "Increase the Memory Allocation slider (recommended: 4096MB - 6144MB).",
                    "Close heavy background applications (browser tabs, video editors) to free system RAM.",
                    "If using 50+ mods, consider installing lightweight optimization mods (e.g. FerriteCore, ModernFix)."
                ],
                raw_snippet="java.lang.OutOfMemoryError: Java heap space"
            )

        # 2. Java Version Class Version Mismatch (e.g. Java 8 trying to run Java 17/21 bytecode)
        if "UnsupportedClassVersionError" in log_text:
            match = re.search(r'class file version (\d+)\.\d+', log_text)
            ver_num = match.group(1) if match else "modern"
            java_map = {"52": "Java 8", "60": "Java 16", "61": "Java 17", "65": "Java 21", "69": "Java 25"}
            req_java = java_map.get(ver_num, "Java 17/21")

            return CrashDiagnosticResult(
                is_crash=True,
                title="Java Runtime Version Mismatch",
                root_cause=f"Minecraft or an installed mod requires {req_java} or newer, but an older Java version was used.",
                offending_component="Java Runtime Executable",
                severity="CRITICAL",
                solution_steps=[
                    f"Navigate to Launcher Settings -> Java Settings.",
                    f"Select '{req_java}' or set to 'Auto Detect (System Default)'.",
                    f"If you do not have {req_java} installed, install Microsoft OpenJDK 21 or Eclipse Adoptium Temurin."
                ],
                raw_snippet="java.lang.UnsupportedClassVersionError"
            )

        # 3. Fabric Mixin Injection / Mod Conflict
        if "org.spongepowered.asm.mixin" in log_text or "MixinTransformerError" in log_text:
            mod_match = re.search(r'(?:in plugin|from mod)\s+([a-zA-Z0-9_\.-]+)', log_text, re.IGNORECASE)
            offending_mod = mod_match.group(1) if mod_match else "Incompatible Mod"

            return CrashDiagnosticResult(
                is_crash=True,
                title=f"Fabric Mixin Transformation Failure ({offending_mod})",
                root_cause=f"Mod '{offending_mod}' failed to inject its mixin code into the game engine due to an incompatibility with your Minecraft or Fabric API version.",
                offending_component=offending_mod,
                severity="CRITICAL",
                solution_steps=[
                    f"Check if '{offending_mod}' has an update for your exact Minecraft version on Modrinth.",
                    "Verify that the Fabric API mod matches your exact Minecraft version.",
                    "Temporarily remove or disable this mod from your instance 'mods' folder to verify stability."
                ],
                raw_snippet="org.spongepowered.asm.mixin.transformer.throwables.MixinTransformerError"
            )

        # 4. Forge / NeoForge Missing Dependency
        if "ModLoadingException" in log_text or "MissingMandatoryDependenciesException" in log_text or "requires" in log_text.lower() and "which is missing" in log_text.lower():
            dep_match = re.search(r'requires\s+([a-zA-Z0-9_\.-]+)', log_text)
            missing_dep = dep_match.group(1) if dep_match else "Required Library Mod"

            return CrashDiagnosticResult(
                is_crash=True,
                title=f"Missing Mod Dependency ({missing_dep})",
                root_cause=f"One of your installed mods requires '{missing_dep}' to load, but it was not found in your mods directory.",
                offending_component=missing_dep,
                severity="CRITICAL",
                solution_steps=[
                    f"Open Modrinth Hub in NeuraX.",
                    f"Search and download '{missing_dep}' for your loader and game version.",
                    "Place the downloaded JAR into your instance 'mods' folder and relaunch."
                ],
                raw_snippet="net.minecraftforge.fml.ModLoadingException: Missing dependency"
            )

        # 5. OpenGL / Graphics Driver Crash
        if "GLFW" in log_text or "LWJGLException" in log_text or "WGL:" in log_text or "Pixel format not accelerated" in log_text:
            return CrashDiagnosticResult(
                is_crash=True,
                title="OpenGL Graphics Display Initialization Failure",
                root_cause="The game window could not be created because your GPU display driver does not support the required OpenGL context.",
                offending_component="GPU Display Driver / Shader Engine",
                severity="CRITICAL",
                solution_steps=[
                    "Update your Graphics Card drivers (NVIDIA GeForce, AMD Radeon, or Intel Arc/UHD).",
                    "If using multiple GPUs (e.g. laptop with integrated + dedicated GPU), ensure Minecraft runs on High Performance GPU in Windows Graphics Settings.",
                    "If using shaderpacks, remove incompatible custom shaders from the 'shaderpacks' folder."
                ],
                raw_snippet="org.lwjgl.LWJGLException: Pixel format not accelerated"
            )

        # 6. Generic Exception Detection
        ex_match = re.search(r'([a-zA-Z0-9_.]+(?:Exception|Error)):\s*(.*)', log_text)
        if ex_match:
            ex_name = ex_match.group(1)
            ex_msg = ex_match.group(2)[:120]
            return CrashDiagnosticResult(
                is_crash=True,
                title=f"Game Exception: {ex_name}",
                root_cause=ex_msg or f"An unhandled {ex_name} occurred during execution.",
                offending_component="Game Process",
                severity="WARNING",
                solution_steps=[
                    "Check the Diagnostic Output Console for the complete error stack trace.",
                    "Verify that your mod versions match the active instance Minecraft version.",
                    "Run 'Performance Mode: Clean & Repair' in Launcher Settings."
                ],
                raw_snippet=f"{ex_name}: {ex_msg}"
            )

        return CrashDiagnosticResult(
            is_crash=False,
            title="Clean Execution State",
            root_cause="No recognized crash signatures found.",
            offending_component="None",
            severity="INFO",
            solution_steps=["Game process is operational."],
            raw_snippet=""
        )

    @staticmethod
    def analyze_latest_crash_report(game_dir: Path) -> Optional[CrashDiagnosticResult]:
        """Scan instance crash-reports directory for latest crash dump."""
        crash_dir = game_dir / "crash-reports"
        if not crash_dir.exists():
            return None

        files = list(crash_dir.glob("crash-*.txt"))
        if not files:
            return None

        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_file = files[0]

        try:
            with open(latest_file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            res = AICrashAnalyzer.analyze_log(content)
            return res
        except Exception:
            return None
