"""
loader_versions_view.py — Loader Version Manager dialog
========================================================

A modal dialog that lets the user pick a specific software version of each
mod loader (Fabric Loader, Quilt Loader, Forge, NeoForge). The selection
is queued for re-install on the next launch and persisted as the user's
"pinned" version.

The dialog is reached from the Instances view header ("Loader Versions" button)
and is intentionally self-contained: it talks to `neurax.core.loader_versions`
and the launcher's ConfigManager.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFrame, QListWidget, QListWidgetItem, QMessageBox, QProgressBar,
    QApplication, QSizePolicy
)

from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.icons import IconEngine
from neurax.core import loader_versions


_LOADER_LABELS = {
    "fabric": "Fabric Loader",
    "quilt": "Quilt Loader",
    "forge": "Forge",
    "neoforge": "NeoForge",
}


class _LoaderFetchWorker(QThread):
    """Fetch the available versions for one loader off the UI thread."""
    finished_with_data = pyqtSignal(str, list)  # loader, list[str]

    def __init__(self, loader: str, parent=None):
        super().__init__(parent)
        self.loader = loader

    def run(self):
        try:
            versions = loader_versions.fetch_available_versions(self.loader)
        except Exception:
            versions = []
        self.finished_with_data.emit(self.loader, versions)


class _ReinstallWorker(QThread):
    """Wipe + queue the reinstall so it survives across launches."""
    finished_ok = pyqtSignal(str, str, str, list)  # loader, mc, target, removed
    failed = pyqtSignal(str)  # message

    def __init__(self, config, game_dir: Path, loader: str, mc_version: str, target: str, parent=None):
        super().__init__(parent)
        self.config = config
        self.game_dir = Path(game_dir)
        self.loader = loader
        self.mc_version = mc_version
        self.target = target

    def run(self):
        try:
            removed = loader_versions.wipe_and_queue_reinstall(
                self.config, self.game_dir, self.loader, self.mc_version, self.target
            )
            self.finished_ok.emit(self.loader, self.mc_version, self.target, removed)
        except Exception as e:
            self.failed.emit(str(e))


class LoaderVersionsDialog(QDialog):
    """Manage the per-loader software version. Lets the user:

      1. Pick a loader (Fabric / Quilt / Forge / NeoForge).
      2. See the currently installed + latest available version.
      3. Pick a specific version from the dropdown.
      4. Set it as the pinned version for the selected Minecraft version.

    On Save the dialog wipes old loader dirs under the selected instance's
    .minecraft/versions/ and queues a re-install on the next Play.
    """

    def __init__(self, parent=None, config=None, instance_data: Optional[dict] = None):
        super().__init__(parent)
        self.config = config
        self.instance_data = instance_data or {}
        self._fetch_workers: List[_LoaderFetchWorker] = []
        self._reinstall_worker: Optional[_ReinstallWorker] = None

        self.setWindowTitle("Loader Versions")
        self.resize(620, 560)
        self.setMinimumSize(540, 480)

        accent = (config.get("accent_color", "#00F0FF") if config else "#00F0FF")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        title = QLabel("Loader Version Manager")
        title.setStyleSheet("font-size: 20px; font-weight: 800; letter-spacing: 0.5px;")
        layout.addWidget(title)
        subtitle = QLabel(
            "Pin the exact software version of each loader you want to install. "
            "On the next launch NeuraX wipes the old loader profile and installs "
            "the version you pick here."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(subtitle)

        # --- Loader + Minecraft version card ---
        card = GlassCard()
        cv = QVBoxLayout(card)
        cv.setContentsMargins(16, 14, 16, 14)
        cv.setSpacing(10)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Loader:"))
        self.loader_combo = QComboBox()
        for loader_key, label in _LOADER_LABELS.items():
            self.loader_combo.addItem(label, loader_key)
        self.loader_combo.currentIndexChanged.connect(self._on_loader_changed)
        row1.addWidget(self.loader_combo, stretch=1)

        row1.addSpacing(8)
        row1.addWidget(QLabel("Minecraft:"))
        self.mc_combo = QComboBox()
        self.mc_combo.setMinimumWidth(160)
        self._populate_mc_versions()
        self.mc_combo.currentIndexChanged.connect(self._refresh_installed_label)
        row1.addWidget(self.mc_combo, stretch=1)
        cv.addLayout(row1)

        row2 = QHBoxLayout()
        self.installed_lbl = QLabel("Installed: —")
        self.installed_lbl.setStyleSheet("font-size: 12px; font-weight: 700;")
        row2.addWidget(self.installed_lbl)
        row2.addStretch()
        self.latest_lbl = QLabel("Latest upstream: —")
        self.latest_lbl.setStyleSheet("font-size: 12px; color: #00FF99; font-weight: 700;")
        row2.addWidget(self.latest_lbl)
        cv.addLayout(row2)
        layout.addWidget(card)

        # --- Picker card ---
        picker = GlassCard()
        pv = QVBoxLayout(picker)
        pv.setContentsMargins(16, 14, 16, 14)
        pv.setSpacing(10)

        pv.addWidget(QLabel("Select loader version to install on next launch:"))
        self.version_combo = QComboBox()
        self.version_combo.setMinimumHeight(34)
        self.version_combo.addItem("(latest available)", "")
        pv.addWidget(self.version_combo)

        # Refresh + clear pin row
        row3 = QHBoxLayout()
        refresh_btn = QPushButton(" Refresh List")
        refresh_btn.setObjectName("SecondaryButton")
        refresh_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        refresh_btn.setIconSize(QSize(14, 14))
        refresh_btn.clicked.connect(self._refresh_versions)
        row3.addWidget(refresh_btn)

        clear_btn = QPushButton(" Clear Pin")
        clear_btn.setObjectName("SecondaryButton")
        clear_btn.setIcon(IconEngine.get_icon("trash", QColor("#94A3B8"), QColor("#FF3366"), 14))
        clear_btn.setIconSize(QSize(14, 14))
        clear_btn.clicked.connect(self._clear_pin)
        row3.addWidget(clear_btn)

        row3.addStretch()
        self.pin_status_lbl = QLabel("No pin set — uses upstream latest")
        self.pin_status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        row3.addWidget(self.pin_status_lbl)
        pv.addLayout(row3)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        pv.addWidget(self.progress_bar)

        layout.addWidget(picker, stretch=1)

        # --- Buttons ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self.save_btn = QPushButton(" Apply on Next Launch")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setIcon(IconEngine.get_icon("save", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        self.save_btn.setIconSize(QSize(14, 14))
        self.save_btn.clicked.connect(self._apply)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        # Initial state.
        self._on_loader_changed(0)
        QApplication.processEvents()
        self._refresh_versions()

    # ------------------------------------------------------------------ helpers
    def _populate_mc_versions(self):
        self.mc_combo.clear()
        if self.instance_data:
            v = str(self.instance_data.get("version", "")).strip()
            if v:
                self.mc_combo.addItem(v, v)
                self.mc_combo.setCurrentIndex(0)
        # Try the version manager for known MC versions so the user can pick
        # a different MC even if this dialog was opened without an instance.
        try:
            from neurax.core.versions import VersionManager
            cache_dir = (self.config.neurax_dir / "cache") if self.config else Path("neurax_cache")
            vm = VersionManager.get_instance(cache_dir)
            for v in vm.get_filtered_versions(show_releases=True, show_snapshots=False, show_beta=False, show_alpha=False):
                if self.mc_combo.findData(v) < 0:
                    self.mc_combo.addItem(v, v)
        except Exception:
            pass

    def _on_loader_changed(self, _index: int):
        self._refresh_installed_label()
        self._refresh_versions()

    def _refresh_installed_label(self):
        loader_key = self.loader_combo.currentData() or ""
        mc_version = self.mc_combo.currentData() or ""
        pinned = loader_versions.get_desired_loader_version(self.config, loader_key, mc_version) if self.config else ""
        if pinned:
            self.pin_status_lbl.setText(f"Pinned: {pinned}")
            self.pin_status_lbl.setStyleSheet("color: #00FF99; font-size: 11px; font-weight: 800;")
        else:
            self.pin_status_lbl.setText("No pin set — uses upstream latest")
            self.pin_status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")

        # Installed (what's currently in the instance .minecraft/versions dir)
        if self.config and mc_version and self.instance_data:
            game_dir = Path(self.instance_data.get("game_dir", ""))
            try:
                from neurax.core.launcher import find_installed_loader_version
                installed = find_installed_loader_version(game_dir, loader_key, mc_version)
            except Exception:
                installed = mc_version
            if installed and installed != mc_version:
                self.installed_lbl.setText(f"Installed: {installed}")
            else:
                self.installed_lbl.setText("Installed: — (not installed yet)")
        else:
            self.installed_lbl.setText("Installed: —")

    def _refresh_versions(self):
        loader_key = self.loader_combo.currentData() or ""
        if not loader_key:
            return
        self.progress_bar.show()
        self.version_combo.setEnabled(False)

        worker = _LoaderFetchWorker(loader_key, self)
        worker.finished_with_data.connect(self._on_versions_loaded)
        self._fetch_workers.append(worker)
        worker.start()

    def _on_versions_loaded(self, loader_key: str, versions: List[str]):
        # Ignore callbacks from older workers we no longer care about.
        current = self.loader_combo.currentData() or ""
        if current != loader_key:
            return
        self.progress_bar.hide()
        self.version_combo.setEnabled(True)
        current_pin = ""
        try:
            current_pin = loader_versions.get_desired_loader_version(
                self.config, loader_key, self.mc_combo.currentData() or ""
            ) if self.config else ""
        except Exception:
            current_pin = ""

        self.version_combo.blockSignals(True)
        self.version_combo.clear()
        self.version_combo.addItem("(latest available)", "")
        for v in versions:
            self.version_combo.addItem(v, v)
        # Re-select the pinned value so the user sees it pre-highlighted.
        if current_pin:
            idx = self.version_combo.findData(current_pin)
            if idx >= 0:
                self.version_combo.setCurrentIndex(idx)
        self.version_combo.blockSignals(False)

        if versions:
            self.latest_lbl.setText(f"Latest upstream: {versions[0]}")
        else:
            self.latest_lbl.setText("Latest upstream: (offline)")
            self.latest_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")

    def _clear_pin(self):
        if not self.config:
            return
        loader_key = self.loader_combo.currentData() or ""
        mc_version = self.mc_combo.currentData() or ""
        loader_versions.set_desired_loader_version(self.config, loader_key, mc_version, "")
        self._refresh_installed_label()
        QMessageBox.information(
            self, "Pin Cleared",
            f"Cleared the pinned {loader_key} version for Minecraft {mc_version}."
        )

    def _apply(self):
        if not self.config:
            QMessageBox.warning(self, "No Config", "ConfigManager is unavailable; cannot apply.")
            return
        loader_key = self.loader_combo.currentData() or ""
        mc_version = self.mc_combo.currentData() or ""
        target = self.version_combo.currentData() or ""
        if not loader_key or not mc_version:
            QMessageBox.warning(self, "Selection Required", "Please pick a loader and a Minecraft version.")
            return

        # Persist the pin immediately so even if the user closes the dialog
        # the install picks the right version on the next Play.
        loader_versions.set_desired_loader_version(self.config, loader_key, mc_version, target)

        # Determine game_dir to wipe.
        game_dir: Optional[Path] = None
        if self.instance_data:
            try:
                game_dir = Path(self.instance_data.get("game_dir", ""))
            except Exception:
                game_dir = None
        if game_dir is None or not str(game_dir):
            # Fall back to the default instance directory under .neurax.
            try:
                from neurax.core.config import get_dot_neurax_dir
                game_dir = get_dot_neurax_dir() / "instances" / mc_version / ".minecraft"
            except Exception:
                game_dir = None

        if game_dir is None:
            # No path to wipe — just queue the install. The next launch will
            # install under whatever instance the user picked.
            loader_versions.queue_reinstall(self.config, loader_key, mc_version, target)
            self.accept()
            return

        # Run wipe + queue on a worker so the UI doesn't freeze.
        self.save_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.show()

        self._reinstall_worker = _ReinstallWorker(self.config, game_dir, loader_key, mc_version, target, self)
        self._reinstall_worker.finished_ok.connect(self._on_apply_done)
        self._reinstall_worker.failed.connect(self._on_apply_failed)
        self._reinstall_worker.start()

    def _on_apply_done(self, loader: str, mc_version: str, target: str, removed: List[str]):
        self.progress_bar.hide()
        self.save_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        msg = (
            f"Queued {loader} loader {target or '(latest)'} for Minecraft {mc_version}.\n\n"
            f"Removed {len(removed)} existing loader profile(s): "
            f"{', '.join(removed) if removed else '(none)'}\n\n"
            "The new version will install the next time you press PLAY."
        )
        QMessageBox.information(self, "Queued", msg)
        self.accept()

    def _on_apply_failed(self, msg: str):
        self.progress_bar.hide()
        self.save_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        QMessageBox.critical(self, "Apply Failed", msg)

    def reject(self):
        # Cancel any in-flight work so the thread doesn't outlive the dialog.
        for w in list(self._fetch_workers):
            try:
                if w.isRunning():
                    w.requestInterruption()
                    w.quit()
                    w.wait(500)
            except Exception:
                pass
        if self._reinstall_worker is not None:
            try:
                if self._reinstall_worker.isRunning():
                    self._reinstall_worker.requestInterruption()
                    self._reinstall_worker.quit()
                    self._reinstall_worker.wait(500)
            except Exception:
                pass
        super().reject()

    def closeEvent(self, event):
        self.reject()
        event.accept()