import os
<<<<<<< HEAD
=======
import sys
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
import logging
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from neurax.core.config import get_neurax_dir

<<<<<<< HEAD
_LOGGER_NAME = "NeuraX"


=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
class LogSignalEmitter(QObject):
    log_signal = pyqtSignal(str)

class Logger:
    _instance = None

    def __init__(self):
        self.neurax_dir = get_neurax_dir()
        self.logs_dir = self.neurax_dir / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        self.signal_emitter = LogSignalEmitter()
<<<<<<< HEAD

        self.logger = logging.getLogger(_LOGGER_NAME)
=======
        
        self.logger = logging.getLogger("NeuraX")
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.logger.setLevel(logging.INFO)
        
        # Prevent duplicate handlers if re-initialized
        if not self.logger.handlers:
            log_file = self.logs_dir / "launcher.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            
            formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S")
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
<<<<<<< HEAD

            # No StreamHandler(sys.stdout) — the launcher is built as a
            # windowed app and any stdout write can flash a console on
            # Windows. Everything we capture lives in launcher.log (and
            # in launcher-stdouterr.log for stray prints / tracebacks).
=======
            
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(formatter)
            self.logger.addHandler(stream_handler)
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = Logger()
        return cls._instance

    def info(self, msg: str):
        self.logger.info(msg)
        try:
            self.signal_emitter.log_signal.emit(f"[INFO] {msg}")
        except Exception:
            pass

    def warning(self, msg: str):
        self.logger.warning(msg)
        try:
            self.signal_emitter.log_signal.emit(f"[WARNING] {msg}")
        except Exception:
            pass

    def error(self, msg: str):
        self.logger.error(msg)
        try:
            self.signal_emitter.log_signal.emit(f"[ERROR] {msg}")
        except Exception:
            pass

    def user_action(self, action: str):
        msg = f"User Action: {action}"
        self.logger.info(msg)
        try:
            self.signal_emitter.log_signal.emit(f"[ACTION] {msg}")
        except Exception:
            pass

    def user_input(self, field: str, value):
        msg = f"User Input [{field}]: {value}"
        self.logger.info(msg)
        try:
            self.signal_emitter.log_signal.emit(f"[INPUT] {msg}")
        except Exception:
            pass
