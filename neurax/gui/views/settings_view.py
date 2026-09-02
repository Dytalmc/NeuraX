import time
import webbrowser
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QMessageBox, QDialog, QApplication, QFileDialog, QScrollArea, QProgressBar, QGridLayout, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.widgets.ram_slider import RamSlider
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager, get_system_ram_info
from neurax.core.auth import AuthManager
from neurax.core.instances import InstanceManager
from neurax.core.java_finder import JavaFinder
from neurax.core.maintenance import MaintenanceWorker
from neurax.core.logger import Logger
from neurax.core.discord_rpc import DiscordManager
from neurax.gui.theme import Theme


class MSAuthWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, auth_mgr: AuthManager, url_or_code: str):
        super().__init__()
        self.auth_mgr = auth_mgr
        self.url_or_code = url_or_code

    def run(self):
        try:
            res = self.auth_mgr.complete_login_with_url(self.url_or_code)
            username = res.get("username", "Player")
            self.finished.emit(True, f"Successfully logged in as {username}!")
        except Exception as e:
            self.finished.emit(False, str(e))


class MSAuthDialog(QDialog):
    def __init__(self, parent, auth_mgr: AuthManager):
        super().__init__(parent)
        self.auth_mgr = auth_mgr
        self.logger = Logger.get_instance()
        self.worker = None
        self.setWindowTitle("Microsoft Account Authentication")
        self.resize(500, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info_lbl = QLabel(
            "<b>Step 1:</b> Click the button below to sign in with your Microsoft account in your browser.<br>"
            "<b>Step 2:</b> After logging in, copy the full URL from your browser's address bar and paste it below."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("font-size: 13px;")
        layout.addWidget(info_lbl)

        self.link_btn = QPushButton(" 1. Open Microsoft Login Page")
        self.link_btn.setObjectName("PrimaryButton")
        self.link_btn.setIcon(IconEngine.get_icon("globe", QColor("#FFFFFF"), QColor("#FFFFFF"), 16))
        self.link_btn.setIconSize(QSize(16, 16))
        self.link_btn.clicked.connect(self._open_browser)
        layout.addWidget(self.link_btn)

        layout.addWidget(QLabel("<b>Step 3:</b> Paste Redirected URL / Auth Code:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://login.live.com/oauth20_desktop.srf?code=...")
        layout.addWidget(self.url_input)

        self.login_btn = QPushButton(" Complete Microsoft Login")
        self.login_btn.setObjectName("PrimaryButton")
        self.login_btn.setIcon(IconEngine.get_icon("shield", QColor("#FFFFFF"), QColor("#FFFFFF"), 16))
        self.login_btn.setIconSize(QSize(16, 16))
        self.login_btn.clicked.connect(self._start_complete_login)
        layout.addWidget(self.login_btn)

        self.status_lbl = QLabel("Ready to authenticate.")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet("font-size: 12px; font-style: italic;")
        layout.addWidget(self.status_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _open_browser(self):
        try:
            login_url = self.auth_mgr.get_login_url()
            self.logger.user_action("Opened Microsoft auth link in browser")
            webbrowser.open(login_url)
            self.status_lbl.setText("Browser opened. Sign in and paste the redirected URL above.")
        except Exception as e:
            self.status_lbl.setText(f"Error opening browser: {e}")

    def _start_complete_login(self):
        url_text = self.url_input.text().strip()
        if not url_text:
            QMessageBox.warning(self, "Input Required", "Please paste the redirected URL or code from your browser.")
            return

        self.login_btn.setEnabled(False)
        self.link_btn.setEnabled(False)
        self.status_lbl.setText("Authenticating with Microsoft & Minecraft services...")

        self.worker = MSAuthWorker(self.auth_mgr, url_text)
        self.worker.finished.connect(self._on_auth_finished)
        self.worker.start()

    def _on_auth_finished(self, success: bool, msg: str):
        self.login_btn.setEnabled(True)
        self.link_btn.setEnabled(True)
        if success:
            self.logger.info(f"Microsoft Authentication finished: {msg}")
            self.status_lbl.setText("Authentication successful!")
            QMessageBox.information(self, "Microsoft Auth", msg)
            self.accept()
        else:
            self.logger.error(f"Microsoft Authentication failed: {msg}")
            self.status_lbl.setText("Authentication failed.")
            QMessageBox.critical(self, "Microsoft Auth Error", msg)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait(500)
        super().closeEvent(event)


class SettingsView(QWidget):
    """Launcher Settings View: Appearance & Theme Mode, Memory allocation, Java runtime, Maintenance, Global Sync, and Authentication."""

    def __init__(self, config: ConfigManager, auth_mgr: AuthManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.auth_mgr = auth_mgr
        self.logger = Logger.get_instance()
        self.instance_mgr = InstanceManager(self.config.neurax_dir)

        total_mb, max_allocable = get_system_ram_info()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Launcher Settings")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        main_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(15)

        card = GlassCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(25, 25, 25, 25)
        card_layout.setSpacing(18)

        # 1. Appearance & Theme Mode Section
        appear_lbl = QLabel("Appearance & Theme Engine")
        appear_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        card_layout.addWidget(appear_lbl)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(12)

        current_mode = self.config.get("theme_mode", "dark")
        accent = self.config.get("accent_color", "#00F0FF")

        self.dark_mode_btn = QPushButton(" Dark Mode")
        self.dark_mode_btn.setObjectName("ModeButton")
        self.dark_mode_btn.setIcon(IconEngine.get_icon("moon", QColor("#FFFFFF"), QColor(accent), 16))
        self.dark_mode_btn.setIconSize(QSize(16, 16))
        self.dark_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dark_mode_btn.setProperty("active", "true" if current_mode == "dark" else "false")
        self.dark_mode_btn.clicked.connect(lambda: self._set_theme_mode("dark"))
        mode_row.addWidget(self.dark_mode_btn)

        self.light_mode_btn = QPushButton(" Light Mode")
        self.light_mode_btn.setObjectName("ModeButton")
        self.light_mode_btn.setIcon(IconEngine.get_icon("sun", QColor("#1E293B"), QColor(accent), 16))
        self.light_mode_btn.setIconSize(QSize(16, 16))
        self.light_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.light_mode_btn.setProperty("active", "true" if current_mode == "light" else "false")
        self.light_mode_btn.clicked.connect(lambda: self._set_theme_mode("light"))
        mode_row.addWidget(self.light_mode_btn)

        mode_row.addStretch()
        card_layout.addLayout(mode_row)

        # Accent Theme Colors
        theme_lbl = QLabel("Theme Accent Color:")
        theme_lbl.setStyleSheet("font-weight: 600; margin-top: 4px;")
        card_layout.addWidget(theme_lbl)

        color_row = QHBoxLayout()
        self.accent_buttons = {}
        current_accent_name = self.config.get("theme_accent", "Cyan")
        for color_name, color_hex in Theme.ACCENTS.items():
            btn = QPushButton(f" {color_name}")
            btn.setObjectName("SecondaryButton")
            btn.setIcon(IconEngine.get_icon("palette", QColor(color_hex), QColor(color_hex), 14))
            btn.setIconSize(QSize(14, 14))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", "true" if color_name == current_accent_name else "false")
            btn.clicked.connect(lambda checked, h=color_hex, n=color_name: self._set_theme_color(n, h))
            color_row.addWidget(btn)
            self.accent_buttons[color_name] = btn
        color_row.addStretch()
        card_layout.addLayout(color_row)

        # 2. Account Section
        acc_lbl = QLabel("Account & Authentication")
        acc_lbl.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        card_layout.addWidget(acc_lbl)

        acc_row = QHBoxLayout()
        username = self.config.get("username", "Not Logged In")
        token = self.config.get("access_token", "0")
        is_logged_in = (token != "0" and self.config.get("auth_mode") == "microsoft")
        status_text = f"Logged in as: {username}" if is_logged_in else "Not Logged In (Microsoft Account Required)"
        self.account_status_lbl = QLabel(status_text)
        self.account_status_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        acc_row.addWidget(self.account_status_lbl, stretch=2)

        ms_login_btn = QPushButton(" Login with Microsoft")
        ms_login_btn.setObjectName("PrimaryButton")
        ms_login_btn.setIcon(IconEngine.get_icon("shield", QColor("#FFFFFF"), QColor("#FFFFFF"), 16))
        ms_login_btn.setIconSize(QSize(16, 16))
        ms_login_btn.clicked.connect(self._ms_login)
        acc_row.addWidget(ms_login_btn)
        card_layout.addLayout(acc_row)

        # 3. Global Directory Sync Section
        global_sync_lbl = QLabel("Global Instance Sync")
        global_sync_lbl.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        card_layout.addWidget(global_sync_lbl)

        self.global_sync_cb = QCheckBox("Auto-sync instances before Launch")
        self.global_sync_cb.setChecked(self.config.get("global_sync_enabled", False))
        self.global_sync_cb.toggled.connect(self._on_global_sync_toggled)
        card_layout.addWidget(self.global_sync_cb)

        # HOW: Items to Sync
        how_lbl = QLabel("Customize Content (HOW):")
        how_lbl.setStyleSheet("font-weight: 600; margin-top: 4px;")
        card_layout.addWidget(how_lbl)

        items_row = QHBoxLayout()
        self.sync_settings_cb = QCheckBox("Settings (options.txt)")
        self.sync_settings_cb.setChecked(self.config.get("global_sync_settings", True))
        self.sync_settings_cb.toggled.connect(lambda val: self.config.set("global_sync_settings", val))
        items_row.addWidget(self.sync_settings_cb)

        self.sync_saves_cb = QCheckBox("Saves (world folders)")
        self.sync_saves_cb.setChecked(self.config.get("global_sync_saves", True))
        self.sync_saves_cb.toggled.connect(lambda val: self.config.set("global_sync_saves", val))
        items_row.addWidget(self.sync_saves_cb)

        self.sync_servers_cb = QCheckBox("Servers (servers.dat)")
        self.sync_servers_cb.setChecked(self.config.get("global_sync_servers", True))
        self.sync_servers_cb.toggled.connect(lambda val: self.config.set("global_sync_servers", val))
        items_row.addWidget(self.sync_servers_cb)
        items_row.addStretch()
        card_layout.addLayout(items_row)

        # FROM & TO: Source and Target Instances
        direction_lbl = QLabel("Customize Direction (FROM & TO):")
        direction_lbl.setStyleSheet("font-weight: 600; margin-top: 4px;")
        card_layout.addWidget(direction_lbl)

        direction_row = QHBoxLayout()
        direction_row.setSpacing(15)

        from_col = QVBoxLayout()
        from_col.addWidget(QLabel("FROM (Source Instance):"))
        self.sync_source_combo = QComboBox()
        from_col.addWidget(self.sync_source_combo)
        direction_row.addLayout(from_col, stretch=1)

        to_col = QVBoxLayout()
        to_col.addWidget(QLabel("TO (Target Instance):"))
        self.sync_target_combo = QComboBox()
        to_col.addWidget(self.sync_target_combo)
        direction_row.addLayout(to_col, stretch=1)

        card_layout.addLayout(direction_row)

        self.sync_source_combo.currentIndexChanged.connect(self._on_sync_source_changed)
        self.sync_target_combo.currentIndexChanged.connect(self._on_sync_target_changed)

        sync_now_row = QHBoxLayout()
        sync_now_btn = QPushButton(" Sync Selected Data Now")
        sync_now_btn.setObjectName("SecondaryButton")
        sync_now_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        sync_now_btn.setIconSize(QSize(14, 14))
        sync_now_btn.clicked.connect(self._manual_global_sync)
        sync_now_row.addWidget(sync_now_btn)
        sync_now_row.addStretch()
        card_layout.addLayout(sync_now_row)

        self._populate_sync_combos()
        self.instance_mgr.instances_changed.connect(self._populate_sync_combos)

        # 4. Performance Mode: Clean & Repair
        maint_lbl = QLabel("Performance Mode: Clean & Repair")
        maint_lbl.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        card_layout.addWidget(maint_lbl)

        maint_row = QHBoxLayout()
        self.maint_btn = QPushButton(" Clean & Repair Cache")
        self.maint_btn.setObjectName("PrimaryButton")
        self.maint_btn.setIcon(IconEngine.get_icon("zap", QColor("#FFFFFF"), QColor("#FFFFFF"), 16))
        self.maint_btn.setIconSize(QSize(16, 16))
        self.maint_btn.clicked.connect(self._run_maintenance)
        maint_row.addWidget(self.maint_btn)
        card_layout.addLayout(maint_row)

        self.maint_progress = QProgressBar()
        self.maint_progress.setFixedHeight(8)
        self.maint_progress.setTextVisible(False)
        self.maint_progress.setValue(0)
        card_layout.addWidget(self.maint_progress)

        self.maint_status_lbl = QLabel("Ready for optimization.")
        self.maint_status_lbl.setStyleSheet("font-size: 12px; font-style: italic;")
        card_layout.addWidget(self.maint_status_lbl)

        # 5. Memory Allocation Section
        ram_lbl = QLabel(f"Memory Allocation (System Total: {total_mb / 1024:.1f} GB)")
        ram_lbl.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        card_layout.addWidget(ram_lbl)

        max_ram = min(self.config.get("max_ram_mb", 4096), max_allocable)

        self.max_ram_slider = RamSlider("Memory Allocation", 1024, max_allocable, max_ram)
        self.max_ram_slider.valueChanged.connect(self._on_max_ram_changed)
        card_layout.addWidget(self.max_ram_slider)

        # 6. Java Settings
        java_lbl = QLabel("Java Executable Runtime")
        java_lbl.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        card_layout.addWidget(java_lbl)

        java_row = QHBoxLayout()
        self.java_combo = QComboBox()
        self.java_combo.addItem("Auto Detect (System Default)", "auto")
        for name, path in JavaFinder.find_java_installations():
            self.java_combo.addItem(f"{name} ({path})", path)

        current_java = self.config.get("java_path", "auto")
        matched = False
        for i in range(self.java_combo.count()):
            if self.java_combo.itemData(i) == current_java:
                self.java_combo.setCurrentIndex(i)
                matched = True
                break
        if not matched and current_java != "auto":
            self.java_combo.addItem(f"Custom ({current_java})", current_java)
            self.java_combo.setCurrentIndex(self.java_combo.count() - 1)

        self.java_combo.currentIndexChanged.connect(self._on_java_changed)
        java_row.addWidget(self.java_combo, stretch=1)

        browse_java_btn = QPushButton(" Browse...")
        browse_java_btn.setObjectName("SecondaryButton")
        browse_java_btn.setIcon(IconEngine.get_icon("folder", QColor("#94A3B8"), QColor(accent), 14))
        browse_java_btn.setIconSize(QSize(14, 14))
        browse_java_btn.clicked.connect(self._browse_java)
        java_row.addWidget(browse_java_btn)
        card_layout.addLayout(java_row)

        jvm_lbl = QLabel("JVM Arguments")
        jvm_lbl.setStyleSheet("font-weight: 600; margin-top: 4px;")
        card_layout.addWidget(jvm_lbl)

        self.jvm_input = QLineEdit(self.config.get("jvm_args", ""))
        self.jvm_input.textChanged.connect(self._on_jvm_args_changed)
        card_layout.addWidget(self.jvm_input)

        # Close on launch checkbox
        self.close_cb = QCheckBox("Close launcher on game launch")
        self.close_cb.setChecked(self.config.get("close_on_launch", False))
        self.close_cb.toggled.connect(self._on_close_cb_toggled)
        card_layout.addWidget(self.close_cb)

        # 7. Discord Rich Presence Integration Section
        discord_lbl = QLabel("Discord Rich Presence Integration")
        discord_lbl.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        card_layout.addWidget(discord_lbl)

        discord_top_row = QHBoxLayout()
        self.discord_cb = QCheckBox("Enable Discord Rich Presence (RPC)")
        self.discord_cb.setChecked(self.config.get("discord_rpc", True))
        self.discord_cb.toggled.connect(self._on_discord_rpc_toggled)
        discord_top_row.addWidget(self.discord_cb)

        test_rpc_btn = QPushButton(" Test Presence")
        test_rpc_btn.setObjectName("SecondaryButton")
        test_rpc_btn.setIcon(IconEngine.get_icon("zap", QColor("#94A3B8"), QColor(accent), 14))
        test_rpc_btn.setIconSize(QSize(14, 14))
        test_rpc_btn.clicked.connect(self._test_discord_presence)
        discord_top_row.addWidget(test_rpc_btn)

        reconnect_rpc_btn = QPushButton(" Reconnect")
        reconnect_rpc_btn.setObjectName("SecondaryButton")
        reconnect_rpc_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        reconnect_rpc_btn.setIconSize(QSize(14, 14))
        reconnect_rpc_btn.clicked.connect(self._reconnect_discord)
        discord_top_row.addWidget(reconnect_rpc_btn)
        card_layout.addLayout(discord_top_row)

        discord_grid = QGridLayout()
        discord_grid.setSpacing(10)

        self.discord_launcher_cb = QCheckBox("Show Launcher Activity")
        self.discord_launcher_cb.setChecked(self.config.get("discord_launcher_activity", True))
        self.discord_launcher_cb.toggled.connect(lambda v: self.config.set("discord_launcher_activity", v))
        discord_grid.addWidget(self.discord_launcher_cb, 0, 0)

        self.discord_mc_cb = QCheckBox("Show Minecraft Activity")
        self.discord_mc_cb.setChecked(self.config.get("discord_mc_activity", True))
        self.discord_mc_cb.toggled.connect(lambda v: self.config.set("discord_mc_activity", v))
        discord_grid.addWidget(self.discord_mc_cb, 0, 1)

        self.discord_ver_cb = QCheckBox("Show Version")
        self.discord_ver_cb.setChecked(self.config.get("discord_show_version", True))
        self.discord_ver_cb.toggled.connect(lambda v: self.config.set("discord_show_version", v))
        discord_grid.addWidget(self.discord_ver_cb, 1, 0)

        self.discord_loader_cb = QCheckBox("Show Loader")
        self.discord_loader_cb.setChecked(self.config.get("discord_show_loader", True))
        self.discord_loader_cb.toggled.connect(lambda v: self.config.set("discord_show_loader", v))
        discord_grid.addWidget(self.discord_loader_cb, 1, 1)

        self.discord_inst_cb = QCheckBox("Show Instance")
        self.discord_inst_cb.setChecked(self.config.get("discord_show_instance", True))
        self.discord_inst_cb.toggled.connect(lambda v: self.config.set("discord_show_instance", v))
        discord_grid.addWidget(self.discord_inst_cb, 2, 0)

        self.discord_srv_cb = QCheckBox("Show Server")
        self.discord_srv_cb.setChecked(self.config.get("discord_show_server", True))
        self.discord_srv_cb.toggled.connect(lambda v: self.config.set("discord_show_server", v))
        discord_grid.addWidget(self.discord_srv_cb, 2, 1)

        self.discord_time_cb = QCheckBox("Show Session Time")
        self.discord_time_cb.setChecked(self.config.get("discord_show_time", True))
        self.discord_time_cb.toggled.connect(lambda v: self.config.set("discord_show_time", v))
        discord_grid.addWidget(self.discord_time_cb, 3, 0)

        self.discord_priv_cb = QCheckBox("Show Private Servers")
        self.discord_priv_cb.setChecked(self.config.get("discord_show_private_servers", False))
        self.discord_priv_cb.toggled.connect(lambda v: self.config.set("discord_show_private_servers", v))
        discord_grid.addWidget(self.discord_priv_cb, 3, 1)

        card_layout.addLayout(discord_grid)

        mode_sel_row = QHBoxLayout()
        mode_sel_row.addWidget(QLabel("Detail Mode:"))
        self.discord_mode_combo = QComboBox()
        self.discord_mode_combo.addItems(["Full", "Standard", "Minimal", "Private", "Disabled"])
        current_disc_mode = self.config.get("discord_mode", "Full")
        idx = self.discord_mode_combo.findText(current_disc_mode)
        if idx >= 0:
            self.discord_mode_combo.setCurrentIndex(idx)
        self.discord_mode_combo.currentTextChanged.connect(lambda text: self.config.set("discord_mode", text))
        mode_sel_row.addWidget(self.discord_mode_combo)
        mode_sel_row.addStretch()
        card_layout.addLayout(mode_sel_row)

<<<<<<< HEAD
        # Own Client ID — paste your application's ID here so RPC has a
        # registered application to talk to. Without this the bundled
        # legacy IDs may all be rejected with `Error 4000: Client ID is
        # Invalid`. Register a new application at discord.com/developers,
        # copy the "Application ID", and paste it below.
        cid_row = QHBoxLayout()
        cid_lbl = QLabel("My Client ID:")
        cid_lbl.setToolTip(
            "Discord application ID from discord.com/developers. Without a "
            "valid ID the launcher cannot register a Rich Presence."
        )
        cid_row.addWidget(cid_lbl)
        self.discord_client_id_edit = QLineEdit()
        self.discord_client_id_edit.setPlaceholderText("Paste your Discord Application ID here (leave blank to use bundled legacy IDs)")
        self.discord_client_id_edit.setText(self.config.get("discord_client_id", "") or "")
        self.discord_client_id_edit.editingFinished.connect(
            lambda: self._on_discord_client_id_changed(self.discord_client_id_edit.text())
        )
        cid_row.addWidget(self.discord_client_id_edit, 1)

        help_btn = QPushButton("?")
        help_btn.setObjectName("SecondaryButton")
        help_btn.setFixedWidth(28)
        help_btn.setToolTip(
            "How to get a Client ID:\n"
            "1. Go to discord.com/developers/applications\n"
            "2. Click 'New Application' and name it NeuraX\n"
            "3. Copy the 'Application ID' number\n"
            "4. Paste it into the box on the left\n"
            "5. (Optional) Under Rich Presence → Art Assets upload\n"
            "   nx.ico as 'nx_logo' and nx.png as 'nx_logo_small'"
        )
        help_btn.clicked.connect(self._show_discord_help)
        cid_row.addWidget(help_btn)
        card_layout.addLayout(cid_row)

=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        scroll_layout.addWidget(card)
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

    def _set_theme_mode(self, mode: str):
        self.dark_mode_btn.setProperty("active", "true" if mode == "dark" else "false")
        self.light_mode_btn.setProperty("active", "true" if mode == "light" else "false")
        self.dark_mode_btn.style().unpolish(self.dark_mode_btn)
        self.dark_mode_btn.style().polish(self.dark_mode_btn)
        self.light_mode_btn.style().unpolish(self.light_mode_btn)
        self.light_mode_btn.style().polish(self.light_mode_btn)

        self.logger.user_action(f"Toggled Theme Mode to '{mode.upper()}'")
        self.config.set("theme_mode", mode)

    def _set_theme_color(self, name: str, hex_code: str):
        for btn_name, btn in self.accent_buttons.items():
            is_active = (btn_name == name)
            btn.setProperty("active", "true" if is_active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.logger.user_action(f"Changed accent color to '{name}' ({hex_code})")
        self.config.set("theme_accent", name)
        self.config.set("accent_color", hex_code)

    def _populate_sync_combos(self):
        self.sync_source_combo.blockSignals(True)
        self.sync_target_combo.blockSignals(True)

        self.sync_source_combo.clear()
        self.sync_target_combo.clear()

        self.sync_source_combo.addItem("Most Played Instance (Auto)", "auto")
        self.sync_target_combo.addItem("All Other Instances", "all")

        instances = self.instance_mgr.list_instances()
        current_source = self.config.get("global_sync_source", "auto")
        current_target = self.config.get("global_sync_target", "all")

        source_idx = 0
        target_idx = 0

        for inst in instances:
            name = inst.get("name", inst.get("folder_name"))
            folder = inst.get("folder_name")
            display_text = f"{name} ({inst.get('version', '')})"

            self.sync_source_combo.addItem(display_text, folder)
            if folder == current_source:
                source_idx = self.sync_source_combo.count() - 1

            self.sync_target_combo.addItem(display_text, folder)
            if folder == current_target:
                target_idx = self.sync_target_combo.count() - 1

        self.sync_source_combo.setCurrentIndex(source_idx)
        self.sync_target_combo.setCurrentIndex(target_idx)

        self.sync_source_combo.blockSignals(False)
        self.sync_target_combo.blockSignals(False)

    def _on_sync_source_changed(self, idx: int):
        data = self.sync_source_combo.itemData(idx)
        if data is not None:
            self.config.set("global_sync_source", data)
            self.logger.user_input("Global Sync Source", data)

    def _on_sync_target_changed(self, idx: int):
        data = self.sync_target_combo.itemData(idx)
        if data is not None:
            self.config.set("global_sync_target", data)
            self.logger.user_input("Global Sync Target", data)

    def _on_global_sync_toggled(self, val: bool):
        self.config.set("global_sync_enabled", val)
        self.logger.user_input("Global Sync Enabled", val)

    def _manual_global_sync(self):
        try:
            ok, msg = self.instance_mgr.sync_global_data(self.config)
            if ok:
                QMessageBox.information(self, "Global Sync Complete", msg)
            else:
                QMessageBox.warning(self, "Global Sync Notice", msg)
        except Exception as e:
            QMessageBox.critical(self, "Global Sync Error", str(e))

    def _run_maintenance(self):
        self.maint_btn.setEnabled(False)
        self.maint_progress.setValue(0)
        self.maint_status_lbl.setText("Running system maintenance & repair...")
        self.maint_worker = MaintenanceWorker(self.config.neurax_dir)
        self.maint_worker.progress.connect(self._on_maint_progress)
        self.maint_worker.finished.connect(self._on_maint_finished)
        self.maint_worker.start()

    def _on_maint_progress(self, pct: int, status: str):
        self.maint_progress.setValue(pct)
        self.maint_status_lbl.setText(status)

    def _on_maint_finished(self, success: bool, message: str):
        self.maint_btn.setEnabled(True)
        self.maint_progress.setValue(100 if success else 0)
        self.maint_status_lbl.setText(message)
        if success:
            self.logger.info("Maintenance finished successfully.")
            QMessageBox.information(self, "Maintenance Complete", message)
        else:
            self.logger.error(f"Maintenance encountered an issue: {message}")
            QMessageBox.warning(self, "Maintenance Notice", message)

    def _on_max_ram_changed(self, val: int):
        self.config.set("max_ram_mb", val)
        self.logger.user_input("Max RAM", f"{val}MB")

    def _on_java_changed(self, idx: int):
        data = self.java_combo.itemData(idx)
        if data:
            self.config.set("java_path", data)
            self.logger.user_input("Java Path", data)

    def _browse_java(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Java Binary", "", "Executable (*.exe);;All Files (*)")
        if file_path:
            ver = JavaFinder.get_java_version(file_path)
            self.java_combo.addItem(f"Custom {ver} ({file_path})", file_path)
            self.java_combo.setCurrentIndex(self.java_combo.count() - 1)
            self.config.set("java_path", file_path)
            self.logger.user_input("Custom Java Path", file_path)

    def _on_jvm_args_changed(self, text: str):
        self.config.set("jvm_args", text.strip())

    def _on_close_cb_toggled(self, val: bool):
        self.config.set("close_on_launch", val)
        self.logger.user_input("Close on launch", val)

    def _on_discord_rpc_toggled(self, val: bool):
        self.config.set("discord_rpc", val)
        self.logger.user_input("Discord RPC", val)
        rpc = DiscordManager.get_instance(self.config)
        if val:
<<<<<<< HEAD
            ok, msg = rpc.connect()
            if not ok:
                QMessageBox.information(self, "Discord RPC", msg)
        else:
            rpc.clear_presence()

    def _on_discord_client_id_changed(self, text: str):
        cleaned = (text or "").strip()
        current = self.config.get("discord_client_id", "") or ""
        if cleaned == current:
            return
        # Basic sanity check: Discord application IDs are 17-20 digit
        # snowflakes. We store the raw value anyway but warn the user
        # so they can fix a typo immediately.
        if cleaned and (not cleaned.isdigit() or not (15 <= len(cleaned) <= 20)):
            QMessageBox.warning(
                self,
                "Discord Client ID",
                "That doesn't look like a valid Discord application ID. "
                "It should be a 17–20 digit number from discord.com/developers.",
            )
            self.discord_client_id_edit.setText(current)
            return
        self.config.set("discord_client_id", cleaned)
        self.logger.user_input("Discord Client ID", "updated" if cleaned else "cleared")

    def _show_discord_help(self):
        QMessageBox.information(
            self,
            "Discord Client ID",
            "To get a working Discord Client ID:\n\n"
            "1. Open discord.com/developers/applications in your browser.\n"
            "2. Click 'New Application' and name it NeuraX.\n"
            "3. On the application's General Information page, copy the\n"
            "   'Application ID' (a 17–20 digit number).\n"
            "4. Paste it into the box next to 'My Client ID'.\n\n"
            "Optional — upload art:\n"
            "• Under Rich Presence → Art Assets, upload nx.ico as 'nx_logo'.\n"
            "• Upload nx.png as 'nx_logo_small'.\n\n"
            "The launcher already points Discord at the local copies of\n"
            "those files, so once they're registered under those exact\n"
            "keys the icon will render inside Discord.",
        )

    def _test_discord_presence(self):
        rpc = DiscordManager.get_instance(self.config)
        if not rpc.is_enabled():
            QMessageBox.information(self, "Discord RPC", "Discord RPC is currently disabled. Please enable it first.")
            return
        # If we're not connected yet, force a connect attempt first so
        # the test actually fires a payload.
        if not rpc.connected:
            ok, msg = rpc.connect()
            if not ok:
                QMessageBox.warning(self, "Discord RPC", msg)
                return
        rpc.set_launcher_activity("Testing Rich Presence", "In NeuraX Launcher Settings")
=======
            rpc.start()
        else:
            rpc.stop()

    def _test_discord_presence(self):
        rpc = DiscordManager.get_instance(self.config)
        if not rpc.enabled:
            QMessageBox.information(self, "Discord RPC", "Discord RPC is currently disabled. Please enable it first.")
            return
        rpc.update_presence(state="Testing Rich Presence", details="In NeuraX Launcher Settings", force=True)
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        QMessageBox.information(self, "Discord RPC", "Discord presence updated! Check your Discord profile.")

    def _reconnect_discord(self):
        rpc = DiscordManager.get_instance(self.config)
<<<<<<< HEAD
        ok, msg = rpc.connect()
        if not ok:
            QMessageBox.warning(self, "Discord RPC", msg)
        else:
            QMessageBox.information(self, "Discord RPC", "Reconnection attempt initiated.")
=======
        rpc.reconnect()
        QMessageBox.information(self, "Discord RPC", "Reconnection attempt initiated.")
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    def _ms_login(self):
        self.logger.user_action("Triggered Microsoft Auth from SettingsView")
        dialog = MSAuthDialog(self, self.auth_mgr)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            username = self.config.get("username", "Player")
            self.account_status_lbl.setText(f"Logged in as: {username}")
