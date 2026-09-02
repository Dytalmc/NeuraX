from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGridLayout, QFrame, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QPixmap, QDesktopServices, QCursor, QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager, get_dot_neurax_dir
from neurax.core.instances import InstanceManager
from neurax.core.logger import Logger

class GalleryScanWorker(QThread):
    """Scans one or more screenshots directories and emits a list of (path, source_label) tuples.

    Each result tuple is `(Path, str)` where `source_label` is a short,
    human-readable name for the directory the file came from (e.g. an instance
    name, or "Global" for the shared folder). The card UI uses this label to
    show which instance a screenshot belongs to.
    """
    scanned = pyqtSignal(list)

    def __init__(self, sources: list):
        """`sources` is a list of (Path, str) tuples — one per directory to scan."""
        super().__init__()
        self.sources = sources

    def run(self):
        files = []
        for directory, label in self.sources:
            if not directory or not directory.exists():
                continue
            try:
                for ext in ("*.png", "*.jpg", "*.jpeg"):
                    for p in directory.glob(ext):
                        if p.is_file():
                            files.append((p, label))
            except Exception:
                # One bad directory shouldn't kill the whole scan.
                continue
        # Sort newest-first across all sources, so the gallery feels consistent
        # even when the user has screenshots in multiple instances.
        files.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
        self.scanned.emit(files)


class ScreenshotCard(QFrame):
    def __init__(self, file_path: Path, source_label: str, delete_cb, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.source_label = source_label
        self.delete_cb = delete_cb
        self.pixmap = QPixmap(str(self.file_path))
        self.init_ui()

    def init_ui(self):
        self.setObjectName("GlassCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.img_lbl = QLabel()
        self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_lbl.setMinimumSize(200, 90)
        self.img_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.img_lbl.setStyleSheet("border-radius: 8px; background-color: #080A0F;")

        layout.addWidget(self.img_lbl)

        footer = QHBoxLayout()
        name_lbl = QLabel(self.file_path.name)
        name_lbl.setStyleSheet("font-size: 11px; font-weight: 600;")
        name_lbl.setToolTip(self.file_path.name)
        footer.addWidget(name_lbl, stretch=1)

        del_btn = QPushButton()
        del_btn.setIcon(IconEngine.get_icon("trash", QColor("#FF3366"), QColor("#FFFFFF"), 14))
        del_btn.setIconSize(QSize(14, 14))
        del_btn.setFixedSize(26, 26)
        del_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 51, 102, 0.15);
                border: 1px solid rgba(255, 51, 102, 0.4);
                border-radius: 6px;
            }
            QPushButton:hover {
                background: rgba(255, 51, 102, 0.4);
            }
        """)
        del_btn.clicked.connect(self._delete_file)
        footer.addWidget(del_btn)
        layout.addLayout(footer)

        # Source tag — small chip below the footer so the user can tell which
        # instance a screenshot came from. The shared "Global" folder gets the
        # same treatment so it doesn't look like an unattributed orphan.
        source_lbl = QLabel(self.source_label)
        source_lbl.setStyleSheet(
            "font-size: 10px; font-weight: 700; letter-spacing: 0.5px;"
            "color: #00F0FF; padding: 2px 6px;"
            "background: rgba(0, 240, 255, 0.1);"
            "border: 1px solid rgba(0, 240, 255, 0.3);"
            "border-radius: 4px;"
        )
        source_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        source_lbl.setToolTip(str(self.file_path.parent))
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.addWidget(source_lbl)
        source_row.addStretch()
        layout.addLayout(source_row)

        self.update_thumbnail()

    def update_thumbnail(self):
        if not self.pixmap.isNull():
            card_w = self.width() - 20
            w = max(200, card_w if card_w > 0 else self.img_lbl.width())
            h = int(w * 0.46)
            if h < 90:
                h = 90
            if h > 180:
                h = 180
            if (w, h) == getattr(self, "_last_scaled_size", None):
                return
            self._last_scaled_size = (w, h)
            if self.img_lbl.height() != h:
                self.img_lbl.setFixedHeight(h)
            scaled = self.pixmap.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.img_lbl.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_thumbnail()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.file_path)))
        super().mousePressEvent(event)

    def _delete_file(self):
        reply = QMessageBox.question(
            self, "Delete Screenshot", f"Delete screenshot '{self.file_path.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.file_path.unlink()
                self.delete_cb(self)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete screenshot: {e}")


class GalleryView(QWidget):
    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.logger = Logger.get_instance()
        self.cards = []
        self.current_cols = 2

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title = QLabel("Screenshot Gallery")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        title_col.addWidget(title)

        subtitle = QLabel("Browse screenshots from every instance and the shared Global folder")
        subtitle.setStyleSheet("font-size: 12px;")
        title_col.addWidget(subtitle)

        root_hint = QLabel(f"All sources under: {get_dot_neurax_dir()}")
        root_hint.setStyleSheet("font-size: 10px; color: #94A3B8;")
        root_hint.setToolTip(
            "Aggregated folders:\n"
            "  • ~/.neurax/screenshots/\n"
            "  • ~/.neurax/global/.minecraft/screenshots/\n"
            "  • ~/.neurax/instances/<name>/.minecraft/screenshots/"
        )
        title_col.addWidget(root_hint)

        header.addLayout(title_col)
        header.addStretch()

        accent = self.config.get("accent_color", "#00F0FF")
        open_folder_btn = QPushButton(" Open Screenshots Folder")
        open_folder_btn.setObjectName("SecondaryButton")
        open_folder_btn.setIcon(IconEngine.get_icon("folder", QColor("#94A3B8"), QColor(accent), 14))
        open_folder_btn.setIconSize(QSize(14, 14))
        open_folder_btn.clicked.connect(self._open_screenshots_folder)
        header.addWidget(open_folder_btn)

        refresh_btn = QPushButton(" Refresh")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        refresh_btn.setIconSize(QSize(14, 14))
        refresh_btn.clicked.connect(self.scan_screenshots)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.scroll_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(15)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll_area)

        self.status_lbl = QLabel("Scanning screenshots directory...")
        self.status_lbl.setStyleSheet("font-size: 12px; font-style: italic;")
        layout.addWidget(self.status_lbl)

        self.scan_screenshots()

    def _get_global_screenshots_dir(self) -> Path:
        """Shared screenshots folder used across all instances (no instance scope)."""
        return get_dot_neurax_dir() / "screenshots"

    def _get_screenshot_sources(self) -> list:
        """Return a list of (Path, label) tuples covering every screenshots directory
        the launcher knows about — all under the user's `.neurax` root:

        • `~/.neurax/screenshots/`                          (shared / global)
        • `~/.neurax/global/.minecraft/screenshots/`       (global instance)
        • `~/.neurax/instances/<folder>/.minecraft/screenshots/`  (per-instance)

        Labels are the on-disk folder names so the gallery directly reflects
        what's in the `.neurax` directory tree, and so two instances that
        happen to share a display name stay disambiguated automatically.
        """
        sources = []

        # 1. Shared "global" folder at the top of .neurax — the flat
        #    `screenshots/` location that the "Open Screenshots Folder"
        #    button opens. Created on demand so dropping files in there
        #    works without setup.
        global_dir = self._get_global_screenshots_dir()
        global_dir.mkdir(parents=True, exist_ok=True)
        sources.append((global_dir, "Global"))

        # 2. `~/.neurax/global/.minecraft/screenshots/` — the nested
        #    Minecraft-style layout that some installs use for the
        #    global/shared instance. Auto-created on demand.
        global_inst_dir = get_dot_neurax_dir() / "global" / ".minecraft" / "screenshots"
        global_inst_dir.mkdir(parents=True, exist_ok=True)
        sources.append((global_inst_dir, "global"))

        # 3. Every instance's own screenshots folder, labelled with its
        #    on-disk folder name (e.g. "Default", "Fabric - 2612",
        #    "FabulouslyOptimized-V1400-Beta6") so it always matches the
        #    directory listing under `~/.neurax/instances/`.
        if self.instance_mgr:
            try:
                instances = self.instance_mgr.list_instances()
            except Exception:
                instances = []
            for inst in instances:
                game_dir = inst.get("game_dir")
                folder_name = inst.get("folder_name") or ""
                if not game_dir or not folder_name:
                    continue
                sdir = Path(game_dir) / "screenshots"
                sources.append((sdir, folder_name))
        else:
            # Fallback: at minimum include the currently selected instance so
            # the gallery isn't empty just because the manager failed to load.
            selected = self.config.get("selected_instance", "Default")
            sdir = get_dot_neurax_dir() / "instances" / selected / ".minecraft" / "screenshots"
            sources.append((sdir, selected))

        return sources

    def _open_screenshots_folder(self):
        # The "Open Screenshots Folder" button now opens the shared global
        # folder, since the gallery aggregates from there. Users wanting a
        # specific instance's folder can navigate manually.
        sdir = self._get_global_screenshots_dir()
        sdir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(sdir)))

    def scan_screenshots(self):
        sources = self._get_screenshot_sources()
        self.status_lbl.setText(f"Scanning {len(sources)} screenshot folder(s)...")
        # Retire the previous worker, if any, the same way the skin view does —
        # it's a short-lived QThread but rapid refreshes can still race.
        if getattr(self, "worker", None) is not None:
            try:
                self.worker.scanned.disconnect(self._on_scanned)
            except (TypeError, RuntimeError):
                pass
            prev = self.worker
            self.worker = None
            prev.deleteLater()

        self.worker = GalleryScanWorker(sources)
        self.worker.scanned.connect(self._on_scanned)
        self.worker.start()

    def _on_scanned(self, files: list):
        # `files` is a list of (Path, source_label) tuples — see GalleryScanWorker.
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        self.cards.clear()

        if not files:
            card = GlassCard()
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(30, 30, 30, 30)
            card_layout.setSpacing(8)

            no_img_title = QLabel("No Screenshots Found")
            no_img_title.setStyleSheet("font-size: 16px; font-weight: bold;")
            no_img_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(no_img_title)

            sources = self._get_screenshot_sources()
            folder_lines = "\n".join(f"• {label}: {p}" for p, label in sources)
            no_img_desc = QLabel(
                f"Press F2 in Minecraft to capture screenshots.\n\nSearched folders:\n{folder_lines}"
            )
            no_img_desc.setStyleSheet("font-size: 13px;")
            no_img_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_img_desc.setWordWrap(True)
            card_layout.addWidget(no_img_desc)

            self.grid_layout.addWidget(card, 0, 0)
            self.status_lbl.setText("Found 0 screenshots.")
            return

        for p, source_label in files:
            card = ScreenshotCard(p, source_label=source_label, delete_cb=self._on_card_deleted)
            self.cards.append(card)

        self._relayout_grid()
        # Surface the source breakdown in the status line, e.g.
        # "Loaded 17 screenshot(s) across 3 instance(s)."
        unique_sources = {label for _, label in files}
        self.status_lbl.setText(
            f"Loaded {len(files)} screenshot(s) from {len(unique_sources)} source(s)."
        )

    def _relayout_grid(self):
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        cols = self.current_cols
        for i, card in enumerate(self.cards):
            r = i // cols
            c = i % cols
            self.grid_layout.addWidget(card, r, c)

    def _on_card_deleted(self, card: ScreenshotCard):
        if card in self.cards:
            self.cards.remove(card)
            card.deleteLater()
            self._relayout_grid()
            self.status_lbl.setText(f"Loaded {len(self.cards)} screenshot(s).")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        cols = 2
        if w > 1200:
            cols = 4
        elif w > 800:
            cols = 3
        else:
            cols = 2

        if cols != self.current_cols:
            self.current_cols = cols
            if self.cards:
                self._relayout_grid()
