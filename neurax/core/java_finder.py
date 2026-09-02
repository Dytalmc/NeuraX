import os
import sys
import shutil
import subprocess
import re
from typing import List, Tuple

class JavaFinder:
    _cache = None
<<<<<<< HEAD
    # Per-path cache so repeated ``get_java_version`` calls (one per
    # candidate during launch) don't keep spawning ``java -version``.
    _version_cache: dict = {}

    @staticmethod
    def find_java_installations(force_refresh: bool = False) -> List[Tuple[str, str]]:
        if JavaFinder._cache is not None and not force_refresh:
=======

    @staticmethod
    def find_java_installations() -> List[Tuple[str, str]]:
        if JavaFinder._cache is not None:
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
            return JavaFinder._cache

        found = []
        seen_paths = set()

        def add_entry(name: str, path: str):
            if not path:
                return
            normalized = os.path.normpath(path)
            if normalized not in seen_paths and os.path.isfile(normalized):
                seen_paths.add(normalized)
                found.append((name, normalized))

        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            jh_exe = os.path.join(java_home, "bin", "java.exe" if sys.platform == "win32" else "java")
            if os.path.isfile(jh_exe):
                ver = JavaFinder.get_java_version(jh_exe)
                add_entry(f"JAVA_HOME ({ver})", jh_exe)

        sys_java = shutil.which("java")
        if sys_java:
            version_str = JavaFinder.get_java_version(sys_java)
            add_entry(f"System PATH Java ({version_str})", sys_java)

        if sys.platform == "win32":
            search_roots = [
                r"C:\Program Files\Java",
                r"C:\Program Files (x86)\Java",
                r"C:\Program Files\Eclipse Adoptium",
                r"C:\Program Files\Eclipse Foundation",
                r"C:\Program Files\Zulu",
                r"C:\Program Files\Amazon Corretto",
                r"C:\Program Files\BellSoft",
                r"C:\Program Files\Semeru",
                r"C:\Program Files\Microsoft",
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Common\Microsoft\JDK"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Eclipse Adoptium"),
                os.path.expandvars(r"%USERPROFILE%\.jdks"),
                os.path.expandvars(r"%USERPROFILE%\.cursor\jdks"),
                os.path.expandvars(r"%USERPROFILE%\.mcl\runtimes")
            ]
            for sroot in search_roots:
                if os.path.exists(sroot):
                    for root, dirs, files in os.walk(sroot):
                        depth = root[len(sroot):].count(os.sep)
                        if depth > 3:
                            dirs.clear()
                            continue
                        if "java.exe" in files and "bin" in root.lower():
                            exe = os.path.join(root, "java.exe")
                            ver = JavaFinder.get_java_version(exe)
                            parent_dir = os.path.basename(os.path.dirname(os.path.dirname(exe)))
                            add_entry(f"{parent_dir} ({ver})", exe)
                            dirs.clear()

        elif sys.platform == "darwin":
            mac_roots = ["/Library/Java/JavaVirtualMachines", os.path.expanduser("~/Library/Java/JavaVirtualMachines")]
            for mroot in mac_roots:
                if os.path.exists(mroot):
                    for root, dirs, files in os.walk(mroot):
                        depth = root[len(mroot):].count(os.sep)
                        if depth > 3:
                            dirs.clear()
                            continue
                        if "java" in files and "bin" in root:
                            exe = os.path.join(root, "java")
                            ver = JavaFinder.get_java_version(exe)
                            add_entry(f"macOS JVM ({ver})", exe)
                            dirs.clear()

        else:
            linux_roots = ["/usr/lib/jvm", "/usr/java", "/opt"]
            for lroot in linux_roots:
                if os.path.exists(lroot):
                    for root, dirs, files in os.walk(lroot):
                        depth = root[len(lroot):].count(os.sep)
                        if depth > 3:
                            dirs.clear()
                            continue
                        if "java" in files and "bin" in root:
                            exe = os.path.join(root, "java")
                            ver = JavaFinder.get_java_version(exe)
                            add_entry(f"Linux JVM ({ver})", exe)
                            dirs.clear()

        JavaFinder._cache = found
        return found

    @staticmethod
<<<<<<< HEAD
    def _probe_version_direct(java_exe: str) -> str:
        """Spawn ``java -version`` and read its output reliably.

        We deliberately do NOT use ``DETACHED_PROCESS`` here. Windows
        has a long-standing quirk where ``DETACHED_PROCESS`` detaches
        the child from any console allocation, which silently breaks
        ``subprocess.PIPE`` capture of the child's stderr on Java 8 /
        11 / 17 builds that write their version banner to stderr in a
        way that goes through the console subsystem. As a result the
        probe returns an empty bytes object, ``JavaFinder`` falls back
        to the literal string ``"Java"``, the major-version detector
        defaults to ``17``, and the launcher reports "Java 21 not
        found" even though Java 21 is sitting right there in
        ``C:\\Program Files\\Java\\jdk-21``.

        For ``java -version`` specifically we don't need
        ``DETACHED_PROCESS`` — the child lives for ~50 ms and exits
        before any console window can appear. ``CREATE_NO_WINDOW``
        alone is enough to prevent any flash.
        """
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            proc = subprocess.Popen(
                [java_exe, "-version"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
            try:
                out, _ = proc.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                return ""
            text = (out or b"").decode("utf-8", errors="ignore")
            for line in text.splitlines():
                if "version" in line.lower():
                    parts = line.split('"')
                    if len(parts) > 1 and parts[1].strip():
                        return parts[1].strip()
                    return line.strip()
            return ""
        except Exception:
            return ""

    @staticmethod
    def get_java_version(java_exe: str) -> str:
        # Per-path cache — ``launch_game`` calls this for every Java
        # candidate and ``java -version`` is ~50–100 ms each.
        cached = JavaFinder._version_cache.get(java_exe)
        if cached is not None:
            return cached
        ver = JavaFinder._probe_version_direct(java_exe)
        if not ver:
            ver = "Java"
        JavaFinder._version_cache[java_exe] = ver
        return ver
=======
    def get_java_version(java_exe: str) -> str:
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            res = subprocess.check_output([java_exe, "-version"], stderr=subprocess.STDOUT, timeout=2, creationflags=creationflags).decode("utf-8", errors="ignore")
            for line in res.splitlines():
                if "version" in line.lower():
                    parts = line.split('"')
                    return parts[1] if len(parts) > 1 else line.strip()
        except Exception:
            pass
        return "Java"
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    @staticmethod
    def get_java_major_version(java_exe: str) -> int:
        version_str = JavaFinder.get_java_version(java_exe)
<<<<<<< HEAD
        # Parse Java's quoted version banner: ``openjdk version "21.0.3" 2024-04-16``
        # ``version_str`` is the inner quoted text, so it never has the
        # "openjdk version" prefix; just match the first digit run.
        m = re.search(r'(\d+)', version_str)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, TypeError):
                pass
=======
        try:
            match = re.search(r'(\d+)(?:\.(\d+))?', version_str)
            if match:
                first = int(match.group(1))
                if first == 1 and match.group(2):
                    return int(match.group(2))
                return first
        except Exception:
            pass
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        return 17
