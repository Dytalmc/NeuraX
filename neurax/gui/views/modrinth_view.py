import os
import re
import json
import time
import html
import shutil
import tempfile
import requests
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt, QUrl, QTimer, QSize
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QScrollArea, QFrame, QDialog, QTreeWidget, QTreeWidgetItem,
    QProgressBar, QMessageBox, QSplitter, QTextBrowser,
    QHeaderView, QStackedWidget, QGridLayout, QApplication
)
from PyQt6.QtGui import QPixmap, QDesktopServices, QCursor, QImage, QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.widgets.animated_stacked_widget import AnimatedStackedWidget
from neurax.gui.views.new_server_view import AnimatedSubTabBar
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager, get_dot_neurax_dir
from neurax.core.instances import InstanceManager
from neurax.core.auth import AuthManager
from neurax.core.local_server import LocalServerManager
from neurax.core.logger import Logger
from neurax.core.ai.ai_mod_radar import AIModRadar
from neurax.core.modrinth import (
    ModrinthAPI, ModrinthSearchWorker, ModrinthAIRadarWorker,
    ModrinthInstallWorker, render_markdown_to_html, format_bytes,
    PROJECT_TYPES, LOADERS, SORT_OPTIONS
)

def get_modrinth_stylesheet(accent_color: str = "#00F0FF", mode: str = "dark") -> str:
    is_dark = (mode == "dark")
    color = QColor(accent_color)
    r, g, b = color.red(), color.green(), color.blue()
    hover_color = color.lighter(120).name()
    rgba_bg = f"rgba({r}, {g}, {b}, 0.12)"
    rgba_hover_bg = f"rgba({r}, {g}, {b}, 0.22)"

    if is_dark:
        bg_root = "#07090E"
        text_color = "#FFFFFF"
        card_bg = "rgba(14, 18, 26, 0.85)"
        card_border = "rgba(255, 255, 255, 0.08)"
        input_bg = "rgba(18, 22, 31, 0.85)"
        input_border = "rgba(255, 255, 255, 0.1)"
        btn_sec_bg = "rgba(255, 255, 255, 0.06)"
        btn_sec_border = "rgba(255, 255, 255, 0.12)"
        tree_bg = "#0B0E14"
        tree_header_bg = "#11151F"
    else:
        bg_root = "#FFFFFF"
        text_color = "#000000"
        card_bg = "#FFFFFF"
        card_border = "rgba(0, 0, 0, 0.12)"
        input_bg = "#FFFFFF"
        input_border = "rgba(0, 0, 0, 0.18)"
        btn_sec_bg = "#FFFFFF"
        btn_sec_border = "rgba(0, 0, 0, 0.18)"
        tree_bg = "#FFFFFF"
        tree_header_bg = "#F3F4F6"

    return f"""
    QDialog, QWidget#ModrinthViewRoot {{
        background-color: {bg_root};
        color: {text_color};
        font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
    }}
    QLabel {{
        color: {text_color};
    }}
    QFrame#ModrinthCard {{
        background-color: {card_bg};
        border: 1px solid {card_border};
        border-radius: 12px;
    }}
    QFrame#ModrinthCard:hover {{
        border: 1.5px solid {accent_color};
    }}
    QLineEdit, QComboBox {{
        background-color: {input_bg};
        border: 1.5px solid {input_border};
        border-radius: 8px;
        padding: 6px 12px;
        color: {text_color};
        font-size: 13px;
        font-weight: 600;
    }}
    QLineEdit:focus, QComboBox:focus, QComboBox:on {{
        border: 1.5px solid {accent_color};
    }}
    QPushButton#ModrinthPrimaryButton {{
        background-color: {accent_color};
        color: #FFFFFF;
        font-weight: 800;
        font-size: 13px;
        border: none;
        border-radius: 8px;
        padding: 8px 18px;
    }}
    QPushButton#ModrinthPrimaryButton:hover {{
        background-color: {hover_color};
        color: #FFFFFF;
    }}
    QPushButton#ModrinthSecondaryButton {{
        background-color: {btn_sec_bg};
        border: 1px solid {btn_sec_border};
        color: {text_color};
        font-weight: 600;
        border-radius: 8px;
        padding: 6px 14px;
        font-size: 12px;
    }}
    QPushButton#ModrinthSecondaryButton:hover {{
        background-color: {rgba_bg};
        color: {accent_color};
        border-color: {accent_color};
    }}
    QTreeWidget {{
        background-color: {tree_bg};
        color: {text_color};
        border: 1px solid {card_border};
        border-radius: 8px;
        padding: 4px;
        outline: none;
    }}
    QHeaderView::section {{
        background-color: {tree_header_bg};
        color: {accent_color};
        font-weight: bold;
        padding: 8px;
        border: 1px solid {card_border};
    }}
    QTreeWidget::item {{
        padding: 8px 6px;
        border-bottom: 1px solid {card_border};
        color: {text_color};
    }}
    QTreeWidget::item:hover {{
        background-color: {rgba_bg};
        color: {text_color};
    }}
    QTreeWidget::item:selected {{
        background-color: {rgba_hover_bg};
        color: {text_color};
        font-weight: bold;
    }}
    """

TYPE_BADGE_STYLES = {
    "MOD": "background-color: rgba(0, 240, 255, 0.15); color: #00F0FF; border: 1px solid rgba(0, 240, 255, 0.4);",
    "MODPACK": "background-color: rgba(59, 130, 246, 0.15); color: #3B82F6; border: 1px solid rgba(59, 130, 246, 0.4);",
    "RESOURCEPACK": "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; border: 1px solid rgba(245, 158, 11, 0.4);",
    "SHADER": "background-color: rgba(236, 72, 153, 0.15); color: #EC4899; border: 1px solid rgba(236, 72, 153, 0.4);",
    "PLUGIN": "background-color: rgba(139, 92, 246, 0.15); color: #8B5CF6; border: 1px solid rgba(139, 92, 246, 0.4);",
    "DATAPACK": "background-color: rgba(16, 185, 129, 0.15); color: #10B981; border: 1px solid rgba(16, 185, 129, 0.4);"
}

class ImageLoaderThread(QThread):
    image_loaded = pyqtSignal(QPixmap)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            res = requests.get(self.url, timeout=5)
            if res.status_code == 200:
                pix = QPixmap()
                pix.loadFromData(res.content)
                if not pix.isNull():
                    self.image_loaded.emit(pix)
        except Exception:
            pass


def _safe_set_pixmap(label: QLabel, pixmap: QPixmap, size: int) -> None:
    """Apply a scaled pixmap to a QLabel, swallowing the race-condition crash.

    ImageLoaderThread emits its signal asynchronously on the GUI thread after a
    background HTTP request. By the time the signal fires, the card/dialog that
    owned the QLabel may already have been destroyed (e.g. the user clicked
    another project, or closed the inspector popup). In that case PyQt6 raises:

        RuntimeError: wrapped C/C++ object of type QLabel has been deleted

    This helper wraps the call in a try/except so the UI stays responsive
    instead of crashing mid-search.
    """
    try:
        scaled = pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setPixmap(scaled)
    except (RuntimeError, TypeError):
        # Label was garbage-collected between signal emit and dispatch — safe
        # to ignore. The pixmap is discarded and the next-launched card will
        # start its own loader thread.
        pass


class FetchProjectDataWorker(QThread):
    details_fetched = pyqtSignal(dict)
    versions_fetched = pyqtSignal(list)

    def __init__(self, project_id_or_slug: str):
        super().__init__()
        self.target_id = project_id_or_slug

    def run(self):
        try:
            details = ModrinthAPI.get_project(self.target_id)
            if details:
                self.details_fetched.emit(details)
        except Exception:
            pass

        try:
            versions = ModrinthAPI.get_project_versions(self.target_id)
            self.versions_fetched.emit(versions or [])
        except Exception:
            self.versions_fetched.emit([])


class ModrinthProjectCard(GlassCard):
    """High-Performance Project Card with live icon loader, AI score badge, and vector styling."""
    clicked = pyqtSignal(dict)

    def __init__(self, project_data: dict, accent_color: str = "#00F0FF", parent=None):
        super().__init__(parent)
        self.setObjectName("ModrinthCard")
        self.project_data = dict(project_data)
        self.accent_color = accent_color
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.img_thread = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        # Icon Label with Vector Default Fallback
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(56, 56)
        self.icon_lbl.setStyleSheet("background-color: #0A0D14; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 10px;")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(IconEngine.get_pixmap("modrinth", QColor(accent_color), 36))
        layout.addWidget(self.icon_lbl)

        icon_url = self.project_data.get("icon_url")
        if icon_url:
            self.img_thread = ImageLoaderThread(icon_url)
            self.img_thread.image_loaded.connect(
                lambda p: _safe_set_pixmap(self.icon_lbl, p, 56)
            )
            self.img_thread.start()

        col = QVBoxLayout()
        col.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        title_str = self.project_data.get("title") or self.project_data.get("slug") or "Untitled"
        title_lbl = QLabel(title_str)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: 800;")
        top_row.addWidget(title_lbl)

        ptype = str(self.project_data.get("project_type", "mod")).upper()
        badge_style = TYPE_BADGE_STYLES.get(ptype, TYPE_BADGE_STYLES["MOD"])
        badge = QLabel(ptype)
        badge.setStyleSheet(f"{badge_style} border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 800;")
        top_row.addWidget(badge)

        # AI Evaluation Grade Badge
        downloads = self.project_data.get("downloads", 0)
        ai_eval = AIModRadar.evaluate_project_impact(self.project_data.get("slug", ""), ptype, downloads)
        ai_badge = QLabel(ai_eval["grade"])
        ai_badge.setStyleSheet("background-color: rgba(0, 255, 153, 0.12); color: #00FF99; border: 1px solid rgba(0, 255, 153, 0.3); border-radius: 4px; padding: 2px 6px; font-size: 9px; font-weight: 800;")
        top_row.addWidget(ai_badge)

        top_row.addStretch()
        col.addLayout(top_row)

        desc_str = self.project_data.get("description", "")
        if desc_str:
            desc_lbl = QLabel(desc_str)
            desc_lbl.setStyleSheet("font-size: 12px;")
            desc_lbl.setWordWrap(True)
            col.addWidget(desc_lbl)

        bottom_row = QHBoxLayout()
        author = self.project_data.get("author", "Creator")
        follows = self.project_data.get("follows", 0)
        meta_lbl = QLabel(f"By <b style='color: {self.accent_color};'>{author}</b>  •  Downloads: {downloads:,}  •  Follows: {follows:,}")
        meta_lbl.setStyleSheet("font-size: 11px;")
        bottom_row.addWidget(meta_lbl)
        bottom_row.addStretch()

        col.addLayout(bottom_row)
        layout.addLayout(col, stretch=1)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.project_data)
        super().mousePressEvent(event)


class ModrinthProjectDialog(QDialog):
    """Full Modrinth project inspector with rich HTML description, metadata, instant versions list, and installer."""

    def __init__(self, project_data: dict, instance_mgr: InstanceManager = None, server_mgr: LocalServerManager = None, accent_color: str = "#00F0FF", config: ConfigManager = None, parent=None):
        super().__init__(parent)
        self.project_data = dict(project_data)
        self.instance_mgr = instance_mgr
        self.server_mgr = server_mgr
        self.accent_color = accent_color
        self.config = config
        self.logger = Logger.get_instance()
        self.install_worker = None
        self.fetch_worker = None
        self.versions_cache = []
        self.img_thread = None

        self.setStyleSheet(get_modrinth_stylesheet(self.accent_color))
        self.target_id = self.project_data.get("id") or self.project_data.get("project_id") or self.project_data.get("slug")
        title = self.project_data.get("title") or self.target_id or "Project Details"
        self.setWindowTitle(f"Modrinth — {title}")
        self.resize(880, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Card
        header_card = GlassCard()
        header_card.setObjectName("ModrinthCard")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(16, 14, 16, 14)
        h_layout.setSpacing(16)

        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(64, 64)
        self.icon_lbl.setStyleSheet("background: #0A0D14; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px;")
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(IconEngine.get_pixmap("modrinth", QColor(accent_color), 40))
        h_layout.addWidget(self.icon_lbl)

        icon_url = self.project_data.get("icon_url")
        if icon_url:
            self.img_thread = ImageLoaderThread(icon_url)
            self.img_thread.image_loaded.connect(
                lambda p: _safe_set_pixmap(self.icon_lbl, p, 64)
            )
            self.img_thread.start()

        info_col = QVBoxLayout()
        info_col.setSpacing(4)

        title_row = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 19px; font-weight: 900; color: #FFFFFF;")
        title_row.addWidget(title_lbl)

        ptype = str(self.project_data.get("project_type", "mod")).upper()
        badge_style = TYPE_BADGE_STYLES.get(ptype, TYPE_BADGE_STYLES["MOD"])
        badge = QLabel(ptype)
        badge.setStyleSheet(f"{badge_style} border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 800;")
        title_row.addWidget(badge)
        title_row.addStretch()
        info_col.addLayout(title_row)

        author = self.project_data.get("author", "Unknown Creator")
        downloads = self.project_data.get("downloads", 0)
        follows = self.project_data.get("follows", 0)
        sub_lbl = QLabel(f"By <b style='color: {self.accent_color};'>{author}</b>  •  Downloads: {downloads:,}  •  Follows: {follows:,}")
        sub_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        info_col.addWidget(sub_lbl)

        desc_short = self.project_data.get("description", "")
        if desc_short:
            short_lbl = QLabel(desc_short)
            short_lbl.setStyleSheet("color: #E2E8F0; font-size: 12px;")
            short_lbl.setWordWrap(True)
            info_col.addWidget(short_lbl)

        h_layout.addLayout(info_col, stretch=1)
        layout.addWidget(header_card)

        # Target Destination Bar
        target_card = GlassCard()
        target_card.setObjectName("ModrinthCard")
        t_layout = QHBoxLayout(target_card)
        t_layout.setContentsMargins(16, 10, 16, 10)
        t_layout.setSpacing(10)

        t_lbl = QLabel("Target Destination:")
        t_lbl.setStyleSheet(f"color: {self.accent_color}; font-weight: bold;")
        t_layout.addWidget(t_lbl)
        
        self.target_type_combo = QComboBox()
        self.target_type_combo.addItems(["Instance (Client)", "Local Server"])
        
        saved_type = self.config.get("modrinth_target_type", "Instance (Client)") if self.config else "Instance (Client)"
        type_idx = self.target_type_combo.findText(saved_type)
        if type_idx >= 0:
            self.target_type_combo.setCurrentIndex(type_idx)

        self.target_type_combo.currentTextChanged.connect(self._on_target_type_changed)
        t_layout.addWidget(self.target_type_combo)

        s_lbl = QLabel("Select:")
        s_lbl.setStyleSheet("color: #94A3B8;")
        t_layout.addWidget(s_lbl)
        
        self.target_folder_combo = QComboBox()
        self.target_folder_combo.currentIndexChanged.connect(self._on_target_folder_changed)
        t_layout.addWidget(self.target_folder_combo, stretch=1)

        layout.addWidget(target_card)
        self._populate_target_folders()

        # Sub-Tab Navigation Bar
        self.sub_tab_bar = AnimatedSubTabBar([
            ("zap", "Available Versions & Files"),
            ("terminal", "Project Description & Docs")
        ], parent=self)
        self.sub_tab_bar.tab_changed.connect(self._on_sub_tab_changed)
        layout.addWidget(self.sub_tab_bar)

        self.tab_stacked = AnimatedStackedWidget(self)

        # Tab 0: Versions Panel & Installer
        v_widget = QWidget()
        v_layout = QVBoxLayout(v_widget)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(10)

        v_filter_row = QHBoxLayout()
        v_filter_row.setSpacing(10)

        self.v_search_input = QLineEdit()
        self.v_search_input.setPlaceholderText("Filter versions by tag or game version...")
        self.v_search_input.textChanged.connect(self._filter_versions_tree)
        v_filter_row.addWidget(self.v_search_input, stretch=1)

        self.v_loader_combo = QComboBox()
        self.v_loader_combo.addItem("All Loaders")
        self.v_loader_combo.currentTextChanged.connect(self._filter_versions_tree)
        v_filter_row.addWidget(self.v_loader_combo)

        self.v_game_ver_combo = QComboBox()
        self.v_game_ver_combo.addItem("All Game Versions")
        self.v_game_ver_combo.currentTextChanged.connect(self._filter_versions_tree)
        v_filter_row.addWidget(self.v_game_ver_combo)

        reload_v_btn = QPushButton(" Reload Versions")
        reload_v_btn.setObjectName("ModrinthSecondaryButton")
        reload_v_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        reload_v_btn.setIconSize(QSize(14, 14))
        reload_v_btn.clicked.connect(self._fetch_remote_data)
        v_filter_row.addWidget(reload_v_btn)

        v_layout.addLayout(v_filter_row)

        self.versions_tree = QTreeWidget()
        self.versions_tree.setColumnCount(5)
        self.versions_tree.setHeaderLabels(["Version Name / Tag", "Game Versions", "Loaders", "File Size", "Release Type"])
        self.versions_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.versions_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.versions_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.versions_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.versions_tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.versions_tree.itemDoubleClicked.connect(self._install_selected_version)
        v_layout.addWidget(self.versions_tree)

        v_btn_row = QHBoxLayout()
        v_btn_row.addStretch()
        self.install_btn = QPushButton(" Install Selected Version")
        self.install_btn.setObjectName("ModrinthPrimaryButton")
        self.install_btn.setIcon(IconEngine.get_icon("download", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        self.install_btn.setIconSize(QSize(14, 14))
        self.install_btn.clicked.connect(self._install_selected_version)
        v_btn_row.addWidget(self.install_btn)
        v_layout.addLayout(v_btn_row)

        self.tab_stacked.addWidget(v_widget)

        # Tab 1: Rich HTML Description Browser
        self.desc_browser = QTextBrowser()
        self.desc_browser.setOpenExternalLinks(True)
        self.desc_browser.setStyleSheet("""
            QTextBrowser {
                background-color: #0A0D14;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 12px;
            }
        """)
        body_raw = self.project_data.get("body") or self.project_data.get("description") or "Fetching full project description..."
        self.desc_browser.setHtml(render_markdown_to_html(body_raw, self.accent_color))
        self.tab_stacked.addWidget(self.desc_browser)

        layout.addWidget(self.tab_stacked, stretch=1)

        # Download Progress
        self.install_progress = QProgressBar()
        self.install_progress.setFixedHeight(6)
        self.install_progress.setTextVisible(False)
        self.install_progress.setValue(0)
        self.install_progress.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255, 255, 255, 0.08); border-radius: 3px; border: none; }}
            QProgressBar::chunk {{ background: {self.accent_color}; border-radius: 3px; }}
        """)
        self.install_progress.setVisible(False)
        layout.addWidget(self.install_progress)

        self.install_status_lbl = QLabel("")
        self.install_status_lbl.setStyleSheet(f"color: {self.accent_color}; font-size: 11px; font-weight: bold;")
        self.install_status_lbl.setVisible(False)
        layout.addWidget(self.install_status_lbl)

        # Footer Status & Actions
        footer = QHBoxLayout()
        self.status_lbl = QLabel("Fetching versions from Modrinth API...")
        self.status_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-style: italic;")
        footer.addWidget(self.status_lbl, stretch=1)

        slug = self.project_data.get("slug") or self.target_id
        self.web_btn = QPushButton(" View on Modrinth.com")
        self.web_btn.setObjectName("ModrinthSecondaryButton")
        self.web_btn.setIcon(IconEngine.get_icon("globe", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        self.web_btn.setIconSize(QSize(14, 14))
        self.web_btn.clicked.connect(self._open_web_page)
        footer.addWidget(self.web_btn)

        close_btn = QPushButton("Close")
        close_btn.setObjectName("ModrinthSecondaryButton")
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)

        layout.addLayout(footer)

        self._fetch_remote_data()

    def _on_sub_tab_changed(self, index: int):
        self.tab_stacked.slide_to_index(index)

    def _on_target_type_changed(self, text: str):
        if self.config:
            self.config.set("modrinth_target_type", text)
        self._populate_target_folders()

    def _on_target_folder_changed(self, index: int):
        if index < 0 or not self.config:
            return
        folder_name = self.target_folder_combo.itemData(index)
        if not folder_name:
            return
        target_type = self.target_type_combo.currentText()
        if target_type.startswith("Instance"):
            self.config.set("modrinth_target_instance", folder_name)
        else:
            self.config.set("modrinth_target_server", folder_name)

    def _populate_target_folders(self):
        self.target_folder_combo.blockSignals(True)
        self.target_folder_combo.clear()
        target_type = self.target_type_combo.currentText()

        saved_inst = self.config.get("modrinth_target_instance", "") if self.config else ""
        if not saved_inst and self.config:
            saved_inst = self.config.get("selected_instance", "Default")

        saved_srv = self.config.get("modrinth_target_server", "") if self.config else ""

        select_idx = 0

        if target_type.startswith("Instance"):
            if self.instance_mgr:
                instances = self.instance_mgr.list_instances()
                for idx, inst in enumerate(instances):
                    self.target_folder_combo.addItem(f"{inst['name']} ({inst.get('loader', 'Vanilla')} {inst.get('version', '')})", inst['folder_name'])
                    if inst['folder_name'] == saved_inst:
                        select_idx = idx
        else:
            if self.server_mgr:
                servers = self.server_mgr.list_servers()
                for idx, srv in enumerate(servers):
                    self.target_folder_combo.addItem(f"{srv['name']} ({srv.get('loader', 'Vanilla')} {srv.get('version', '')})", srv['folder_name'])
                    if srv['folder_name'] == saved_srv:
                        select_idx = idx

        if self.target_folder_combo.count() > 0:
            self.target_folder_combo.setCurrentIndex(select_idx)
            folder_name = self.target_folder_combo.itemData(select_idx)
            if folder_name and self.config:
                if target_type.startswith("Instance"):
                    self.config.set("modrinth_target_instance", folder_name)
                else:
                    self.config.set("modrinth_target_server", folder_name)

        self.target_folder_combo.blockSignals(False)

    def _fetch_remote_data(self):
        self.status_lbl.setText("Connecting to Modrinth API...")
        self.fetch_worker = FetchProjectDataWorker(self.target_id)
        self.fetch_worker.details_fetched.connect(self._on_details_fetched)
        self.fetch_worker.versions_fetched.connect(self._on_versions_fetched)
        self.fetch_worker.start()

    def _on_details_fetched(self, details: dict):
        if not details:
            return
        self.project_data.update(details)
        body_md = details.get("body") or details.get("description") or ""
        if body_md:
            self.desc_browser.setHtml(render_markdown_to_html(body_md, self.accent_color))

        icon_url = details.get("icon_url")
        if icon_url and not getattr(self, "_icon_updated", False):
            self._icon_updated = True
            self.img_thread = ImageLoaderThread(icon_url)
            self.img_thread.image_loaded.connect(
                lambda p: _safe_set_pixmap(self.icon_lbl, p, 64)
            )
            self.img_thread.start()

    def _on_versions_fetched(self, versions: list):
        self.versions_cache = versions or []
        self.status_lbl.setText(f"Loaded {len(self.versions_cache)} version file(s).")

        all_loaders = set()
        all_game_vers = set()
        for v in self.versions_cache:
            for l in v.get("loaders", []):
                all_loaders.add(l.capitalize())
            for gv in v.get("game_versions", []):
                all_game_vers.add(gv)

        self.v_loader_combo.blockSignals(True)
        self.v_game_ver_combo.blockSignals(True)

        self.v_loader_combo.clear()
        self.v_loader_combo.addItem("All Loaders")
        for l in sorted(all_loaders):
            self.v_loader_combo.addItem(l)

        self.v_game_ver_combo.clear()
        self.v_game_ver_combo.addItem("All Game Versions")
        for gv in sorted(all_game_vers, reverse=True):
            self.v_game_ver_combo.addItem(gv)

        self.v_loader_combo.blockSignals(False)
        self.v_game_ver_combo.blockSignals(False)

        self._filter_versions_tree()

    def _filter_versions_tree(self):
        self.versions_tree.clear()
        search_text = self.v_search_input.text().strip().lower()
        sel_loader = self.v_loader_combo.currentText()
        sel_game_ver = self.v_game_ver_combo.currentText()

        for v in self.versions_cache:
            v_name = v.get("name") or v.get("version_number") or "Version"
            v_num = v.get("version_number", "")
            loaders = v.get("loaders", [])
            game_vers = v.get("game_versions", [])
            v_type = v.get("version_type", "release").upper()

            files = v.get("files", [])
            primary_file = files[0] if files else {}
            f_size = format_bytes(primary_file.get("size", 0)) if primary_file else "Unknown"

            if search_text:
                corpus = f"{v_name} {v_num} {' '.join(loaders)} {' '.join(game_vers)}".lower()
                if search_text not in corpus:
                    continue

            if sel_loader != "All Loaders" and sel_loader.lower() not in [l.lower() for l in loaders]:
                continue

            if sel_game_ver != "All Game Versions" and sel_game_ver not in game_vers:
                continue

            loaders_str = ", ".join(l.capitalize() for l in loaders[:4])
            game_vers_str = ", ".join(game_vers[:3])
            if len(game_vers) > 3:
                game_vers_str += f" (+{len(game_vers)-3})"

            item = QTreeWidgetItem([
                f"{v_name} ({v_num})",
                game_vers_str,
                loaders_str,
                f_size,
                v_type
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, v)
            self.versions_tree.addTopLevelItem(item)

        if self.versions_tree.topLevelItemCount() > 0:
            self.versions_tree.setCurrentItem(self.versions_tree.topLevelItem(0))

    def _install_selected_version(self):
        curr_item = self.versions_tree.currentItem()
        if not curr_item:
            QMessageBox.warning(self, "Selection Required", "Please select a version to install.")
            return

        v_data = curr_item.data(0, Qt.ItemDataRole.UserRole)
        if not v_data:
            return

        files = v_data.get("files", [])
        primary_file = None
        for f in files:
            if f.get("primary"):
                primary_file = f
                break
        if not primary_file and files:
            primary_file = files[0]

        if not primary_file or not primary_file.get("url"):
            QMessageBox.warning(self, "File Error", "No valid download file found for this version.")
            return

        file_url = primary_file.get("url")
        file_name = primary_file.get("filename") or os.path.basename(file_url)

        target_type_raw = self.target_type_combo.currentText()
        target_folder = self.target_folder_combo.currentData()

        if not target_folder:
            QMessageBox.warning(self, "Target Required", "Please select a valid target instance or server destination.")
            return

        project_type = str(self.project_data.get("project_type", "mod")).lower()

        if project_type == "modpack" and target_type_raw.startswith("Instance"):
            target_type = "modpack_instance"
        elif target_type_raw.startswith("Instance"):
            target_type = "instance"
        else:
            target_type = "server"

        self.install_btn.setEnabled(False)
        self.install_progress.setVisible(True)
        self.install_progress.setValue(0)
        self.install_status_lbl.setVisible(True)
        self.install_status_lbl.setText("Initiating download...")

        self.install_worker = ModrinthInstallWorker(
            file_url=file_url,
            file_name=file_name,
            target_type=target_type,
            target_folder_name=target_folder,
            project_type=project_type,
            instance_mgr=self.instance_mgr,
            server_mgr=self.server_mgr
        )
        self.install_worker.progress.connect(self._on_install_progress)
        self.install_worker.finished.connect(self._on_install_finished)
        self.install_worker.start()

    def _on_install_progress(self, pct: int, status: str):
        self.install_progress.setValue(pct)
        self.install_status_lbl.setText(status)

    def _on_install_finished(self, success: bool, msg: str):
        self.install_btn.setEnabled(True)
        if success:
            self.install_progress.setValue(100)
            self.install_status_lbl.setText("Installation complete!")
            QMessageBox.information(self, "Installation Complete", msg)
        else:
            self.install_progress.setValue(0)
            self.install_status_lbl.setText("Installation failed.")
            QMessageBox.critical(self, "Installation Error", msg)

    def _open_web_page(self):
        ptype = str(self.project_data.get("project_type", "mod")).lower()
        slug = self.project_data.get("slug") or self.target_id
        url = f"https://modrinth.com/{ptype}/{slug}"
        QDesktopServices.openUrl(QUrl(url))


class ModrinthView(QWidget):
    """Primary Modrinth Hub View with 0-Token AI Radar pipeline, instant live-search on typing, category filters, and launcher theme integration."""

    # Strong references to retired ModrinthSearchWorker QThreads, kept until
    # each one's C++ thread actually finishes. Prevents
    # "QThread: Destroyed while thread '' is still running" when the user
    # types fast enough to spawn overlapping searches.
    _retired_workers: list = []

    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager = None, auth_mgr: AuthManager = None, main_window = None, parent = None):
        super().__init__(parent)
        self.setObjectName("ModrinthViewRoot")
        self.config = config
        self.instance_mgr = instance_mgr
        self.auth_mgr = auth_mgr
        self.main_window = main_window
        self.logger = Logger.get_instance()
        self.server_mgr = LocalServerManager(config.neurax_dir) if config else None

        self.accent_color = self.config.get("accent_color", "#00F0FF") if self.config else "#00F0FF"
        mode = self.config.get("theme_mode", "dark") if self.config else "dark"
        self.setStyleSheet(get_modrinth_stylesheet(self.accent_color, mode))

        if self.config:
            self.config.config_changed.connect(self._on_config_changed)

        self.search_worker = None
        self.radar_worker = None
        self.current_offset = 0
        self.page_limit = 20
        self.total_hits = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        header.setSpacing(10)

        title_col = QVBoxLayout()
        title = QLabel("Modrinth Hub & AI Radar")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_col.addWidget(title)

        subtitle = QLabel("Browse 100,000+ Mods, Modpacks, Resource Packs, Shaders & Plugins with Real-Time AI Monitor")
        subtitle.setStyleSheet("font-size: 12px;")
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()

        refresh_btn = QPushButton(" Refresh Hub")
        refresh_btn.setObjectName("ModrinthSecondaryButton")
        refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        refresh_btn.setIconSize(QSize(14, 14))
        refresh_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        refresh_btn.clicked.connect(self._do_search)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # AI Radar Live Notification Banner Card
        self.radar_card = GlassCard()
        self.radar_card.setObjectName("ModrinthCard")
        r_layout = QHBoxLayout(self.radar_card)
        r_layout.setContentsMargins(16, 10, 16, 10)
        r_layout.setSpacing(12)

        self.r_icon = QLabel()
        self.r_icon.setFixedSize(20, 20)
        self.r_icon.setPixmap(IconEngine.get_pixmap("ai_radar", QColor(self.accent_color), 20))
        r_layout.addWidget(self.r_icon)

        self.radar_status_lbl = QLabel("AI Mod Radar: Scanning Modrinth release pipeline in real-time...")
        self.radar_status_lbl.setStyleSheet(f"color: {self.accent_color}; font-size: 12px; font-weight: bold;")
        r_layout.addWidget(self.radar_status_lbl, stretch=1)

        layout.addWidget(self.radar_card)

        # Search & Filter Controls Card
        filter_card = GlassCard()
        filter_card.setObjectName("ModrinthCard")
        f_layout = QVBoxLayout(filter_card)
        f_layout.setContentsMargins(16, 12, 16, 12)
        f_layout.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search mods, modpacks, shaders, plugins, resourcepacks...")
        
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(350)
        self.search_timer.timeout.connect(lambda: self._do_search(offset=0))
        self.search_input.textChanged.connect(lambda: self.search_timer.start(350))
        
        search_row.addWidget(self.search_input, stretch=1)
        f_layout.addLayout(search_row)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(10)

        filters_row.addWidget(QLabel("Category:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(PROJECT_TYPES.keys()))
        self.type_combo.currentTextChanged.connect(lambda: self._do_search(offset=0))
        filters_row.addWidget(self.type_combo)

        filters_row.addWidget(QLabel("Loader:"))
        self.loader_combo = QComboBox()
        self.loader_combo.addItems(LOADERS)
        self.loader_combo.currentTextChanged.connect(lambda: self._do_search(offset=0))
        filters_row.addWidget(self.loader_combo)

        filters_row.addWidget(QLabel("Game Ver:"))
        self.version_combo = QComboBox()
        self.version_combo.addItem("All")
        for v in ["1.21.4", "1.21.1", "1.20.4", "1.20.1", "1.19.4", "1.18.2", "1.16.5", "1.12.2", "1.8.9"]:
            self.version_combo.addItem(v)
        self.version_combo.currentTextChanged.connect(lambda: self._do_search(offset=0))
        filters_row.addWidget(self.version_combo)

        filters_row.addWidget(QLabel("Sort By:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(list(SORT_OPTIONS.keys()))
        self.sort_combo.currentTextChanged.connect(lambda: self._do_search(offset=0))
        filters_row.addWidget(self.sort_combo)

        filters_row.addStretch()
        f_layout.addLayout(filters_row)

        layout.addWidget(filter_card)

        # Progress bar
        self.search_progress = QProgressBar()
        self.search_progress.setFixedHeight(4)
        self.search_progress.setMinimum(0)
        self.search_progress.setMaximum(0)
        self.search_progress.setTextVisible(False)
        self.search_progress.setStyleSheet(f"""
            QProgressBar {{ background: rgba(255, 255, 255, 0.08); border-radius: 2px; border: none; }}
            QProgressBar::chunk {{ background: {self.accent_color}; border-radius: 2px; }}
        """)
        self.search_progress.setVisible(False)
        layout.addWidget(self.search_progress)

        # Results Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.scroll_widget)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        self.results_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area, stretch=1)

        # Pagination Footer
        page_footer = QHBoxLayout()
        self.prev_btn = QPushButton(" Previous")
        self.prev_btn.setObjectName("ModrinthSecondaryButton")
        self.prev_btn.setIcon(IconEngine.get_icon("chevron_left", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        self.prev_btn.setIconSize(QSize(14, 14))
        self.prev_btn.clicked.connect(self._prev_page)
        page_footer.addWidget(self.prev_btn)

        self.page_info_lbl = QLabel("Page 1")
        self.page_info_lbl.setStyleSheet("color: #E2E8F0; font-weight: bold; font-size: 13px;")
        page_footer.addWidget(self.page_info_lbl)

        self.next_btn = QPushButton("Next ")
        self.next_btn.setObjectName("ModrinthSecondaryButton")
        self.next_btn.setIcon(IconEngine.get_icon("chevron_right", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        self.next_btn.setIconSize(QSize(14, 14))
        self.next_btn.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.next_btn.clicked.connect(self._next_page)
        page_footer.addWidget(self.next_btn)

        page_footer.addStretch()
        self.results_count_lbl = QLabel("Showing 0 projects")
        self.results_count_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        page_footer.addWidget(self.results_count_lbl)

        layout.addLayout(page_footer)

        if self.config:
            self.config.config_changed.connect(self._on_config_changed)

        # Start AI Radar
        self.radar_worker = ModrinthAIRadarWorker(poll_interval=60)
        self.radar_worker.radar_detected.connect(self._on_radar_detected)
        self.radar_worker.start()

        # Initial Search
        self._do_search(offset=0)

    def _on_config_changed(self, key: str, value: object):
        if key == "accent_color":
            self.accent_color = str(value)
            self.setStyleSheet(get_modrinth_stylesheet(self.accent_color))
            self.r_icon.setPixmap(IconEngine.get_pixmap("ai_radar", QColor(self.accent_color), 20))
            self.search_progress.setStyleSheet(f"""
                QProgressBar {{ background: rgba(255, 255, 255, 0.08); border-radius: 2px; border: none; }}
                QProgressBar::chunk {{ background: {self.accent_color}; border-radius: 2px; }}
            """)
            self.radar_status_lbl.setStyleSheet(f"color: {self.accent_color}; font-size: 12px; font-weight: bold;")

    def _do_search(self, offset: int = 0):
        # Retire the previous search worker, if any, the same way SkinView does:
        # disconnect its results_ready signal so a late completion can't call
        # back into this widget, then park it on a class-level retirement list
        # and schedule its deleteLater() when its finished signal fires. This
        # prevents the "QThread: Destroyed while thread '' is still running"
        # warning that the launcher would otherwise emit when rapid typing
        # creates overlapping Modrinth searches.
        if self.search_worker is not None:
            prev = self.search_worker
            self.search_worker = None
            try:
                prev.results_ready.disconnect(self._on_search_results)
            except (TypeError, RuntimeError):
                pass
            ModrinthView._retired_workers.append(prev)

            def _retire_finished():
                try:
                    ModrinthView._retired_workers.remove(prev)
                except ValueError:
                    pass
                prev.deleteLater()

            try:
                prev.finished.connect(_retire_finished)
            except (TypeError, RuntimeError):
                ModrinthView._retired_workers.remove(prev)
                prev.deleteLater()

        self.current_offset = max(0, offset)
        self.search_progress.setVisible(True)

        query = self.search_input.text().strip()
        ptype = self.type_combo.currentText()
        loader = self.loader_combo.currentText()
        ver = self.version_combo.currentText()
        sort_by = self.sort_combo.currentText()

        self.search_worker = ModrinthSearchWorker(
            query=query,
            project_type=ptype,
            loader=loader,
            version=ver,
            sort_by=sort_by,
            limit=self.page_limit,
            offset=self.current_offset
        )
        self.search_worker.results_ready.connect(self._on_search_results)
        self.search_worker.start()

    def _on_search_results(self, data: dict):
        self.search_progress.setVisible(False)

        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        hits = data.get("hits", [])
        self.total_hits = data.get("total_hits", len(hits))

        if not hits:
            empty_card = GlassCard()
            empty_card.setObjectName("ModrinthCard")
            e_layout = QVBoxLayout(empty_card)
            e_layout.setContentsMargins(30, 30, 30, 30)
            lbl = QLabel("No Modrinth Projects Found\nTry adjusting your search query or category/loader filters.")
            lbl.setStyleSheet("color: #94A3B8; font-size: 14px; font-weight: bold;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e_layout.addWidget(lbl)
            self.results_layout.addWidget(empty_card)
        else:
            for item_data in hits:
                card = ModrinthProjectCard(item_data, accent_color=self.accent_color)
                card.clicked.connect(self._on_card_clicked)
                self.results_layout.addWidget(card)

        current_page = (self.current_offset // self.page_limit) + 1
        total_pages = max(1, (self.total_hits + self.page_limit - 1) // self.page_limit)

        self.page_info_lbl.setText(f"Page {current_page} of {total_pages}")
        self.results_count_lbl.setText(f"Showing {len(hits)} of {self.total_hits:,} projects")

        self.prev_btn.setEnabled(self.current_offset > 0)
        self.next_btn.setEnabled(self.current_offset + self.page_limit < self.total_hits)

    def _prev_page(self):
        if self.current_offset >= self.page_limit:
            self._do_search(offset=self.current_offset - self.page_limit)

    def _next_page(self):
        if self.current_offset + self.page_limit < self.total_hits:
            self._do_search(offset=self.current_offset + self.page_limit)

    def _on_card_clicked(self, project_data: dict):
        self.logger.user_action(f"Opened Modrinth project inspector: '{project_data.get('title') or project_data.get('slug')}'")
        dialog = ModrinthProjectDialog(
            project_data=project_data,
            instance_mgr=self.instance_mgr,
            server_mgr=self.server_mgr,
            accent_color=self.accent_color,
            config=self.config,
            parent=self
        )
        dialog.exec()

    def _on_radar_detected(self, hits: list, summary: str):
        if summary:
            self.radar_status_lbl.setText(summary)

    def _on_config_changed(self, key: str, value: object):
        if key in ("accent_color", "theme_mode"):
            self.accent_color = self.config.get("accent_color", "#00F0FF")
            mode = self.config.get("theme_mode", "dark")
            self.setStyleSheet(get_modrinth_stylesheet(self.accent_color, mode))
