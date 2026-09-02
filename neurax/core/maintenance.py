import os
import shutil
import zipfile
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from neurax.core.logger import Logger
from neurax.core.config import get_dot_neurax_dir


def is_valid_jar(file_path: Path | str) -> bool:
    p = Path(file_path)
    if not p.exists() or p.stat().st_size == 0:
        return False
    try:
        with zipfile.ZipFile(p, "r") as zf:
            return zf.testzip() is None
    except Exception:
        return False


class MaintenanceWorker(QThread):
    """Auto-repair and clean cache utility worker."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, neurax_dir: Path):
        super().__init__()
        self.neurax_dir = neurax_dir
        self.logger = Logger.get_instance()

    def run(self):
        try:
            self.progress.emit(10, "Starting maintenance scan...")
            cleaned_logs = 0
            cleaned_bytes = 0

            # 1. Clear .log and .log.gz files from instance folders
            self.progress.emit(25, "Cleaning log files from instances...")
            instances_dir = get_dot_neurax_dir() / "instances"
            if instances_dir.exists():
                for instance_folder in instances_dir.iterdir():
                    if instance_folder.is_dir():
                        logs_dir = instance_folder / ".minecraft" / "logs"
                        if logs_dir.exists():
                            for item in logs_dir.glob("*"):
                                if item.suffix in (".log", ".gz") or ".log" in item.name:
                                    try:
                                        cleaned_bytes += item.stat().st_size
                                        item.unlink()
                                        cleaned_logs += 1
                                    except Exception:
                                        pass

            # 2. Clear webcache and unlinked indexes
            self.progress.emit(50, "Cleaning webcache and temporary assets...")
            cache_dir = self.neurax_dir / "cache"
            webcache_dir = cache_dir / "webcache"
            if webcache_dir.exists():
                try:
                    shutil.rmtree(webcache_dir)
                except Exception:
                    pass

            # 3. Check & Repair corrupt/0KB client jars and libraries
            self.progress.emit(75, "Checking integrity of game libraries and version files...")
            repaired_files = 0
            
            for scan_dir in [self.neurax_dir, get_dot_neurax_dir()]:
                versions_dir = scan_dir / "versions"
                libraries_dir = scan_dir / "libraries"

                if versions_dir.exists():
                    for v_dir in versions_dir.iterdir():
                        if v_dir.is_dir():
                            for jar_file in v_dir.glob("*.jar"):
                                if not is_valid_jar(jar_file):
                                    try:
                                        jar_file.unlink()
                                        repaired_files += 1
                                    except Exception:
                                        pass

                if libraries_dir.exists():
                    for root, _, files in os.walk(libraries_dir):
                        for fname in files:
                            if fname.endswith(".jar"):
                                fpath = Path(root) / fname
                                if not is_valid_jar(fpath):
                                    try:
                                        fpath.unlink()
                                        repaired_files += 1
                                    except Exception:
                                        pass

            if instances_dir.exists():
                for instance_folder in instances_dir.iterdir():
                    if not instance_folder.is_dir():
                        continue
                    game_dir = instance_folder / ".minecraft"
                    versions_dir = game_dir / "versions"
                    libraries_dir = game_dir / "libraries"

                    if versions_dir.exists():
                        for v_dir in versions_dir.iterdir():
                            if v_dir.is_dir():
                                for jar_file in v_dir.glob("*.jar"):
                                    if not is_valid_jar(jar_file):
                                        try:
                                            jar_file.unlink()
                                            repaired_files += 1
                                        except Exception:
                                            pass

                    if libraries_dir.exists():
                        for root, _, files in os.walk(libraries_dir):
                            for fname in files:
                                if fname.endswith(".jar"):
                                    fpath = Path(root) / fname
                                    if not is_valid_jar(fpath):
                                        try:
                                            fpath.unlink()
                                            repaired_files += 1
                                        except Exception:
                                            pass

            self.progress.emit(100, "Maintenance complete!")
            cleaned_mb = cleaned_bytes / (1024 * 1024)
            msg = f"Cleaned {cleaned_logs} log files ({cleaned_mb:.2f} MB freed). Repaired {repaired_files} corrupt/invalid jar file(s)."
            self.logger.info(f"[Maintenance] {msg}")
            self.finished.emit(True, msg)
        except Exception as e:
            err_msg = f"Maintenance failed: {e}"
            self.logger.error(f"[Maintenance Error] {err_msg}")
            self.finished.emit(False, err_msg)
