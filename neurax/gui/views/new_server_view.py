import os
import sys
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QPlainTextEdit, QProgressBar,
    QFrame, QTreeWidget, QTreeWidgetItem, QSplitter,
    QMessageBox
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QSize
from PyQt6.QtGui import QDesktopServices, QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.widgets.ram_slider import RamSlider
from neurax.gui.widgets.animated_stacked_widget import AnimatedStackedWidget
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager, get_dot_neurax_dir, get_system_ram_info
from neurax.core.auth import AuthManager
from neurax.core.versions import VersionManager
from neurax.core.local_server import LocalServerManager, CreateServerWorker, LocalServerRunner
from neurax.core.logger import Logger

class AnimatedSubTabBar(QFrame):
    tab_changed = pyqtSignal(int)

    def __init__(self, tabs: list, config: ConfigManager = None, parent=None):
        super().__init__(parent)
        self.setObjectName("SubTabBar")
        self.config = config
        self.tabs = tabs
        self.buttons = []
        self.current_index = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.indicator = QFrame(self)
        self.indicator.setObjectName("TabIndicator")
        self.indicator.setGeometry(0, 0, 0, 0)
        
        accent = self.config.get("accent_color", "#00F0FF") if self.config else "#00F0FF"
        self.set_accent_color(accent)

        for idx, (icon_type, name) in enumerate(tabs):
            btn = QPushButton(f" {name}")
            btn.setObjectName("SubTabButton")
            btn.setIcon(IconEngine.get_icon(icon_type, QColor("#94A3B8"), QColor(accent), 16))
            btn.setIconSize(QSize(16, 16))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", "true" if idx == 0 else "false")
            btn.clicked.connect(lambda checked, i=idx: self.set_active_tab(i))
            layout.addWidget(btn)
            self.buttons.append(btn)

        layout.addStretch()

        for btn in self.buttons:
            btn.raise_()

        self.indicator_anim = QPropertyAnimation(self.indicator, b"geometry", self)
        self.indicator_anim.setDuration(220)
        self.indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_accent_color(self, color_hex: str):
        c = QColor(color_hex)
        r, g, b = c.red(), c.green(), c.blue()
        self.indicator.setStyleSheet(f"""
            QFrame#TabIndicator {{
                background-color: rgba({r}, {g}, {b}, 0.2);
                border: 1.5px solid {color_hex};
                border-radius: 8px;
            }}
        """)
        mode = self.config.get("theme_mode", "dark") if self.config else "dark"
        icon_normal = QColor("#FFFFFF") if mode == "dark" else QColor("#1E293B")
        for idx, (icon_type, name) in enumerate(getattr(self, "tabs", [])):
            if idx < len(self.buttons):
                self.buttons[idx].setIcon(IconEngine.get_icon(icon_type, icon_normal, c, 16))

    def _update_indicator(self, index: int, animate: bool = True):
        if 0 <= index < len(self.buttons):
            target_btn = self.buttons[index]
            btn_geom = target_btn.geometry()
            if btn_geom.width() > 0 and btn_geom.height() > 0:
                target_rect = QRect(btn_geom.x(), btn_geom.y(), btn_geom.width(), btn_geom.height())
                if animate and self.indicator.width() > 0 and self.indicator.height() > 0:
                    self.indicator_anim.stop()
                    self.indicator_anim.setStartValue(self.indicator.geometry())
                    self.indicator_anim.setEndValue(target_rect)
                    self.indicator_anim.start()
                else:
                    self.indicator_anim.stop()
                    self.indicator.setGeometry(target_rect)
            else:
                self.indicator.setGeometry(0, 0, 0, 0)

    def set_active_tab(self, index: int, notify: bool = True):
        if index == self.current_index and not notify:
            return
        
        self.current_index = index
        for idx, btn in enumerate(self.buttons):
            btn.setProperty("active", "true" if idx == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._update_indicator(index, animate=True)
        if notify:
            self.tab_changed.emit(index)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_indicator(self.current_index, animate=False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_indicator(self.current_index, animate=False)


class NewServerView(QWidget):
    def __init__(self, config: ConfigManager, auth_mgr: AuthManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.auth_mgr = auth_mgr
        self.logger = Logger.get_instance()
        self.server_mgr = LocalServerManager(config.neurax_dir)
        self.version_mgr = VersionManager(config.neurax_dir / "cache")
        self.active_runner = None
        self.current_editing_file = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header_layout = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("+ New Server")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_col.addWidget(title)

        subtitle = QLabel("Create and manage local Minecraft servers stored in .neurax/servers")
        subtitle.setStyleSheet("font-size: 12px;")
        title_col.addWidget(subtitle)

        header_layout.addLayout(title_col)
        header_layout.addStretch()

        open_servers_dir_btn = QPushButton(" Open Servers Folder")
        open_servers_dir_btn.setObjectName("SecondaryButton")
        open_servers_dir_btn.setIcon(IconEngine.get_icon("folder", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        open_servers_dir_btn.setIconSize(QSize(14, 14))
        open_servers_dir_btn.clicked.connect(self._open_servers_folder)
        header_layout.addWidget(open_servers_dir_btn)

        layout.addLayout(header_layout)

        self.sub_tab_bar = AnimatedSubTabBar(
            [
                ("servers", "Create & Run Local Server"),
                ("folder", "File Explorer & Editor")
            ],
            config=self.config,
            parent=self
        )
        layout.addWidget(self.sub_tab_bar)

        self.stacked_widget = AnimatedStackedWidget(self)

        self.control_tab = QWidget()
        self._init_control_tab()
        self.stacked_widget.addWidget(self.control_tab)

        self.editor_tab = QWidget()
        self._init_editor_tab()
        self.stacked_widget.addWidget(self.editor_tab)

        layout.addWidget(self.stacked_widget, stretch=1)

        self.sub_tab_bar.tab_changed.connect(self._on_sub_tab_changed)
        self.server_mgr.servers_changed.connect(self._refresh_server_combos)
        self.config.config_changed.connect(self._on_config_changed)
        self._refresh_server_combos()

    def _on_sub_tab_changed(self, index: int):
        self.stacked_widget.slide_to_index(index)

    def _on_config_changed(self, key: str, value: object):
        if key == "accent_color":
            self.sub_tab_bar.set_accent_color(str(value))

    def _open_servers_folder(self):
        servers_dir = get_dot_neurax_dir() / "servers"
        servers_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(servers_dir)))

    def _init_control_tab(self):
        accent = self.config.get("accent_color", "#00F0FF") if self.config else "#00F0FF"
        ctrl_layout = QVBoxLayout(self.control_tab)
        ctrl_layout.setContentsMargins(15, 15, 15, 15)
        ctrl_layout.setSpacing(15)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        create_card = GlassCard()
        create_layout = QVBoxLayout(create_card)
        create_layout.setContentsMargins(20, 20, 20, 20)
        create_layout.setSpacing(12)

        create_title = QLabel("Create New Local Server")
        create_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        create_layout.addWidget(create_title)

        create_layout.addWidget(QLabel("Server Name:"))
        self.server_name_input = QLineEdit()
        self.server_name_input.setPlaceholderText("My Survival Server")
        create_layout.addWidget(self.server_name_input)

        total_mb, max_allocable = get_system_ram_info()
        self.ram_slider = RamSlider("Memory Allocation", 1024, max_allocable, 2048)
        create_layout.addWidget(self.ram_slider)

        create_layout.addWidget(QLabel("Server Loader / API:"))
        self.loader_combo = QComboBox()
        self.loader_combo.addItems([
            "Paper", "Vanilla", "Fabric", "Purpur", "Quilt", "Forge", "NeoForge",
            "Folia", "Leaf", "Spigot", "Bukkit", "Velocity", "PumpkinMC"
        ])
        create_layout.addWidget(self.loader_combo)

        create_layout.addWidget(QLabel("Minecraft Version:"))
        self.version_combo = QComboBox()
        self._populate_versions()
        create_layout.addWidget(self.version_combo)

        create_layout.addWidget(QLabel("Server Port:"))
        self.port_input = QLineEdit("25565")
        create_layout.addWidget(self.port_input)

        self.create_btn = QPushButton(" Create Local Server")
        self.create_btn.setObjectName("PrimaryButton")
        self.create_btn.setIcon(IconEngine.get_icon("play_triangle", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        self.create_btn.setIconSize(QSize(14, 14))
        self.create_btn.setMinimumHeight(38)
        self.create_btn.clicked.connect(self._create_local_server)
        create_layout.addWidget(self.create_btn)

        self.create_progress = QProgressBar()
        self.create_progress.setFixedHeight(6)
        self.create_progress.setTextVisible(False)
        self.create_progress.setValue(0)
        create_layout.addWidget(self.create_progress)

        self.create_status_lbl = QLabel("Ready to build local server.")
        self.create_status_lbl.setStyleSheet("font-size: 11px; font-style: italic;")
        create_layout.addWidget(self.create_status_lbl)

        create_layout.addStretch()
        splitter.addWidget(create_card)

        run_card = GlassCard()
        run_layout = QVBoxLayout(run_card)
        run_layout.setContentsMargins(20, 20, 20, 20)
        run_layout.setSpacing(12)

        run_title_row = QHBoxLayout()
        run_title = QLabel("Local Server Control & Live Console")
        run_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        run_title_row.addWidget(run_title)
        run_title_row.addStretch()

        self.status_badge = QLabel("OFFLINE")
        self.status_badge.setStyleSheet("""
            background-color: rgba(255, 51, 102, 0.15);
            color: #FF3366;
            border: 1px solid rgba(255, 51, 102, 0.4);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 800;
        """)
        run_title_row.addWidget(self.status_badge)
        run_layout.addLayout(run_title_row)

        select_row = QHBoxLayout()
        select_row.addWidget(QLabel("Select Local Server:"))
        self.run_server_combo = QComboBox()
        self.run_server_combo.currentIndexChanged.connect(self._on_run_server_changed)
        select_row.addWidget(self.run_server_combo, stretch=1)
        run_layout.addLayout(select_row)

        actions_row = QHBoxLayout()
        self.start_btn = QPushButton(" Start Server")
        self.start_btn.setObjectName("PrimaryButton")
        self.start_btn.setIcon(IconEngine.get_icon("play_triangle", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        self.start_btn.setIconSize(QSize(14, 14))
        self.start_btn.clicked.connect(self._start_server)
        actions_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton(" Stop Server")
        self.stop_btn.setObjectName("SecondaryButton")
        self.stop_btn.setIcon(IconEngine.get_icon("stop_square", QColor("#94A3B8"), QColor("#FF3366"), 14))
        self.stop_btn.setIconSize(QSize(14, 14))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_server)
        actions_row.addWidget(self.stop_btn)

        self.reinstall_btn = QPushButton(" Reinstall")
        self.reinstall_btn.setObjectName("SecondaryButton")
        self.reinstall_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        self.reinstall_btn.setIconSize(QSize(14, 14))
        self.reinstall_btn.clicked.connect(self._reinstall_current_server)
        actions_row.addWidget(self.reinstall_btn)

        self.clear_console_btn = QPushButton(" Clear Console")
        self.clear_console_btn.setObjectName("SecondaryButton")
        self.clear_console_btn.setIcon(IconEngine.get_icon("trash", QColor("#94A3B8"), QColor("#FF3366"), 14))
        self.clear_console_btn.setIconSize(QSize(14, 14))
        self.clear_console_btn.clicked.connect(self._clear_console)
        actions_row.addWidget(self.clear_console_btn)

        self.delete_server_btn = QPushButton(" Delete Server")
        self.delete_server_btn.setObjectName("SecondaryButton")
        self.delete_server_btn.setIcon(IconEngine.get_icon("trash", QColor("#94A3B8"), QColor("#FF3366"), 14))
        self.delete_server_btn.setIconSize(QSize(14, 14))
        self.delete_server_btn.clicked.connect(self._delete_current_server)
        actions_row.addWidget(self.delete_server_btn)

        run_layout.addLayout(actions_row)

        self.console_output = QPlainTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setMaximumBlockCount(2000)
        self.console_output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #05070B;
                color: #00FF99;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 8px;
            }
        """)
        run_layout.addWidget(self.console_output)

        cmd_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Enter server command (e.g., op player, say Hello, stop)...")
        self.cmd_input.returnPressed.connect(self._send_command)
        cmd_row.addWidget(self.cmd_input, stretch=1)

        send_cmd_btn = QPushButton("Send")
        send_cmd_btn.setObjectName("SecondaryButton")
        send_cmd_btn.clicked.connect(self._send_command)
        cmd_row.addWidget(send_cmd_btn)

        run_layout.addLayout(cmd_row)

        splitter.addWidget(run_card)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        ctrl_layout.addWidget(splitter)

    def _init_editor_tab(self):
        accent = self.config.get("accent_color", "#00F0FF") if self.config else "#00F0FF"
        edit_layout = QVBoxLayout(self.editor_tab)
        edit_layout.setContentsMargins(15, 15, 15, 15)
        edit_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Select Server Folder:"))
        self.editor_server_combo = QComboBox()
        self.editor_server_combo.currentIndexChanged.connect(self._load_file_tree)
        top_row.addWidget(self.editor_server_combo, stretch=1)

        refresh_tree_btn = QPushButton(" Refresh Files")
        refresh_tree_btn.setObjectName("SecondaryButton")
        refresh_tree_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        refresh_tree_btn.setIconSize(QSize(14, 14))
        refresh_tree_btn.clicked.connect(self._load_file_tree)
        top_row.addWidget(refresh_tree_btn)

        edit_layout.addLayout(top_row)

        shortcuts_card = GlassCard()
        shortcuts_layout = QHBoxLayout(shortcuts_card)
        shortcuts_layout.setContentsMargins(12, 8, 12, 8)
        shortcuts_layout.setSpacing(10)

        shortcut_props_btn = QPushButton(" server.properties")
        shortcut_props_btn.setObjectName("SecondaryButton")
        shortcut_props_btn.setIcon(IconEngine.get_icon("settings", QColor("#94A3B8"), QColor(accent), 14))
        shortcut_props_btn.setIconSize(QSize(14, 14))
        shortcut_props_btn.clicked.connect(lambda: self._quick_open_file("server.properties"))
        shortcuts_layout.addWidget(shortcut_props_btn)

        shortcut_eula_btn = QPushButton(" eula.txt")
        shortcut_eula_btn.setObjectName("SecondaryButton")
        shortcut_eula_btn.setIcon(IconEngine.get_icon("terminal", QColor("#94A3B8"), QColor(accent), 14))
        shortcut_eula_btn.setIconSize(QSize(14, 14))
        shortcut_eula_btn.clicked.connect(lambda: self._quick_open_file("eula.txt"))
        shortcuts_layout.addWidget(shortcut_eula_btn)

        shortcut_ops_btn = QPushButton(" ops.json")
        shortcut_ops_btn.setObjectName("SecondaryButton")
        shortcut_ops_btn.setIcon(IconEngine.get_icon("shield", QColor("#94A3B8"), QColor(accent), 14))
        shortcut_ops_btn.setIconSize(QSize(14, 14))
        shortcut_ops_btn.clicked.connect(lambda: self._quick_open_file("ops.json"))
        shortcuts_layout.addWidget(shortcut_ops_btn)

        shortcut_wl_btn = QPushButton(" whitelist.json")
        shortcut_wl_btn.setObjectName("SecondaryButton")
        shortcut_wl_btn.setIcon(IconEngine.get_icon("check", QColor("#94A3B8"), QColor(accent), 14))
        shortcut_wl_btn.setIconSize(QSize(14, 14))
        shortcut_wl_btn.clicked.connect(lambda: self._quick_open_file("whitelist.json"))
        shortcuts_layout.addWidget(shortcut_wl_btn)

        shortcut_world_btn = QPushButton(" View world/ Files")
        shortcut_world_btn.setObjectName("SecondaryButton")
        shortcut_world_btn.setIcon(IconEngine.get_icon("globe", QColor("#94A3B8"), QColor(accent), 14))
        shortcut_world_btn.setIconSize(QSize(14, 14))
        shortcut_world_btn.clicked.connect(self._quick_open_world)
        shortcuts_layout.addWidget(shortcut_world_btn)

        shortcuts_layout.addStretch()
        edit_layout.addWidget(shortcuts_card)

        edit_splitter = QSplitter(Qt.Orientation.Horizontal)

        tree_card = GlassCard()
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(12, 12, 12, 12)
        tree_layout.setSpacing(8)

        tree_title = QLabel("Server Directory Tree")
        tree_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        tree_layout.addWidget(tree_title)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderHidden(True)
        self.file_tree.itemClicked.connect(self._on_tree_item_clicked)
        tree_layout.addWidget(self.file_tree)

        edit_splitter.addWidget(tree_card)

        editor_card = GlassCard()
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(15, 15, 15, 15)
        editor_layout.setSpacing(10)

        editor_header = QHBoxLayout()
        self.file_path_lbl = QLabel("No file selected")
        self.file_path_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        editor_header.addWidget(self.file_path_lbl)
        editor_header.addStretch()

        self.save_file_btn = QPushButton(" Save Changes")
        self.save_file_btn.setObjectName("PrimaryButton")
        self.save_file_btn.setIcon(IconEngine.get_icon("save", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        self.save_file_btn.setIconSize(QSize(14, 14))
        self.save_file_btn.setEnabled(False)
        self.save_file_btn.clicked.connect(self._save_current_file)
        editor_header.addWidget(self.save_file_btn)

        editor_layout.addLayout(editor_header)

        self.file_editor = QPlainTextEdit()
        self.file_editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #05070B;
                color: #FFFFFF;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 10px;
            }
        """)
        editor_layout.addWidget(self.file_editor)

        edit_splitter.addWidget(editor_card)
        edit_splitter.setStretchFactor(0, 1)
        edit_splitter.setStretchFactor(1, 2)

        edit_layout.addWidget(edit_splitter)

    def _populate_versions(self):
        self.version_combo.clear()
        vers = self.version_mgr.get_filtered_versions(show_releases=True)
        for v in vers:
            self.version_combo.addItem(v)

    def _refresh_server_combos(self):
        servers = self.server_mgr.list_servers()
        
        self.run_server_combo.blockSignals(True)
        self.run_server_combo.clear()
        for s in servers:
            self.run_server_combo.addItem(f"{s['name']} ({s.get('loader', 'Paper')} {s.get('version', '')})", s["folder_name"])
        self.run_server_combo.blockSignals(False)

        self.editor_server_combo.blockSignals(True)
        self.editor_server_combo.clear()
        for s in servers:
            self.editor_server_combo.addItem(f"{s['name']} ({s.get('loader', 'Paper')} {s.get('version', '')})", s["folder_name"])
        self.editor_server_combo.blockSignals(False)

        self._load_file_tree()

    def _on_run_server_changed(self, index: int):
        pass

    def _create_local_server(self):
        name = self.server_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Input Required", "Please enter a server name.")
            return

        loader = self.loader_combo.currentText()
        version = self.version_combo.currentText()
        max_ram = self.ram_slider.value()
        try:
            port = int(self.port_input.text().strip())
        except ValueError:
            port = 25565

        self.create_btn.setEnabled(False)
        self.create_progress.setValue(0)
        self.create_status_lbl.setText("Initiating server creation worker...")

        self.worker = CreateServerWorker(
            server_mgr=self.server_mgr,
            name=name,
            loader=loader,
            version=version,
            max_ram=max_ram,
            port=port
        )
        self.worker.progress.connect(self._on_create_progress)
        self.worker.finished.connect(self._on_create_finished)
        self.worker.start()

    def _on_create_progress(self, pct: int, msg: str):
        self.create_progress.setValue(pct)
        self.create_status_lbl.setText(msg)

    def _on_create_finished(self, success: bool, msg: str):
        self.create_btn.setEnabled(True)
        if success:
            self.create_progress.setValue(100)
            self.create_status_lbl.setText("Server created successfully!")
            QMessageBox.information(self, "Success", msg)
            self.server_name_input.clear()
            self._refresh_server_combos()
        else:
            self.create_progress.setValue(0)
            self.create_status_lbl.setText("Server creation failed.")
            QMessageBox.critical(self, "Error", msg)

    def _start_server(self):
        folder_name = self.run_server_combo.currentData()
        if not folder_name:
            QMessageBox.warning(self, "Selection Required", "Please select a server to start.")
            return

        # Guard against rapid double-clicks: a second click while a runner is
        # already active would spawn a second LocalServerRunner on the same
        # server folder, orphaning the first one.
        if self.active_runner is not None and self.active_runner.is_running:
            QMessageBox.information(
                self, "Server Already Running",
                "A local server is already running. Stop it first before starting a new one."
            )
            return

        server_data = self.server_mgr.get_server(folder_name)
        if not server_data:
            return

        self.console_output.appendPlainText(f"\n--- Starting {server_data['name']} ({server_data.get('loader')} {server_data.get('version')}) ---\n")
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.delete_server_btn.setEnabled(False)
        self.reinstall_btn.setEnabled(False)
        self.status_badge.setText("RUNNING")
        self.status_badge.setStyleSheet("""
            background-color: rgba(0, 255, 153, 0.15);
            color: #00FF99;
            border: 1px solid rgba(0, 255, 153, 0.4);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 800;
        """)

        java_path = self.config.get("java_path", "auto")
        folder_name = server_data.get("folder_name", server_data.get("name", "server"))
        max_ram = server_data.get("max_ram", self.config.get("max_ram", 2048))
        self.active_runner = LocalServerRunner(
            server_folder=folder_name,
            max_ram=max_ram,
            java_path=java_path
        )
        self.active_runner.log_output.connect(self._on_server_log)
        self.active_runner.process_finished.connect(self._on_server_stopped)
        self.active_runner.start()

    def _stop_server(self):
        if self.active_runner and self.active_runner.is_running:
            self.console_output.appendPlainText("\n[NeuraX] Sending stop command to server process...\n")
            self.active_runner.send_command("stop")

    def _reinstall_current_server(self):
        folder_name = self.run_server_combo.currentData()
        if not folder_name:
            QMessageBox.warning(self, "Selection Required", "Please select a server to reinstall.")
            return

        server_data = self.server_mgr.get_server(folder_name)
        if not server_data:
            return

        reply = QMessageBox.question(
            self, "Reinstall Server",
            f"Are you sure you want to reinstall server core '{server_data['name']}'? Your worlds and config files will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.reinstall_btn.setEnabled(False)
        self.console_output.appendPlainText(f"\n[NeuraX] Reinstalling server JAR core for {server_data['name']}...\n")

        self.worker = CreateServerWorker(
            server_mgr=self.server_mgr,
            name=server_data["name"],
            loader=server_data.get("loader", "Paper"),
            version=server_data.get("version", "1.20.4"),
            max_ram=server_data.get("max_ram", 2048),
            port=server_data.get("port", 25565),
            custom_folder_name=folder_name
        )
        self.worker.progress.connect(self._on_reinstall_progress)
        self.worker.finished.connect(self._on_reinstall_finished)
        self.worker.start()

    def _on_reinstall_progress(self, pct: int, msg: str):
        self.console_output.appendPlainText(f"[Reinstall {pct}%] {msg}")

    def _on_reinstall_finished(self, success: bool, msg: str):
        self.reinstall_btn.setEnabled(True)
        if success:
            self.console_output.appendPlainText(f"[NeuraX] Reinstall complete! {msg}\n")
            QMessageBox.information(self, "Reinstall Complete", msg)
        else:
            self.console_output.appendPlainText(f"[NeuraX] Reinstall failed! {msg}\n")
            QMessageBox.critical(self, "Reinstall Error", msg)

    def _delete_current_server(self):
        folder_name = self.run_server_combo.currentData()
        if not folder_name:
            QMessageBox.warning(self, "Selection Required", "Please select a server to delete.")
            return

        server_data = self.server_mgr.get_server(folder_name)
        if not server_data:
            return

        reply = QMessageBox.question(
            self, "Delete Server",
            f"Are you sure you want to permanently delete '{server_data['name']}'? All worlds, player data, and configurations will be permanently removed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.server_mgr.delete_server(folder_name)
        self._refresh_server_combos()
        QMessageBox.information(self, "Server Deleted", f"Server '{server_data['name']}' was deleted successfully.")

    def _on_server_log(self, text: str):
        self.console_output.appendPlainText(text)
        sb = self.console_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_server_stopped(self, exit_code: int):
        self.console_output.appendPlainText(f"\n--- Server stopped (Exit code: {exit_code}) ---\n")
        # Drop the dead runner so the next Start Server call gets a fresh
        # LocalServerRunner instead of calling into a stopped QObject.
        if self.active_runner is not None:
            self.active_runner.deleteLater()
            self.active_runner = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.delete_server_btn.setEnabled(True)
        self.reinstall_btn.setEnabled(True)
        self.status_badge.setText("OFFLINE")
        self.status_badge.setStyleSheet("""
            background-color: rgba(255, 51, 102, 0.15);
            color: #FF3366;
            border: 1px solid rgba(255, 51, 102, 0.4);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 800;
        """)

    def _send_command(self):
        cmd = self.cmd_input.text().strip()
        if cmd and self.active_runner and self.active_runner.is_running:
            self.active_runner.send_command(cmd)
            self.console_output.appendPlainText(f"> {cmd}")
            self.cmd_input.clear()

    def _clear_console(self):
        self.console_output.clear()

    def _load_file_tree(self):
        self.file_tree.clear()
        folder_name = self.editor_server_combo.currentData()
        if not folder_name:
            return

        server_dir = self.server_mgr.servers_dir / folder_name
        if not server_dir.exists():
            return

        root_item = QTreeWidgetItem(self.file_tree, [server_dir.name])
        root_item.setData(0, Qt.ItemDataRole.UserRole, str(server_dir))
        root_item.setIcon(0, IconEngine.get_icon("folder", QColor("#94A3B8"), QColor("#00F0FF"), 16))
        self._populate_tree_recursive(server_dir, root_item)
        root_item.setExpanded(True)

    def _populate_tree_recursive(self, directory: Path, parent_item: QTreeWidgetItem):
        try:
            entries = sorted(list(directory.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            for entry in entries:
                item = QTreeWidgetItem(parent_item, [entry.name])
                item.setData(0, Qt.ItemDataRole.UserRole, str(entry))
                if entry.is_dir():
                    item.setIcon(0, IconEngine.get_icon("folder", QColor("#94A3B8"), QColor("#00F0FF"), 16))
                    if entry.name not in (".git", "cache", "logs"):
                        self._populate_tree_recursive(entry, item)
                else:
                    item.setIcon(0, IconEngine.get_icon("terminal", QColor("#94A3B8"), QColor("#00F0FF"), 16))
        except Exception:
            pass

    def _on_tree_item_clicked(self, item: QTreeWidgetItem, column: int):
        file_path_str = item.data(0, Qt.ItemDataRole.UserRole)
        if not file_path_str:
            return
        path = Path(file_path_str)
        if path.is_file():
            self._open_file_in_editor(path)

    def _open_file_in_editor(self, path: Path):
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                QMessageBox.warning(self, "File Too Large", "Files larger than 2MB cannot be opened in the quick editor.")
                return

            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            self.current_editing_file = path
            self.file_path_lbl.setText(path.name)
            self.file_editor.setPlainText(content)
            self.save_file_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "Read Error", f"Could not read file:\n\n{e}")

    def _quick_open_file(self, filename: str):
        folder_name = self.editor_server_combo.currentData()
        if not folder_name:
            return
        target = self.server_mgr.servers_dir / folder_name / filename
        if target.exists():
            self._open_file_in_editor(target)
        else:
            QMessageBox.information(self, "File Not Found", f"File '{filename}' does not exist in this server folder yet.")

    def _quick_open_world(self):
        folder_name = self.editor_server_combo.currentData()
        if not folder_name:
            return
        world_dir = self.server_mgr.servers_dir / folder_name / "world"
        if world_dir.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(world_dir)))
        else:
            QMessageBox.information(self, "World Not Generated", "The 'world' folder has not been generated yet. Run the server once to generate world files.")

    def _save_current_file(self):
        if not self.current_editing_file:
            return
        try:
            content = self.file_editor.toPlainText()
            with open(self.current_editing_file, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "Saved", f"Changes to '{self.current_editing_file.name}' saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file:\n\n{e}")
