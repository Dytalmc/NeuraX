import sys
import os
import gc
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QApplication, QFrame, QLabel, QPushButton
)
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup, QSize, QTimer
from neurax.gui.theme import Theme, create_monochrome_icon
from neurax.gui.widgets.nav_bar import NavBar
from neurax.gui.widgets.animated_stacked_widget import AnimatedStackedWidget
from neurax.gui.views.play_view import PlayView
from neurax.gui.views.instances_view import InstancesView
from neurax.gui.views.versions_view import VersionsView
from neurax.gui.views.servers_view import ServersView
from neurax.gui.views.modrinth_view import ModrinthView
from neurax.gui.views.skins_view import SkinsView
from neurax.gui.views.gallery_view import GalleryView
from neurax.gui.views.announcement_view import AnnouncementView
from neurax.gui.views.settings_view import SettingsView
from neurax.gui.views.new_server_view import NewServerView
from neurax.gui.views.afk_view import AFKView
from neurax.gui.widgets.lock_screen import LockScreenOverlay
from neurax.gui.widgets.status_bar import StatusBarWidget
from neurax.core.config import ConfigManager, get_icon_path
from neurax.core.instances import InstanceManager
from neurax.core.auth import AuthManager
from neurax.core.logger import Logger
from neurax.core.discord_rpc import DiscordManager

try:
    from users import CommunityView, CommunityClient, assemble_heartbeat_payload, get_users_config
    _USERS_OK = True
except Exception:
    CommunityView = None  # type: ignore
    CommunityClient = None  # type: ignore
    assemble_heartbeat_payload = None  # type: ignore
    get_users_config = None  # type: ignore
    _USERS_OK = False

class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager, auth_mgr: AuthManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.auth_mgr = auth_mgr
        self.logger = Logger.get_instance()

        # Initialize Discord RPC System
        DiscordManager.get_instance().initialize(self.config)

        self.setWindowTitle("NeuraX Launcher")
        icon_path = get_icon_path()
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        width = self.config.get("window_width", 1180)
        height = self.config.get("window_height", 1080)
        self.setMinimumSize(900, 600)
        self.resize(width, height)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint)

        # Smooth Window Opacity Fade-In Transition
        self.setWindowOpacity(0.0)
        self.fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade_in.setDuration(350)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_in.start()

        accent = self.config.get("accent_color", "#00F0FF")
        mode = self.config.get("theme_mode", "dark")

        # Apply global theme stylesheet
        qss = Theme.get_stylesheet(accent, mode)
        self.setStyleSheet(qss)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(qss)

        # Central Widget
        self.central_widget = QWidget()
        self.central_widget.setObjectName("centralWidget")
        self.setCentralWidget(self.central_widget)

        main_layout = QHBoxLayout(self.central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Left Nav Bar
        self.nav_bar = NavBar(self)
        self.nav_bar.set_theme_mode(mode)
        self.nav_bar.set_accent_color(accent)
        self.nav_bar.tab_changed.connect(self._on_tab_changed)
        self.nav_bar.community_chip_clicked.connect(self._open_community_view)
        main_layout.addWidget(self.nav_bar)

        # Right pane layout
        right_pane = QWidget()
        right_pane.setObjectName("rightPane")
        right_layout = QVBoxLayout(right_pane)
        right_layout.setContentsMargins(15, 15, 15, 15)
        right_layout.setSpacing(10)

        # Header Bar
        header_bar = QFrame()
        header_bar.setObjectName("HeaderBar")
        header_bar.setFixedHeight(50)
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(15, 0, 15, 0)
        header_layout.setSpacing(10)

        # Hamburger Button to toggle navigation bar
        self.toggle_nav_btn = QPushButton()
        self.toggle_nav_btn.setObjectName("NavToggleButton")
        self.toggle_nav_btn.setFixedSize(30, 30)
        self.toggle_nav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_nav_btn.setIcon(create_monochrome_icon("hamburger", Theme.get_icon_color(mode), QColor(accent)))
        self.toggle_nav_btn.setIconSize(QSize(20, 20))
        self.toggle_nav_btn.clicked.connect(self._toggle_nav_bar)
        header_layout.addWidget(self.toggle_nav_btn)

        self.title_lbl = QLabel("NeuraX Engine")
        self.title_lbl.setStyleSheet("font-weight: 800; font-size: 14px; letter-spacing: 1px;")
        header_layout.addWidget(self.title_lbl)
        header_layout.addStretch()

        # Bug Button to toggle PlayView console
        self.bug_btn = QPushButton()
        self.bug_btn.setObjectName("BugButton")
        self.bug_btn.setFixedSize(30, 30)
        self.bug_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bug_btn.setIcon(create_monochrome_icon("bug", Theme.get_icon_color(mode), QColor(accent)))
        self.bug_btn.setIconSize(QSize(20, 20))
        self.bug_btn.clicked.connect(self._toggle_console)
        header_layout.addWidget(self.bug_btn)

        right_layout.addWidget(header_bar)

        # Animated Stacked Widget for Views
        self.stacked_widget = AnimatedStackedWidget()
        right_layout.addWidget(self.stacked_widget, stretch=1)

        # Instantiate Views
        self.play_view = PlayView(self.config, self.instance_mgr, self.auth_mgr, self)
        self.instances_view = InstancesView(self.config, self.instance_mgr, self)
        self.versions_view = VersionsView(self.config, self.instance_mgr, self.auth_mgr, self)
        self.servers_view = ServersView(self.config, self.instance_mgr, self.auth_mgr, self, self)
        self.modrinth_view = ModrinthView(self.config, self.instance_mgr, self.auth_mgr, self, self)
        self.skins_view = SkinsView(self.config, self.auth_mgr, self)
        self.gallery_view = GalleryView(self.config, self.instance_mgr, self)
        self.announcement_view = AnnouncementView(self.config, self, self)
        self.settings_view = SettingsView(self.config, self.auth_mgr, self)
        self.new_server_view = NewServerView(self.config, self.auth_mgr, self)
        self.afk_view = AFKView(self.config, self)

        # Community view (optional — depends on users.py + PyQt6 being present)
        self.community_view = None
        if _USERS_OK and CommunityView is not None:
            try:
                self.community_view = CommunityView(self)
            except Exception:
                self.community_view = None

        # Add Views to Stacked Widget
        self.stacked_widget.addWidget(self.play_view)          # index 0
        self.stacked_widget.addWidget(self.instances_view)     # index 1
        self.stacked_widget.addWidget(self.versions_view)      # index 2
        self.stacked_widget.addWidget(self.servers_view)       # index 3
        self.stacked_widget.addWidget(self.modrinth_view)      # index 4
        self.stacked_widget.addWidget(self.skins_view)         # index 5
        self.stacked_widget.addWidget(self.gallery_view)       # index 6
        self.stacked_widget.addWidget(self.announcement_view)  # index 7
        self.stacked_widget.addWidget(self.settings_view)      # index 8
        self.stacked_widget.addWidget(self.new_server_view)    # index 9
        self.stacked_widget.addWidget(self.afk_view)           # index 10
        if self.community_view is not None:
            self.stacked_widget.addWidget(self.community_view) # index 11

        # Bottom Status/Progress Bar
        self.status_bar = StatusBarWidget(self.config)
        self.status_bar.setVisible(self.stacked_widget.currentIndex() == 0)
        right_layout.addWidget(self.status_bar)

        main_layout.addWidget(right_pane)

        self.config.config_changed.connect(self._on_config_changed)

        # Lock Screen Overlay
        self.lock_screen = LockScreenOverlay(self.config, self)
        self.lock_screen.setGeometry(self.rect())
        self._check_lock_state()

        # Check lock state timer to support telemetry lock toggle in real time
        self.lock_timer = QTimer(self)
        self.lock_timer.setInterval(1000)
        self.lock_timer.timeout.connect(self._poll_lock_file)
        self.lock_timer.start()

        # Community heartbeat — fire every 5 minutes so the device stays
        # "online" on the Supabase counters. The first beat is sent ~10s
        # after the window is shown, so the loading screen has time to
        # fade out and any UI work isn't blocked.
        self._heartbeat_timer = None
        if _USERS_OK and CommunityClient is not None and assemble_heartbeat_payload is not None:
            self._heartbeat_timer = QTimer(self)
            self._heartbeat_timer.setInterval(5 * 60 * 1000)
            self._heartbeat_timer.timeout.connect(self._send_heartbeat)
            self._heartbeat_timer.start()
            QTimer.singleShot(10_000, self._send_heartbeat)

    def enter_background_mode(self):
        self.hide()
        if hasattr(self, "announcement_view") and self.announcement_view:
            if hasattr(self.announcement_view, "timer") and self.announcement_view.timer:
                self.announcement_view.timer.stop()

        gc.collect()

        if sys.platform == "win32":
            try:
                import ctypes
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                ctypes.windll.psapi.EmptyWorkingSet(handle)
            except Exception:
                pass

    def exit_background_mode(self):
        self.show()
        if self.isMinimized():
            self.showNormal()
        self.activateWindow()
        self.raise_()

        if hasattr(self, "announcement_view") and self.announcement_view:
            if hasattr(self.announcement_view, "timer") and self.announcement_view.timer:
                self.announcement_view.timer.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "lock_screen"):
            self.lock_screen.setGeometry(self.rect())
        if not self.isMaximized() and not self.isMinimized():
            self.config.set("window_width", self.width())
            self.config.set("window_height", self.height())

    def closeEvent(self, event):
        # Mark our device as offline before tearing down — best effort,
        # never block the close on a network failure.
        try:
            self._mark_offline()
        except Exception:
            pass
        DiscordManager.get_instance().close()
        super().closeEvent(event)

    def _send_heartbeat(self):
        """Send one heartbeat + refresh the chip. Safe to call when offline."""
        if not _USERS_OK or CommunityClient is None or assemble_heartbeat_payload is None:
            return
        cfg = get_users_config() if get_users_config is not None else {}
        if cfg.get("offline_mode"):
            return
        client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
        if not client.is_configured():
            return
        try:
            payload = assemble_heartbeat_payload()
            client.send_heartbeat(payload)
        except Exception:
            pass
        # Refresh the chip + community view counters too.
        try:
            if self.nav_bar is not None and hasattr(self.nav_bar, "refresh_community_chip"):
                self.nav_bar.refresh_community_chip()
        except Exception:
            pass
        try:
            if self.community_view is not None and hasattr(self.community_view, "_on_refresh_clicked"):
                self.community_view._on_refresh_clicked()
        except Exception:
            pass

    def _mark_offline(self):
        if not _USERS_OK or CommunityClient is None or assemble_heartbeat_payload is None:
            return
        cfg = get_users_config() if get_users_config is not None else {}
        client = CommunityClient(cfg.get("supabase_url", ""), cfg.get("supabase_anon_key", ""))
        if not client.is_configured():
            return
        try:
            payload = assemble_heartbeat_payload()
            client.set_offline(payload.get("device_id", ""))
        except Exception:
            pass

    def _open_community_view(self):
        """Switch the stacked widget to the Community view (index 11)."""
        if self.community_view is None:
            return
        target = self.stacked_widget.indexOf(self.community_view)
        if target < 0:
            return
        # Re-use the same slide animation as the regular tab clicks.
        self.stacked_widget.slide_to_index(target)
        # Kick off a refresh as soon as the view is shown.
        try:
            if hasattr(self.community_view, "_on_refresh_clicked"):
                self.community_view._on_refresh_clicked()
        except Exception:
            pass

    def _toggle_nav_bar(self):
        self.nav_bar.setVisible(not self.nav_bar.isVisible())

    def _on_tab_changed(self, index: int):
        self.stacked_widget.slide_to_index(index)
        self.status_bar.setVisible(index == 0)
        DiscordManager.get_instance().on_tab_changed(index)

        if index == 7:
            self.announcement_view.mark_as_read()
        if index == 10:
            self.afk_view.reset_timer()
        if index == 11 and self.community_view is not None and hasattr(self.community_view, "_on_refresh_clicked"):
            try:
                self.community_view._on_refresh_clicked()
            except Exception:
                pass

    def _toggle_console(self):
        self.play_view.toggle_console()

    def _on_config_changed(self, key: str, value: object):
        if key == "launcher_locked":
            self._check_lock_state()
        elif key in ("accent_color", "theme_mode"):
            accent = self.config.get("accent_color", "#00F0FF")
            mode = self.config.get("theme_mode", "dark")
            
            qss = Theme.get_stylesheet(accent, mode)
            self.setStyleSheet(qss)
            app = QApplication.instance()
            if app:
                app.setStyleSheet(qss)

            self.nav_bar.set_theme_mode(mode)
            self.nav_bar.set_accent_color(accent)
            self.nav_bar.set_active_tab(self.stacked_widget.currentIndex())
            self.toggle_nav_btn.setIcon(create_monochrome_icon("hamburger", Theme.get_icon_color(mode), QColor(accent)))
            self.bug_btn.setIcon(create_monochrome_icon("bug", Theme.get_icon_color(mode), QColor(accent)))

    def _check_lock_state(self):
        locked = self.config.get("launcher_locked", False)
        if locked:
            self.lock_screen.show_locked()
        else: 
            self.lock_screen.hide_unlocked()

    def _poll_lock_file(self):
        try:
            cfg_path = self.config.config_path
            if cfg_path.exists():
                mtime = os.path.getmtime(cfg_path)
                if not hasattr(self, "_last_config_mtime") or mtime > getattr(self, "_last_config_mtime", 0):
                    self._last_config_mtime = mtime
                    self.config.load()
                    self._check_lock_state()
        except Exception:
            pass

    def quick_join(self, host: str, port: int):
        self.nav_bar._on_btn_clicked(0)
        self.play_view.launch_game(host, port)
