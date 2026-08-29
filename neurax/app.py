import sys
import os
import gc

if sys.platform == "win32":
    try:
        import asyncio
        import asyncio.windows_utils
        from asyncio.proactor_events import _ProactorBasePipeTransport

        _orig_del = _ProactorBasePipeTransport.__del__

        def _safe_del(self, *args, **kwargs):
            try:
                _orig_del(self, *args, **kwargs)
            except BaseException:
                pass

        _ProactorBasePipeTransport.__del__ = _safe_del

        _orig_fileno = asyncio.windows_utils.PipeHandle.fileno

        def _safe_fileno(self):
            try:
                return _orig_fileno(self)
            except (ValueError, OSError):
                return -1

        asyncio.windows_utils.PipeHandle.fileno = _safe_fileno
    except Exception:
        pass

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QMessageBox
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QIcon, QColor
from neurax.core.logger import Logger
from neurax.core.config import ConfigManager, get_icon_path
from neurax.core.instances import InstanceManager
from neurax.core.auth import AuthManager
from neurax.core.java_finder import JavaFinder
from neurax.core.versions import VersionManager
from neurax.gui.theme import ButtonHoverFilter, Theme
from neurax.gui.main_window import MainWindow

try:
    from users import update_users_file
except ImportError:
    update_users_file = None

class LoadingScreen(QWidget):
    def __init__(self, config: ConfigManager = None):
        super().__init__()
        self.config = config or ConfigManager()
        accent_color = self.config.get("accent_color", "#00F0FF")

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(500, 320)
        
        icon_path = get_icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        self.card = QFrame()
        self.card.setObjectName("LoadingCard")
        self.card.setStyleSheet(f"""
            QFrame#LoadingCard {{
                background-color: rgba(15, 15, 20, 0.95);
                border: 1.5px solid {accent_color};
                border-radius: 16px;
            }}
        """)
        
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(30, 30, 30, 30)
        card_layout.setSpacing(15)

        title = QLabel("NEURAX ENGINE")
        title.setStyleSheet("font-size: 24px; font-weight: 900; color: #FFFFFF; letter-spacing: 3px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        self.status_lbl = QLabel("Initializing core components...")
        self.status_lbl.setStyleSheet("color: #8A94A6; font-size: 13px;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.status_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 3px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {accent_color};
                border-radius: 3px;
            }}
        """)
        card_layout.addWidget(self.progress_bar)

        layout.addWidget(self.card)

        self.setWindowOpacity(0.0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_anim.setDuration(250)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_anim.start()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(10)
        self.step = 0

    def update_progress(self):
        self.step += 1
        self.progress_bar.setValue(self.step)
        if self.step == 20:
            self.status_lbl.setText("Scanning Java installations...")
        elif self.step == 40:
            self.status_lbl.setText("Fetching device and instance telemetry...")
            if update_users_file:
                try:
                    update_users_file()
                except Exception:
                    pass
        elif self.step == 50:
            self.status_lbl.setText("Verifying database index...")
        elif self.step == 80:
            self.status_lbl.setText("Launching NeuraX dashboard...")
        elif self.step >= 100:
            self.timer.stop()
            self.launch_main_window()

    def launch_main_window(self):
        config = self.config
        instance_mgr = InstanceManager(config.neurax_dir)
        auth_mgr = AuthManager(config)

        self.main_window = MainWindow(config, instance_mgr, auth_mgr)
        
        self.fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_out.setDuration(200)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.Type.InCubic)
        
        def on_faded():
            self.main_window.show()
            self.close()
            gc.collect()
            
        self.fade_out.finished.connect(on_faded)
        self.fade_out.start()

def main():
    logger = Logger.get_instance()
    logger.info("Starting NeuraX Launcher loading screen...")
    if update_users_file:
        try:
            update_users_file()
        except Exception:
            pass
    app = QApplication(sys.argv)
    
    icon_path = get_icon_path()
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    hover_filter = ButtonHoverFilter()
    app.installEventFilter(hover_filter)

    config = ConfigManager()
    loader = LoadingScreen(config)
    loader.show()

    return app.exec()
