<<<<<<< HEAD
"""Version Manifest & AI Radar — NeuraX Launcher.

This is the fully-rewritten version of the original
``versions_view.py``. The previous version had a QListWidget that
silently refused to render any rows on slow startups because the
chunk-pump path was the only thing that ever called ``addItems`` and
its QTimer could be deferred indefinitely by the surrounding event
loop. The rewrite below:

  * reads the manifest directly on the GUI thread (cached in memory),
  * renders the picker synchronously for the first batch so the user
    never sees an empty card,
  * shows a non-interactive "empty" hint when the active filter
    combination matches zero entries,
  * keeps the AI Version Radar card working independently of the
    picker (so a manifest fetch failure doesn't blank the radar).

The visual style is intentionally aligned with the rest of the
launcher: a ``GlassCard`` header, a 2-row QHBoxLayout of checkboxes
with QCheckBox + ``ChipFilterStyle`` QSS, a single action button row
("Create Instance from Selected" + a hint label), and finally the
picker itself sitting in a ``GlassCard`` with a 320 px minimum height.
"""
from __future__ import annotations

from typing import List, Optional, Set

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QMessageBox, QDialog,
    QAbstractItemView, QFrame,
)

from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager
=======
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QCheckBox, QComboBox, QMessageBox, QDialog
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager, get_dot_neurax_dir
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
from neurax.core.instances import InstanceManager
from neurax.core.versions import VersionManager
from neurax.core.launcher import LaunchWorker
from neurax.core.auth import AuthManager
<<<<<<< HEAD
from neurax.core.ai.ai_version_radar import AIVersionRadarWorker
from neurax.core.logger import Logger
from neurax.gui.views.instances_view import InstanceDialog


# ---------------------------------------------------------------------------
# QSS — kept in the same file so the visual identity of the tab is
# self-contained. Sub-classes inside the launcher reuse the same tokens
# (``--accent``, ``--muted``) so theming flows through.
# ---------------------------------------------------------------------------
_VERSIONS_TAB_QSS = """
QCheckBox#VersionFilter {
    color: #C7D0DD;
    font-size: 12px;
    font-weight: 600;
    spacing: 6px;
    padding: 4px 6px;
}
QCheckBox#VersionFilter:hover {
    color: #FFFFFF;
}
QCheckBox#VersionFilter::indicator {
    width: 14px;
    height: 14px;
    border: 1.4px solid rgba(255, 255, 255, 0.35);
    border-radius: 4px;
    background: rgba(255, 255, 255, 0.04);
}
QCheckBox#VersionFilter::indicator:checked {
    background: %(accent)s;
    border: 1.4px solid %(accent)s;
}
QListWidget#VersionList {
    background: transparent;
    border: none;
    outline: 0;
    color: #C7D0DD;
    font-size: 13px;
}
QListWidget#VersionList::item {
    padding: 8px 12px;
    border-radius: 6px;
    margin: 1px 4px;
}
QListWidget#VersionList::item:hover {
    background: rgba(255, 255, 255, 0.05);
    color: #FFFFFF;
}
QListWidget#VersionList::item:selected {
    background: rgba(%(accent_rgb)s, 0.20);
    color: #FFFFFF;
}
QLabel#EmptyHint {
    color: #64748B;
    font-size: 12px;
    font-style: italic;
    padding: 10px 14px;
}
"""


def _hex_to_rgb_str(hex_color: str) -> str:
    """Convert ``#RRGGBB`` (or ``#AARRGGBB``) to a comma-separated RGB string."""
    s = hex_color.lstrip("#")
    if len(s) == 8:  # AARRGGBB
        s = s[2:]
    if len(s) != 6:
        return "0, 240, 255"
    try:
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        return f"{r}, {g}, {b}"
    except ValueError:
        return "0, 240, 255"


class VersionsView(QWidget):
    """Version Manifest + AI Radar tab."""

    # Emitted when the user double-clicks / clicks a version, so the
    # outer window can react (e.g. switch to the Play tab).
    version_picked = pyqtSignal(str)

    def __init__(
        self,
        config: ConfigManager,
        instance_mgr: Optional[InstanceManager] = None,
        auth_mgr: Optional[AuthManager] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
=======
from neurax.core.ai.ai_version_radar import AIVersionRadar, AIVersionRadarWorker
from neurax.core.logger import Logger
from neurax.gui.views.instances_view import InstanceDialog

class VersionsView(QWidget):
    """View to explore Mojang version manifest with live 0-Token AI Version Radar, filter checkboxes, direct instance creation, and double-tap launch to global directory."""

    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager = None, auth_mgr: AuthManager = None, parent=None):
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.auth_mgr = auth_mgr or getattr(parent, "auth_mgr", None)
        self.main_window = parent
        self.logger = Logger.get_instance()
        self.version_mgr = VersionManager.get_instance(config.neurax_dir / "cache")
<<<<<<< HEAD
        self.launch_worker: Optional[LaunchWorker] = None
        self._ai_radar_worker: Optional[AIVersionRadarWorker] = None

        # Cache the icon so every QListWidgetItem shares one QIcon —
        # adds a few hundred fewer refcount hops on first paint.
        accent = self.config.get("accent_color", "#00F0FF")
        self._version_icon = IconEngine.get_icon("versions", QColor("#8A94A6"), QColor(accent), 16)

        # The chunk pump (kept for >200-entry manifests) — null when
        # the synchronous fast path is in use.
        self._chunk_timer: Optional[QTimer] = None
        self._pending_versions: List[str] = []
        self._versions_chunk: int = 50

        self._build_ui()
        self._wire_signals()
        # Render once, now. The synchronous fast path means the list is
        # never blank on the first paint — even on a slow first read.
        QTimer.singleShot(0, self.refresh_versions)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
=======
        self.launch_worker = None
        self.ai_radar_worker = None

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

<<<<<<< HEAD
        accent = self.config.get("accent_color", "#00F0FF")
        accent_rgb = _hex_to_rgb_str(accent)
        self.setStyleSheet(_VERSIONS_TAB_QSS % {"accent": accent, "accent_rgb": accent_rgb})

        # ---------- Header row ----------
=======
        # Header Row
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        header = QHBoxLayout()
        title = QLabel("Version Manifest & AI Radar")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton(" Refresh Manifest")
        refresh_btn.setObjectName("SecondaryButton")
<<<<<<< HEAD
        refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
=======
        refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor("#00F0FF"), 14))
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        refresh_btn.setIconSize(QSize(14, 14))
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh_versions)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

<<<<<<< HEAD
        # ---------- AI Radar card ----------
=======
        # 0-Token AI Version Radar Panel
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
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
<<<<<<< HEAD
        self._set_badge_style("monitor")
=======
        self.ai_status_badge.setStyleSheet("""
            background-color: rgba(0, 255, 153, 0.15);
            color: #00FF99;
            border: 1px solid rgba(0, 255, 153, 0.4);
            border-radius: 6px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 800;
        """)
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        ai_header.addWidget(self.ai_status_badge)
        ai_layout.addLayout(ai_header)

        self.ai_info_lbl = QLabel("Monitoring Mojang piston-meta & official mod loader APIs...")
        self.ai_info_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.ai_info_lbl.setWordWrap(True)
        ai_layout.addWidget(self.ai_info_lbl)
<<<<<<< HEAD
        layout.addWidget(self.ai_card)

        # ---------- Filter checkboxes ----------
        self.cb_releases = self._make_filter_cb("Releases", "show_releases", True)
        self.cb_snapshots = self._make_filter_cb("Snapshots", "show_snapshots", False)
        self.cb_beta = self._make_filter_cb("Beta", "show_beta", False)
        self.cb_alpha = self._make_filter_cb("Alpha", "show_alpha", False)
        self.cb_indev = self._make_filter_cb("Indev/Infdev", "show_indev", False)
        self.cb_aprilfools = self._make_filter_cb("April Fools", "show_aprilfools", False)
        self.cb_historic = self._make_filter_cb("Historic", "show_historic", False)

        row1 = QHBoxLayout()
=======

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
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        row1.addWidget(self.cb_releases)
        row1.addWidget(self.cb_snapshots)
        row1.addWidget(self.cb_beta)
        row1.addWidget(self.cb_alpha)
        row1.addStretch()
<<<<<<< HEAD
        row2 = QHBoxLayout()
=======
        opts_col.addLayout(row1)

        row2 = QHBoxLayout()
        self.cb_indev = QCheckBox("Indev/Infdev")
        self.cb_indev.setChecked(self.config.get("show_indev", False))
        self.cb_aprilfools = QCheckBox("April Fools")
        self.cb_aprilfools.setChecked(self.config.get("show_aprilfools", False))
        self.cb_historic = QCheckBox("Historic")
        self.cb_historic.setChecked(self.config.get("show_historic", False))
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        row2.addWidget(self.cb_indev)
        row2.addWidget(self.cb_aprilfools)
        row2.addWidget(self.cb_historic)
        row2.addStretch()
<<<<<<< HEAD
        layout.addLayout(row1)
        layout.addLayout(row2)

        for cb in (
            self.cb_releases, self.cb_snapshots, self.cb_beta, self.cb_alpha,
            self.cb_indev, self.cb_aprilfools, self.cb_historic,
        ):
            cb.toggled.connect(self._on_option_changed)

        # ---------- Action row ----------
        action_row = QHBoxLayout()
        action_row.addStretch()
        create_btn = QPushButton(" Create Instance from Selected")
=======
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
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        create_btn.setObjectName("PrimaryButton")
        create_btn.setIcon(IconEngine.get_icon("plus", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        create_btn.setIconSize(QSize(14, 14))
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self.create_instance_from_selected)
<<<<<<< HEAD
        action_row.addWidget(create_btn)
        hint_lbl = QLabel("Tip: double-click a version to launch it in the global directory.")
        hint_lbl.setStyleSheet("color: #64748B; font-size: 11px; font-style: italic;")
        action_row.addWidget(hint_lbl)
        action_row.addStretch()
        layout.addLayout(action_row)

        # ---------- Picker card (the heart of the tab) ----------
        card = GlassCard()
        card.setMinimumHeight(360)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(6, 6, 6, 6)

        self.version_list = QListWidget()
        self.version_list.setObjectName("VersionList")
        self.version_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.version_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.version_list.itemDoubleClicked.connect(self.launch_version_global)
        self.version_list.itemClicked.connect(self._on_version_clicked)
        card_layout.addWidget(self.version_list)
        layout.addWidget(card, 1)

    def _make_filter_cb(self, label: str, key: str, default: bool) -> QCheckBox:
        cb = QCheckBox(label)
        cb.setObjectName("VersionFilter")
        cb.setChecked(self.config.get(key, default))
        return cb

    def _set_badge_style(self, mode: str) -> None:
        if mode == "new_release":
            self.ai_status_badge.setStyleSheet(
                "background-color: rgba(0, 240, 255, 0.18); color: #00F0FF;"
                " border: 1.5px solid #00F0FF; border-radius: 6px; padding: 3px 8px;"
                " font-size: 10px; font-weight: 900;"
            )
        elif mode == "new_snapshot":
            self.ai_status_badge.setStyleSheet(
                "background-color: rgba(255, 215, 0, 0.25); color: #FFD700;"
                " border: 1.5px solid #FFD700; border-radius: 6px; padding: 3px 8px;"
                " font-size: 10px; font-weight: 900;"
            )
        else:
            self.ai_status_badge.setStyleSheet(
                "background-color: rgba(0, 255, 153, 0.15); color: #00FF99;"
                " border: 1px solid rgba(0, 255, 153, 0.4); border-radius: 6px;"
                " padding: 3px 8px; font-size: 10px; font-weight: 800;"
            )

    # -------------------------------------------------------------- Wiring
    def _wire_signals(self) -> None:
        self.version_mgr.versions_updated.connect(self._on_ai_version_update)
        self.version_mgr.start_monitoring(poll_interval=300)

        # Dedicated AI radar worker so new-version detection runs even
        # when the version_mgr is busy.
=======
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
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self._ai_radar_worker = AIVersionRadarWorker(poll_interval=300)
        self._ai_radar_worker.versions_updated.connect(self._on_ai_version_update)
        self._ai_radar_worker.new_version_detected.connect(self._on_new_version_detected)
        self._ai_radar_worker.start()

<<<<<<< HEAD
    # -------------------------------------------------------------- Slots
    def _on_ai_version_update(self, info: dict) -> None:
=======
        self.load_versions()

    def _on_ai_version_update(self, info: dict):
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        latest_rel = info.get("latest_release", "")
        latest_snap = info.get("latest_snapshot", "")
        latest_af = info.get("latest_aprilfools", "24w14a")
        loaders = info.get("loaders", {})
        rel_status = info.get("release_status", "")
        snap_status = info.get("snapshot_status", "")
        stability = info.get("stability_index", 0)
<<<<<<< HEAD

        parts: List[str] = []
=======
        snap_stability = info.get("snapshot_stability", 0)

        parts = []
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        if latest_rel:
            parts.append(f"Latest Release: {latest_rel}" + (f" [{rel_status}]" if rel_status else ""))
        if latest_snap:
            parts.append(f"Latest Snapshot: {latest_snap}" + (f" [{snap_status}]" if snap_status else ""))
        if latest_af:
            parts.append(f"April Fools: {latest_af}")
<<<<<<< HEAD
        loader_str = " \u2022 ".join(
            f"{k}: {v}" for k, v in loaders.items() if v and v not in ("Latest",)
        )
        if loader_str:
            parts.append(f"Loaders: {loader_str}")
        if stability:
            parts.append(f"Release Stability Index: {stability}/100")

        self.ai_info_lbl.setText("\n".join(parts))

        is_new_snap = bool(info.get("new_snapshot_detected"))
        is_new_rel = bool(info.get("new_release_detected"))
        if is_new_rel and latest_rel:
            self.ai_status_badge.setText(f"\U0001F195 NEW RELEASE: {latest_rel}")
            self._set_badge_style("new_release")
        elif is_new_snap and latest_snap:
            self.ai_status_badge.setText(f"\U0001F514 NEW SNAPSHOT: {latest_snap}")
            self._set_badge_style("new_snapshot")
        else:
            self.ai_status_badge.setText("AI VERSION RADAR ACTIVE")
            self._set_badge_style("monitor")

    def _on_new_version_detected(self, version_id: str, version_type: str) -> None:
        self.logger.info(f"AI Version Radar: auto-adding {version_type} '{version_id}' to manifest")
        self.version_mgr.fetch_manifest(force_refresh=True)
        if version_type == "snapshot" and not self.cb_snapshots.isChecked():
            self.cb_snapshots.setChecked(True)
        else:
            self.refresh_versions()
        self.version_list.scrollToTop()

    def _on_option_changed(self) -> None:
        for cb, key in (
            (self.cb_releases, "show_releases"),
            (self.cb_snapshots, "show_snapshots"),
            (self.cb_beta, "show_beta"),
            (self.cb_alpha, "show_alpha"),
            (self.cb_indev, "show_indev"),
            (self.cb_aprilfools, "show_aprilfools"),
            (self.cb_historic, "show_historic"),
        ):
            self.config.set(key, cb.isChecked())
        self.refresh_versions()

    def _on_version_clicked(self, item: QListWidgetItem) -> None:
        # Single click = select. Double click = launch. Selection is
        # the single source of truth for the picked version.
        if item is None:
            return
        ver = item.data(Qt.ItemDataRole.UserRole)
        if ver:
            self.version_picked.emit(ver)

    # -------------------------------------------------------------- Loader
    def refresh_versions(self) -> None:
        self.logger.user_action("Clicked Refresh Version Manifest")
        self.version_mgr.fetch_manifest(force_refresh=True)
        self._populate_list()

    def _populate_list(self) -> None:
        """Repaint the picker from the current filter combination.

        The original chunk-pump path is preserved for very large
        manifests (>200 entries) so we don't stutter the GUI, but the
        first batch is added synchronously so the picker is never
        blank on first paint.
        """
        # Cancel any pending chunk pump from the previous call.
        if self._chunk_timer is not None:
            try:
                self._chunk_timer.stop()
            except Exception:
                pass
            self._chunk_timer = None

        self.version_list.clear()
=======

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
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        versions = self.version_mgr.get_filtered_versions(
            show_releases=self.cb_releases.isChecked(),
            show_snapshots=self.cb_snapshots.isChecked(),
            show_beta=self.cb_beta.isChecked(),
            show_alpha=self.cb_alpha.isChecked(),
            show_indev=self.cb_indev.isChecked(),
            show_aprilfools=self.cb_aprilfools.isChecked(),
<<<<<<< HEAD
            show_historic=self.cb_historic.isChecked(),
        )
        self.logger.info(f"VersionsView: populating list with {len(versions)} entries")

        if not versions:
            self._render_empty_state()
            return

        if len(versions) <= 200:
            self._add_batch(versions)
            return

        # Large manifest: first batch synchronously, then chunk-pump
        # the rest across QTimer ticks so the GUI keeps redrawing.
        first = versions[:200]
        self._add_batch(first)
        self._pending_versions = versions[200:]
        self._versions_chunk = max(50, len(self._pending_versions) // 16 or 50)
        self._chunk_timer = QTimer(self)
        self._chunk_timer.setSingleShot(True)
        self._chunk_timer.timeout.connect(self._pump_versions_chunk)
        self._chunk_timer.start(0)

    def _add_batch(self, batch) -> None:
        items: List[QListWidgetItem] = []
        for ver in batch:
            try:
                item = QListWidgetItem(f"Minecraft {ver}")
            except Exception:
                continue
            try:
                item.setIcon(self._version_icon)
                item.setData(Qt.ItemDataRole.UserRole, ver)
            except Exception:
                pass
            items.append(item)
        if items:
            try:
                self.version_list.addItems(items)
            except Exception as e:
                self.logger.warning(f"VersionsView: addItems failed: {e}")

    def _pump_versions_chunk(self) -> None:
        versions = self._pending_versions
        chunk = self._versions_chunk
        batch = versions[:chunk]
        if not batch:
            self._pending_versions = []
            self._chunk_timer = None
            return
        self._add_batch(batch)
        self._pending_versions = versions[chunk:]
        if self._pending_versions:
            try:
                if self._chunk_timer is not None:
                    self._chunk_timer.start(0)
            except Exception:
                self._chunk_timer = QTimer(self)
                self._chunk_timer.setSingleShot(True)
                self._chunk_timer.timeout.connect(self._pump_versions_chunk)
                self._chunk_timer.start(0)
        else:
            self._chunk_timer = None

    def _render_empty_state(self) -> None:
        any_filter = (
            self.cb_releases.isChecked()
            or self.cb_snapshots.isChecked()
            or self.cb_beta.isChecked()
            or self.cb_alpha.isChecked()
            or self.cb_indev.isChecked()
            or self.cb_aprilfools.isChecked()
            or self.cb_historic.isChecked()
        )
        if not any_filter:
            msg = "No filters enabled — tick at least one of Releases / Snapshots / etc."
        else:
            msg = (
                "No versions match the current filters. Try enabling more filter checkboxes, "
                "or click Refresh Manifest to re-download from Mojang."
            )
        item = QListWidgetItem(msg)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.version_list.addItem(item)

    # -------------------------------------------------------------- Picker
    def _selected_version(self) -> Optional[str]:
        item = self.version_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def create_instance_from_selected(self) -> None:
        selected_ver = self._selected_version() or "1.20.4"
=======
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

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.logger.user_action(f"Initiated instance creation from version '{selected_ver}'")
        dialog = InstanceDialog(
            self, config=self.config,
            title=f"New Instance ({selected_ver})",
            name=f"MC_{selected_ver}",
            version=selected_ver,
<<<<<<< HEAD
            jvm_args=self.config.get("jvm_args", ""),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        if data["name"] and self.instance_mgr:
            new_folder = self.instance_mgr.create_instance(
                name=data["name"],
                version=data["version"],
                loader=data["loader"],
                max_ram=data["max_ram"],
                java_path=data["java_path"],
                jvm_args=data["jvm_args"],
            )
            self.config.set("selected_instance", new_folder)
            self.logger.user_action(f"Created instance '{data['name']}' from version '{selected_ver}'")
            QMessageBox.information(self, "Instance Created", f"Instance '{data['name']}' created successfully.")

    def launch_version_global(self, item=None) -> None:
        # Switch to the Play tab so the user can watch the launch.
=======
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
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        main_win = getattr(self, "main_window", None) or self.window()
        if hasattr(main_win, "nav_bar") and main_win.nav_bar:
            main_win.nav_bar._on_btn_clicked(0)
        elif hasattr(main_win, "stacked_widget") and main_win.stacked_widget:
            main_win.stacked_widget.slide_to_index(0)

<<<<<<< HEAD
        version_id: Optional[str] = None
        if item is not None and hasattr(item, "data"):
            version_id = item.data(Qt.ItemDataRole.UserRole)
        if not version_id:
            current = self.version_list.currentItem()
            if current is not None and hasattr(current, "data"):
                version_id = current.data(Qt.ItemDataRole.UserRole)
=======
        version_id = None
        if item and hasattr(item, "data"):
            version_id = item.data(Qt.ItemDataRole.UserRole)
        if not version_id:
            version_id = self.version_dropdown.currentData()
        if not version_id:
            curr_item = self.version_list.currentItem()
            if curr_item:
                version_id = curr_item.data(Qt.ItemDataRole.UserRole)
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        if not version_id:
            version_id = "1.20.4"

        token = self.config.get("access_token", "0")
        auth_mode = self.config.get("auth_mode", "microsoft")
        if auth_mode == "microsoft" and (not token or token == "0"):
            QMessageBox.warning(
<<<<<<< HEAD
                self, "Sign-in Required",
                "Please sign in with your Microsoft account on the Play tab before launching.",
            )
            return

        self.version_picked.emit(version_id)
        if hasattr(main_win, "_start_launch"):
            try:
                main_win._start_launch(version_id)
                return
            except Exception as e:
                self.logger.warning(f"Main window refused _start_launch: {e}")
        # Fallback: spawn our own LaunchWorker so double-click still works
        # when the host window doesn't expose a launch entry point.
        try:
            instance_dir = self.config.neurax_dir / "instances" / "Default"
            self.launch_worker = LaunchWorker(
                username=self.config.get("username", "Player"),
                uuid=self.config.get("uuid", ""),
                token=token,
                version=version_id,
                game_dir=instance_dir,
                max_ram=int(self.config.get("max_ram_mb", 4096)),
                jvm_args=self.config.get("jvm_args", ""),
                custom_java=self.config.get("java_path", "auto"),
            )
            self.launch_worker.progress.connect(lambda *a: None)
            self.launch_worker.log_message.connect(lambda *a: None)
            self.launch_worker.finished.connect(lambda *a: None)
            self.launch_worker.start()
        except Exception as e:
            self.logger.warning(f"VersionsView: fallback launch failed: {e}")
=======
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
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
