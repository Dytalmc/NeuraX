from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QComboBox, QMessageBox, QDialog
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager, get_dot_neurax_dir
from neurax.core.instances import InstanceManager
from neurax.core.versions import VersionManager
from neurax.core.launcher import LaunchWorker
from neurax.core.auth import AuthManager
from neurax.core.ai.ai_version_radar import AIVersionRadar, AIVersionRadarWorker
from neurax.core.logger import Logger
from neurax.gui.views.instances_view import InstanceDialog

class VersionsView(QWidget):
    """View to explore Mojang version manifest with live 0-Token AI Version Radar, filter checkboxes, direct instance creation, and double-tap launch to global directory."""

    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager = None, auth_mgr: AuthManager = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.auth_mgr = auth_mgr or getattr(parent, "auth_mgr", None)
        self.main_window = parent
        self.logger = Logger.get_instance()
        self.version_mgr = VersionManager.get_instance(config.neurax_dir / "cache")
        self.launch_worker = None
        self.ai_radar_worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Row
        header = QHBoxLayout()
        title = QLabel("Version Manifest & AI Radar")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton(" Refresh Manifest")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        refresh_btn.setIconSize(QSize(14, 14))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh_versions)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        # 0-Token AI Version Radar Panel
        self.ai_card = GlassCard()
        ai_layout = QVBoxLayout(self.ai_card)
        ai_layout.setContentsMargins(18, 14, 18, 14)
        ai_layout.setSpacing(8)

        ai_header = QHBoxLayout()
        ai_title = QLabel("0-Token AI Version Radar & Release Monitor")
        ai_title.setStyleSheet("font-size: 14px; font-weight: 800; letter-spacing: 0.5px;")
        ai_header.addWidget(ai_title)
        ai_header.addStretch()

        self.ai_status_badge = QLabel("REAL-TIME MONITOR ACTIVE")
        self.ai_status_badge.setStyleSheet("""
            background-color: rgba(0, 255, 153, 0.15);
            color: #00FF99;
            border: 1px solid rgba(0, 255, 153, 0.4);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 800;
        """)
        ai_header.addWidget(self.ai_status_badge)
        ai_layout.addLayout(ai_header)

        self.ai_info_lbl = QLabel("Monitoring Mojang piston-meta & official mod loader APIs...")
        self.ai_info_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.ai_info_lbl.setWordWrap(True)
        ai_layout.addWidget(self.ai_info_lbl)

        layout.addWidget(self.ai_card)

        # Checkboxes Options Rows
        opts_col = QVBoxLayout()
        row1 = QHBoxLayout()
        self.cb_releases = QCheckBox("Releases")
        self.cb_releases.setChecked(self.config.get("show_releases", True))
        self.cb_snapshots = QCheckBox("Snapshots")
        self.cb_snapshots.setChecked(self.config.get("show_snapshots", False))
        self.cb_beta = QCheckBox("Beta")
        self.cb_beta.setChecked(self.config.get("show_beta", False))
        self.cb_alpha = QCheckBox("Alpha")
        self.cb_alpha.setChecked(self.config.get("show_alpha", False))
        row1.addWidget(self.cb_releases)
        row1.addWidget(self.cb_snapshots)
        row1.addWidget(self.cb_beta)
        row1.addWidget(self.cb_alpha)
        row1.addStretch()
        opts_col.addLayout(row1)

        row2 = QHBoxLayout()
        self.cb_indev = QCheckBox("Indev/Infdev")
        self.cb_indev.setChecked(self.config.get("show_indev", False))
        self.cb_aprilfools = QCheckBox("April Fools")
        self.cb_aprilfools.setChecked(self.config.get("show_aprilfools", False))
        self.cb_historic = QCheckBox("Historic")
        self.cb_historic.setChecked(self.config.get("show_historic", False))
        row2.addWidget(self.cb_indev)
        row2.addWidget(self.cb_aprilfools)
        row2.addWidget(self.cb_historic)
        row2.addStretch()
        opts_col.addLayout(row2)

        layout.addLayout(opts_col)

        for cb in (self.cb_releases, self.cb_snapshots, self.cb_beta, self.cb_alpha, self.cb_indev, self.cb_aprilfools, self.cb_historic):
            cb.toggled.connect(self._on_option_changed)

        # Version Dropdown Selection Row
        dropdown_row = QHBoxLayout()
        dd_lbl = QLabel("Select Version:")
        dd_lbl.setStyleSheet("font-weight: 600;")
        dropdown_row.addWidget(dd_lbl)
        
        self.version_dropdown = QComboBox()
        self.version_dropdown.setMinimumHeight(38)
        dropdown_row.addWidget(self.version_dropdown, stretch=1)

        create_btn = QPushButton(" Create Instance from Version")
        create_btn.setObjectName("PrimaryButton")
        create_btn.setIcon(IconEngine.get_icon("plus", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        create_btn.setIconSize(QSize(14, 14))
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self.create_instance_from_selected)
        dropdown_row.addWidget(create_btn)
        layout.addLayout(dropdown_row)

        # Versions List Container
        card = GlassCard()
        card_layout = QVBoxLayout(card)

        self.version_list = QListWidget()
        self.version_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.version_list.itemDoubleClicked.connect(self.launch_version_global)
        card_layout.addWidget(self.version_list)
        layout.addWidget(card)

        self.version_mgr.versions_updated.connect(self._on_ai_version_update)
        self.version_mgr.start_monitoring(poll_interval=300)

        # Start a dedicated AIVersionRadarWorker for snapshot/release auto-detection
        self._ai_radar_worker = AIVersionRadarWorker(poll_interval=300)
        self._ai_radar_worker.versions_updated.connect(self._on_ai_version_update)
        self._ai_radar_worker.new_version_detected.connect(self._on_new_version_detected)
        self._ai_radar_worker.start()

        self.load_versions()

    def _on_ai_version_update(self, info: dict):
        latest_rel = info.get("latest_release", "")
        latest_snap = info.get("latest_snapshot", "")
        latest_af = info.get("latest_aprilfools", "24w14a")
        loaders = info.get("loaders", {})
        rel_status = info.get("release_status", "")
        snap_status = info.get("snapshot_status", "")
        stability = info.get("stability_index", 0)
        snap_stability = info.get("snapshot_stability", 0)

        parts = []
        if latest_rel:
            parts.append(f"Latest Release: {latest_rel}" + (f" [{rel_status}]" if rel_status else ""))
        if latest_snap:
            parts.append(f"Latest Snapshot: {latest_snap}" + (f" [{snap_status}]" if snap_status else ""))
        if latest_af:
            parts.append(f"April Fools: {latest_af}")

        loader_str = " • ".join([f"{k}: {v}" for k, v in loaders.items() if v and v not in ("Latest",)])
        if loader_str:
            parts.append(f"Loaders: {loader_str}")

        self.ai_info_lbl.setText("\n".join(parts))

        is_new_snap = info.get("new_snapshot_detected", False)
        is_new_rel = info.get("new_release_detected", False)

        if is_new_rel and latest_rel:
            self.ai_status_badge.setText(f"🆕 NEW RELEASE: {latest_rel}")
            self.ai_status_badge.setStyleSheet("""
                background-color: rgba(0, 240, 255, 0.18);
                color: #00F0FF;
                border: 1.5px solid #00F0FF;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 900;
            """)
        elif is_new_snap and latest_snap:
            self.ai_status_badge.setText(f"🔔 NEW SNAPSHOT: {latest_snap}")
            self.ai_status_badge.setStyleSheet("""
                background-color: rgba(255, 215, 0, 0.25);
                color: #FFD700;
                border: 1.5px solid #FFD700;
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 900;
            """)
        else:
            self.ai_status_badge.setText("AI VERSION RADAR ACTIVE")
            self.ai_status_badge.setStyleSheet("""
                background-color: rgba(0, 255, 153, 0.15);
                color: #00FF99;
                border: 1px solid rgba(0, 255, 153, 0.4);
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 800;
            """)

    def _on_new_version_detected(self, version_id: str, version_type: str):
        """Auto-refresh version list and show a non-blocking notification when new version detected."""
        self.logger.info(f"AI Version Radar: Auto-adding {version_type} '{version_id}' to manifest")
        # Force-refresh the manifest cache so the new version shows up
        self.version_mgr.fetch_manifest(force_refresh=True)
        # Enable snapshots automatically if a snapshot was detected
        if version_type == "snapshot" and not self.cb_snapshots.isChecked():
            self.cb_snapshots.setChecked(True)  # This triggers load_versions via toggled signal
        else:
            self.load_versions()
        # Show top-of-list highlight via scrolling to the top
        self.version_list.scrollToTop()



    def _on_option_changed(self):
        self.config.set("show_releases", self.cb_releases.isChecked())
        self.config.set("show_snapshots", self.cb_snapshots.isChecked())
        self.config.set("show_beta", self.cb_beta.isChecked())
        self.config.set("show_alpha", self.cb_alpha.isChecked())
        self.config.set("show_indev", self.cb_indev.isChecked())
        self.config.set("show_aprilfools", self.cb_aprilfools.isChecked())
        self.config.set("show_historic", self.cb_historic.isChecked())
        self.logger.user_input("Version Filters Changed", f"rel={self.cb_releases.isChecked()}, snap={self.cb_snapshots.isChecked()}, beta={self.cb_beta.isChecked()}, alpha={self.cb_alpha.isChecked()}")
        self.load_versions()

    def refresh_versions(self):
        self.logger.user_action("Clicked Refresh Version Manifest")
        self.version_mgr.fetch_manifest(force_refresh=True)
        self.load_versions()

    def load_versions(self):
        self.version_list.clear()
        self.version_dropdown.clear()
        versions = self.version_mgr.get_filtered_versions(
            show_releases=self.cb_releases.isChecked(),
            show_snapshots=self.cb_snapshots.isChecked(),
            show_beta=self.cb_beta.isChecked(),
            show_alpha=self.cb_alpha.isChecked(),
            show_indev=self.cb_indev.isChecked(),
            show_aprilfools=self.cb_aprilfools.isChecked(),
            show_historic=self.cb_historic.isChecked()
        )
        accent = self.config.get("accent_color", "#00F0FF")
        for ver in versions:
            item = QListWidgetItem(f"Minecraft {ver}")
            item.setIcon(IconEngine.get_icon("versions", QColor("#8A94A6"), QColor(accent), 16))
            item.setData(Qt.ItemDataRole.UserRole, ver)
            self.version_list.addItem(item)
            self.version_dropdown.addItem(f"Minecraft {ver}", ver)

    def create_instance_from_selected(self):
        selected_ver = self.version_dropdown.currentData()
        item = self.version_list.currentItem()
        if item:
            selected_ver = item.data(Qt.ItemDataRole.UserRole)
        if not selected_ver:
            selected_ver = "1.20.4"

        self.logger.user_action(f"Initiated instance creation from version '{selected_ver}'")
        dialog = InstanceDialog(
            self, config=self.config,
            title=f"New Instance ({selected_ver})",
            name=f"MC_{selected_ver}",
            version=selected_ver,
            jvm_args=self.config.get("jvm_args", "")
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if data["name"] and self.instance_mgr:
                new_folder = self.instance_mgr.create_instance(
                    name=data["name"],
                    version=data["version"],
                    loader=data["loader"],
                    max_ram=data["max_ram"],
                    java_path=data["java_path"],
                    jvm_args=data["jvm_args"]
                )
                self.config.set("selected_instance", new_folder)
                self.logger.user_action(f"Created instance '{data['name']}' from version '{selected_ver}'")
                QMessageBox.information(self, "Instance Created", f"Instance '{data['name']}' created successfully.")

    def launch_version_global(self, item=None):
        main_win = getattr(self, "main_window", None) or self.window()
        if hasattr(main_win, "nav_bar") and main_win.nav_bar:
            main_win.nav_bar._on_btn_clicked(0)
        elif hasattr(main_win, "stacked_widget") and main_win.stacked_widget:
            main_win.stacked_widget.slide_to_index(0)

        version_id = None
        if item and hasattr(item, "data"):
            version_id = item.data(Qt.ItemDataRole.UserRole)
        if not version_id:
            version_id = self.version_dropdown.currentData()
        if not version_id:
            curr_item = self.version_list.currentItem()
            if curr_item:
                version_id = curr_item.data(Qt.ItemDataRole.UserRole)
        if not version_id:
            version_id = "1.20.4"

        token = self.config.get("access_token", "0")
        auth_mode = self.config.get("auth_mode", "microsoft")
        if auth_mode == "microsoft" and (not token or token == "0"):
            QMessageBox.warning(
                self,
                "Microsoft Login Required",
                "Please log in with your Microsoft account in Launcher Settings to play."
            )
            return

        if self.launch_worker and self.launch_worker.isRunning():
            QMessageBox.information(self, "Game Launching", "A game launch is already in progress.")
            return

        global_dir = get_dot_neurax_dir() / "global"
        game_dir = global_dir / ".minecraft"
        global_dir.mkdir(parents=True, exist_ok=True)
        game_dir.mkdir(parents=True, exist_ok=True)

        inst_data = {
            "name": f"Global_{version_id}",
            "loader": "Vanilla",
            "version": version_id,
            "game_dir": str(game_dir),
            "max_ram": self.config.get("max_ram_mb", 4096),
            "java_path": self.config.get("java_path", "auto"),
            "jvm_args": self.config.get("jvm_args", "")
        }

        session = {
            "username": self.config.get("username", "NeuraPlayer"),
            "uuid": self.config.get("uuid", "00000000-0000-0000-0000-000000000000"),
            "access_token": token,
            "mode": auth_mode,
            "custom_skin_path": self.config.get("custom_skin_path", ""),
            "skin_model": self.config.get("skin_model", "classic"),
            "xuid": self.config.get("xuid", "0"),
            "accent_color": self.config.get("accent_color", "#00F0FF")
        }

        custom_java = self.config.get("java_path", "auto")
        max_ram = self.config.get("max_ram_mb", 4096)
        jvm_args = self.config.get("jvm_args", "")

        self.logger.user_action(f"Launching global version '{version_id}' directly from Versions view")

        self.launch_worker = LaunchWorker(
            neurax_dir=self.config.neurax_dir,
            instance_data=inst_data,
            session=session,
            custom_java=custom_java,
            jvm_args=jvm_args,
            max_ram=max_ram,
            auth_mgr=self.auth_mgr,
            config_mgr=self.config
        )
        self.launch_worker.finished.connect(self._on_launch_finished)
        self.launch_worker.game_exited.connect(self._on_game_exited)
        if hasattr(self.window(), "status_bar") and self.window().status_bar:
            self.launch_worker.progress.connect(self.window().status_bar.update_status)
        self.launch_worker.start()

    def _on_launch_finished(self, success: bool, msg: str):
        if success:
            self.logger.info(f"Global Version Launch Success: {msg}")
            if self.config.get("close_on_launch", False):
                main_win = getattr(self, "main_window", None) or self.window()
                if hasattr(main_win, "enter_background_mode"):
                    main_win.enter_background_mode()
                elif hasattr(main_win, "hide"):
                    main_win.hide()
        else:
            self.logger.error(f"Global Version Launch Failure: {msg}")
            QMessageBox.critical(self, "Launch Error", f"Could not launch version:\n\n{msg}")

    def _on_game_exited(self, exit_code: int):
        self.logger.info(f"Global Version game exited with code {exit_code}")
        if self.config.get("close_on_launch", False):
            main_win = getattr(self, "main_window", None) or self.window()
            if hasattr(main_win, "exit_background_mode"):
                main_win.exit_background_mode()
            elif hasattr(main_win, "show"):
                main_win.show()
                main_win.activateWindow()
                main_win.raise_()
