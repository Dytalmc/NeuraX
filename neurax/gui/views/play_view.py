from datetime import datetime
import gc
import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QMessageBox, QPlainTextEdit, QCheckBox, QApplication, QFrame, QGridLayout, QDialog
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QVariantAnimation, QSize
from PyQt6.QtGui import QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.widgets.skin_view import SkinView
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager
from neurax.core.instances import InstanceManager
from neurax.core.launcher import LaunchWorker
from neurax.core.auth import AuthManager
from neurax.core.logger import Logger
from neurax.core.ai.ai_crash_analyzer import AICrashAnalyzer, CrashDiagnosticResult

def format_playtime(seconds: int) -> str:
    if not seconds or seconds <= 0:
        return "0m"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else: 
        return f"{secs}s"

class HoverPlayButton(QPushButton):
    """Custom Play Button with smooth responsive cyber-gradient and vector icon."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName("PlayButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(240, 68)
        self._accent_color = "#00F0FF"
        self._hover_val = 0.0
        
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        
        self.update_theme_color(self._accent_color)

    def update_theme_color(self, accent_color: str):
        self._accent_color = accent_color
        self._apply_style(self._hover_val)

    def _apply_style(self, hover_val: float):
        base_color = QColor(self._accent_color)

        r = int(base_color.red() + (255 - base_color.red()) * 0.25 * hover_val)
        g = int(base_color.green() + (255 - base_color.green()) * 0.25 * hover_val)
        b = int(base_color.blue() + (255 - base_color.blue()) * 0.25 * hover_val)

        top_color = QColor(r, g, b).name()
        bottom_color = base_color.darker(int(140 - 25 * hover_val)).name()
        border_color = QColor(r, g, b).lighter(int(105 + 35 * hover_val)).name()

<<<<<<< HEAD
        # Arial Black is requested — falls back to Impact then sans-serif
        # black-weight families if the platform lacks Arial Black.
        # ALL CAPS, bold, NOT italic, tight letter-spacing.
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.setStyleSheet(f"""
            QPushButton#PlayButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {top_color}, stop:1 {bottom_color});
                border: 2px solid {border_color};
                border-radius: 12px;
                color: #FFFFFF;
<<<<<<< HEAD
                font-family: 'Arial Black', 'Helvetica Black', 'Impact', 'Segoe UI Black', sans-serif;
                font-size: 26px;
                font-weight: 900;
                font-style: normal;
                text-transform: uppercase;
                letter-spacing: 1px;
                padding: 0 4px;
=======
                font-family: 'Segoe UI Black', 'Segoe UI', 'Inter', 'Arial Black', sans-serif;
                font-size: 24px;
                font-weight: 900;
                font-style: italic;
                letter-spacing: 4px;
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
            }}
            QPushButton#PlayButton:pressed {{
                background: {base_color.darker(160).name()};
                border-color: {base_color.name()};
                color: #FFFFFF;
            }}
            QPushButton#PlayButton:disabled {{
                background: #171A21;
                border-color: #2D3442;
                color: #64748B;
            }}
        """)

    def _on_anim_value(self, val):
        self._hover_val = float(val)
        self._apply_style(self._hover_val)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_val)
        self._anim.setEndValue(1.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._hover_val)
        self._anim.setEndValue(0.0)
        self._anim.start()
        super().leaveEvent(event)


class CrashReportDialog(QDialog):
    """Futuristic AI Crash Diagnostic & Fix Recommendation Modal."""

    def __init__(self, diag: CrashDiagnosticResult, accent_color: str = "#00F0FF", parent=None):
        super().__init__(parent)
        self.setWindowTitle("NeuraX AI — Crash Diagnostics & Auto-Remediation")
        self.resize(680, 480)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header_card = GlassCard()
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(18, 14, 18, 14)
        h_layout.setSpacing(6)

        title_lbl = QLabel(f"DIAGNOSTIC ANALYSIS: {diag.title}")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 900; color: #FF3366; letter-spacing: 0.5px;")
        h_layout.addWidget(title_lbl)

        cause_lbl = QLabel(f"Root Cause: {diag.root_cause}")
        cause_lbl.setStyleSheet("font-size: 13px; font-weight: 600;")
        cause_lbl.setWordWrap(True)
        h_layout.addWidget(cause_lbl)

        offending_lbl = QLabel(f"Offending Component: {diag.offending_component}")
        offending_lbl.setStyleSheet(f"color: {accent_color}; font-size: 12px; font-weight: bold;")
        h_layout.addWidget(offending_lbl)

        layout.addWidget(header_card)

        steps_card = GlassCard()
        s_layout = QVBoxLayout(steps_card)
        s_layout.setContentsMargins(18, 14, 18, 14)
        s_layout.setSpacing(10)

        step_hdr = QLabel("Recommended Step-by-Step Fix:")
        step_hdr.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {accent_color};")
        s_layout.addWidget(step_hdr)

        for i, step in enumerate(diag.solution_steps, 1):
            s_lbl = QLabel(f"{i}. {step}")
            s_lbl.setStyleSheet("font-size: 12px;")
            s_lbl.setWordWrap(True)
            s_layout.addWidget(s_lbl)

        layout.addWidget(steps_card, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setObjectName("SecondaryButton")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)


class PlayView(QWidget):
    """Main Primary Dashboard Page with dynamic centered play button & AI diagnostics drawer."""

    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager, auth_mgr: AuthManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.auth_mgr = auth_mgr
        self.logger = Logger.get_instance()
        self.launch_worker = None

        accent = self.config.get("accent_color", "#00F0FF")

        self.play_btn_container = QFrame()
        self.play_btn_container.setFixedSize(260, 90)
        self.play_btn_container.setStyleSheet("background: transparent; border: none;")

        self.play_btn = HoverPlayButton("PLAY", self.play_btn_container)
        self.play_btn.clicked.connect(self.launch_game)
        self.play_btn.update_theme_color(accent)

        profile_card = GlassCard()
        profile_card.setObjectName("GlassCard")
        profile_card.setFixedSize(280, 240)

        profile_layout = QVBoxLayout(profile_card)
        profile_layout.setContentsMargins(16, 14, 16, 14)
        profile_layout.setSpacing(8)

        self.skin_view = SkinView(config, view_mode="front")
        self.skin_view.setFixedHeight(100)
        profile_layout.addWidget(self.skin_view, alignment=Qt.AlignmentFlag.AlignCenter)

        user_row = QHBoxLayout()
        user_row.setContentsMargins(0, 0, 0, 0)
        user_row.setSpacing(8)

        token = self.config.get("access_token", "0")
        auth_mode = self.config.get("auth_mode", "microsoft")
        is_logged_in = (auth_mode == "microsoft" and token != "0")

        self.user_lbl = QLabel(self.config.get("username", "NeuraPlayer"))
        self.user_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        user_row.addWidget(self.user_lbl)

        user_row.addStretch()

        self.mode_badge = QLabel("MICROSOFT" if is_logged_in else "OFFLINE")
        self.mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_badge_style(accent, is_logged_in)
        user_row.addWidget(self.mode_badge)
        profile_layout.addLayout(user_row)

        inst_lbl = QLabel("Active Instance:")
        inst_lbl.setStyleSheet("font-size: 11px; font-weight: 600;")
        profile_layout.addWidget(inst_lbl)

        self.inst_combo = QComboBox()
        self.inst_combo.setFixedHeight(32)
        self.inst_combo.currentIndexChanged.connect(self._on_instance_changed)
        profile_layout.addWidget(self.inst_combo)

        self.inst_playtime_lbl = QLabel("Instance: 0m")
        self.inst_playtime_lbl.setStyleSheet("font-size: 11px;")
        profile_layout.addWidget(self.inst_playtime_lbl)

        self.total_playtime_lbl = QLabel("Total: 0m")
        self.total_playtime_lbl.setStyleSheet("font-size: 10px;")
        profile_layout.addWidget(self.total_playtime_lbl)

        self.console_drawer = QFrame()
        self.console_drawer.setObjectName("ConsoleDrawer")
        self.console_drawer.setMaximumHeight(0)
        self.console_drawer.setStyleSheet("""
            QFrame#ConsoleDrawer {
                background-color: rgba(10, 13, 19, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }
        """)

        console_layout = QVBoxLayout(self.console_drawer)
        console_layout.setContentsMargins(12, 10, 12, 10)
        console_layout.setSpacing(8)

        console_header = QHBoxLayout()
        console_title = QLabel("Diagnostic Output & AI Crash Engine")
        console_title.setStyleSheet("font-size: 13px; font-weight: bold;")
        console_header.addWidget(console_title)
        console_header.addStretch()

        self.ai_analyze_btn = QPushButton(" AI Diagnose Log")
        self.ai_analyze_btn.setObjectName("SecondaryButton")
        self.ai_analyze_btn.setFixedHeight(22)
        self.ai_analyze_btn.setIcon(IconEngine.get_icon("ai_radar", QColor("#94A3B8"), QColor(accent), 14))
        self.ai_analyze_btn.setIconSize(QSize(12, 12))
        self.ai_analyze_btn.clicked.connect(self._ai_diagnose_log)
        console_header.addWidget(self.ai_analyze_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        self.auto_scroll_cb = QCheckBox("Auto-scroll")
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.setStyleSheet("font-size: 11px;")
        console_header.addWidget(self.auto_scroll_cb, 0, Qt.AlignmentFlag.AlignVCenter)

        copy_btn = QPushButton(" Copy")
        copy_btn.setObjectName("SecondaryButton")
        copy_btn.setFixedHeight(22)
        copy_btn.setIcon(IconEngine.get_icon("copy", QColor("#8A94A6"), QColor(accent), 14))
        copy_btn.setIconSize(QSize(12, 12))
        copy_btn.clicked.connect(self._copy_logs)
        console_header.addWidget(copy_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        clear_btn = QPushButton(" Clear")
        clear_btn.setObjectName("SecondaryButton")
        clear_btn.setFixedHeight(22)
        clear_btn.setIcon(IconEngine.get_icon("trash", QColor("#8A94A6"), QColor("#FF3366"), 14))
        clear_btn.setIconSize(QSize(12, 12))
        clear_btn.clicked.connect(self._clear_logs)
        console_header.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        console_layout.addLayout(console_header)

        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumBlockCount(1500)
        self.log_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #05070B;
                color: #00FF99;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 6px;
                padding: 6px;
            }
        """)
        console_layout.addWidget(self.log_console)

        grid = QGridLayout(self)
        grid.setContentsMargins(20, 20, 20, 20)
        grid.setSpacing(15)

        grid.addWidget(self.play_btn_container, 0, 0, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(profile_card, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.console_drawer, 1, 0)

        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 0)

        self.refresh_instances()
        self.update_playtime_display()
        self.instance_mgr.instances_changed.connect(self.refresh_instances)
        self.config.config_changed.connect(self._on_config_changed)

        self.logger.signal_emitter.log_signal.connect(self._append_log)
        self.logger.info("NeuraX Engine Cyber Cockpit initialized.")

    def _update_badge_style(self, accent: str, is_logged_in: bool):
        c_color = QColor(accent)
        if is_logged_in:
            self.mode_badge.setStyleSheet(f"""
                background-color: rgba({c_color.red()}, {c_color.green()}, {c_color.blue()}, 0.15);
                color: {accent};
                border: 1px solid rgba({c_color.red()}, {c_color.green()}, {c_color.blue()}, 0.4);
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 800;
            """)
        else:
            self.mode_badge.setStyleSheet("""
                background-color: rgba(120, 120, 120, 0.12);
                border: 1px solid rgba(120, 120, 120, 0.3);
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: 800;
            """)

    def _ai_diagnose_log(self):
        log_content = self.log_console.toPlainText()
        diag = AICrashAnalyzer.analyze_log(log_content)
        dialog = CrashReportDialog(diag, self.config.get("accent_color", "#00F0FF"), self)
        dialog.exec()

    def _append_log(self, text: str):
        self.log_console.appendPlainText(text)
        if self.auto_scroll_cb.isChecked():
            sb = self.log_console.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _copy_logs(self):
        cb = QApplication.clipboard()
        if cb:
            cb.setText(self.log_console.toPlainText())
            self.logger.info("Logs copied to system clipboard.")

    def _clear_logs(self):
        self.log_console.clear()

    def toggle_console(self):
        is_open = self.console_drawer.maximumHeight() > 0
        target = 0 if is_open else 220
        self.anim = QPropertyAnimation(self.console_drawer, b"maximumHeight", self)
        self.anim.setDuration(250)
        self.anim.setStartValue(self.console_drawer.height())
        self.anim.setEndValue(target)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()

    def _on_config_changed(self, key: str, value: object):
        if key in ("username", "auth_mode", "access_token"):
            token = self.config.get("access_token", "0")
            auth_mode = self.config.get("auth_mode", "microsoft")
            is_logged_in = (auth_mode == "microsoft" and token != "0")
            self.user_lbl.setText(self.config.get("username", "NeuraPlayer"))
            self.mode_badge.setText("MICROSOFT" if is_logged_in else "OFFLINE")
            self._update_badge_style(self.config.get("accent_color", "#00F0FF"), is_logged_in)
            self.skin_view.reload_skin()
        elif key == "selected_instance":
            idx = self.inst_combo.findData(value)
            if idx >= 0 and idx != self.inst_combo.currentIndex():
                self.inst_combo.setCurrentIndex(idx)
            self.update_playtime_display()
        elif key == "accent_color":
            accent = str(value)
            self.play_btn.update_theme_color(accent)
            token = self.config.get("access_token", "0")
            auth_mode = self.config.get("auth_mode", "microsoft")
            self._update_badge_style(accent, auth_mode == "microsoft" and token != "0")
        elif key == "analytics":
            self.update_playtime_display()

    def refresh_instances(self):
        self.inst_combo.blockSignals(True)
        self.inst_combo.clear()
        instances = self.instance_mgr.list_instances()
        selected = self.config.get("selected_instance", "Default")
        selected_idx = 0
        for idx, inst in enumerate(instances):
            self.inst_combo.addItem(f"{inst['name']} ({inst['version']})", inst["folder_name"])
            if inst["folder_name"] == selected:
                selected_idx = idx
        self.inst_combo.setCurrentIndex(selected_idx)
        self.inst_combo.blockSignals(False)
        self.update_playtime_display()

    def _on_instance_changed(self, index: int):
        folder_name = self.inst_combo.currentData()
        if folder_name:
            self.config.set("selected_instance", folder_name)
            self.update_playtime_display()

    def update_playtime_display(self):
        analytics = self.config.get("analytics", {})
        folder_name = self.config.get("selected_instance", "Default")
        inst_data = self.instance_mgr.get_instance(folder_name)
        inst_name = inst_data.get("name", folder_name) if inst_data else folder_name

        inst_stats = analytics.get(inst_name, {})
        if not inst_stats and folder_name in analytics:
            inst_stats = analytics.get(folder_name, {})

        inst_sec = inst_stats.get("total_seconds", 0) if isinstance(inst_stats, dict) else 0

        tot_sec = 0
        for k, v in analytics.items():
            if isinstance(v, dict):
                tot_sec += v.get("total_seconds", 0)

        self.inst_playtime_lbl.setText(f"Instance: {format_playtime(inst_sec)}")
        self.total_playtime_lbl.setText(f"Total: {format_playtime(tot_sec)}")

    def launch_game(self, server_host: str = None, server_port: int = 25565):
        if self.launch_worker and self.launch_worker.isRunning():
            QMessageBox.information(self, "Game Running", "Minecraft is already launching or currently running.")
            return

        self.logger.user_action(f"Requested game launch for instance '{self.config.get('selected_instance')}'")

        if self.config.get("global_sync_enabled", False):
            ok, msg = self.instance_mgr.sync_global_data(self.config)
            self.logger.info(f"Pre-launch global sync: {msg}")

        self.play_btn.setEnabled(False)
        self.play_btn.setText("LAUNCHING...")

        self.launch_worker = LaunchWorker(
            config=self.config,
            instance_mgr=self.instance_mgr,
            auth_mgr=self.auth_mgr,
            server_host=server_host,
            server_port=server_port
        )
        self.launch_worker.progress.connect(self._on_launch_progress)
        self.launch_worker.game_started.connect(self._on_game_started)
        self.launch_worker.game_exited.connect(self._on_game_exited)
        self.launch_worker.error_occurred.connect(self._on_launch_error)
<<<<<<< HEAD
        # Per-file download / install log lines — show what file is
        # being downloaded right now inside the in-launcher log panel
        # (the green console drawer), like a real Minecraft launcher.
        try:
            self.launch_worker.log_message.connect(self._append_log)
        except Exception:
            pass
=======
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.launch_worker.start()

    def _on_launch_progress(self, percent: int, status_text: str, speed_text: str = ""):
        main_win = self.window()
        if hasattr(main_win, "status_bar"):
            main_win.status_bar.update_status(percent, status_text, speed_text)

    def _on_game_started(self):
        self.logger.info("Minecraft game process successfully launched.")
        self.play_btn.setText("IN GAME")
        main_win = self.window()
        if hasattr(main_win, "status_bar"):
            main_win.status_bar.update_status(100, "Game Running")

        if self.config.get("close_on_launch", False):
            if hasattr(main_win, "enter_background_mode"):
                main_win.enter_background_mode()
            else:
                main_win.hide()

    def _on_game_exited(self, exit_code: int):
        self.play_btn.setEnabled(True)
        self.play_btn.setText("PLAY")
        self.logger.info(f"Minecraft process exited with return code: {exit_code}")
        main_win = self.window()
        if hasattr(main_win, "status_bar"):
            main_win.status_bar.update_status(0, "Ready to launch")

        if self.config.get("close_on_launch", False):
            if hasattr(main_win, "exit_background_mode"):
                main_win.exit_background_mode()
            else:
                main_win.show()

        if exit_code != 0:
            log_content = self.log_console.toPlainText()
            diag = AICrashAnalyzer.analyze_log(log_content)
            if diag.is_crash:
                dialog = CrashReportDialog(diag, self.config.get("accent_color", "#00F0FF"), self)
                dialog.exec()

    def _on_launch_error(self, error_msg: str):
        self.play_btn.setEnabled(True)
        self.play_btn.setText("PLAY")
        self.logger.error(f"Launch failed: {error_msg}")
        main_win = self.window()
        if hasattr(main_win, "status_bar"):
            main_win.status_bar.update_status(0, "Ready to launch")
        QMessageBox.critical(self, "Launch Error", error_msg)
