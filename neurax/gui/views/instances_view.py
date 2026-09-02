from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QDialog,
    QLineEdit, QComboBox, QCheckBox, QFileDialog, QRadioButton,
    QButtonGroup, QProgressBar
)
from PyQt6.QtCore import Qt, QUrl, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.widgets.ram_slider import RamSlider
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager, get_system_ram_info, get_dot_neurax_dir
from neurax.core.instances import InstanceManager
from neurax.core.versions import VersionManager
from neurax.core.java_finder import JavaFinder
from neurax.core.mrpack import MRPackConverterWorker
from neurax.core.logger import Logger
from neurax.core import loader_versions
from neurax.gui.views.play_view import format_playtime
from neurax.gui.views.loader_versions_view import LoaderVersionsDialog

class _LoaderListFetchWorker(QThread):
    """Fetch every available loader version for one loader off the UI thread."""
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


class MRPackDialog(QDialog):
    """Dialog for selecting .mrpack file and converting to .zip archive or working instance."""

    def __init__(self, parent=None, config: ConfigManager = None, instance_mgr: InstanceManager = None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.logger = Logger.get_instance()
        self.worker = None

        self.setWindowTitle("Modrinth .mrpack Converter")
        self.resize(520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info_lbl = QLabel("Convert Modrinth .mrpack packages into a downloadable .zip file or directly into a working NeuraX game instance.")
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("font-size: 13px;")
        layout.addWidget(info_lbl)

        # File Selection
        layout.addWidget(QLabel("Select .mrpack File:"))
        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("Path to modpack.mrpack...")
        file_row.addWidget(self.file_input, stretch=1)
        browse_file_btn = QPushButton(" Browse...")
        browse_file_btn.setObjectName("SecondaryButton")
        browse_file_btn.setIcon(IconEngine.get_icon("folder", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        browse_file_btn.setIconSize(QSize(14, 14))
        browse_file_btn.clicked.connect(self._browse_mrpack)
        file_row.addWidget(browse_file_btn)
        layout.addLayout(file_row)

        # Output Option
        layout.addWidget(QLabel("Conversion Mode:"))
        self.rb_zip = QRadioButton("Download / Save as Standard .ZIP Archive")
        self.rb_instance = QRadioButton("Convert directly to Working Game Instance")
        self.rb_instance.setChecked(True)

        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rb_zip, 0)
        self.mode_group.addButton(self.rb_instance, 1)

        layout.addWidget(self.rb_instance)
        layout.addWidget(self.rb_zip)

        # Options Widgets Stack
        self.instance_opt_widget = QWidget()
        inst_opt_layout = QVBoxLayout(self.instance_opt_widget)
        inst_opt_layout.setContentsMargins(0, 4, 0, 4)
        inst_opt_layout.setSpacing(6)
        inst_opt_layout.addWidget(QLabel("New Instance Name:"))
        self.inst_name_input = QLineEdit()
        self.inst_name_input.setPlaceholderText("Modpack Instance")
        inst_opt_layout.addWidget(self.inst_name_input)
        layout.addWidget(self.instance_opt_widget)

        self.zip_opt_widget = QWidget()
        zip_opt_layout = QVBoxLayout(self.zip_opt_widget)
        zip_opt_layout.setContentsMargins(0, 4, 0, 4)
        zip_opt_layout.setSpacing(6)
        zip_opt_layout.addWidget(QLabel("Save .zip File Location:"))
        zip_row = QHBoxLayout()
        self.zip_path_input = QLineEdit()
        self.zip_path_input.setPlaceholderText("C:/path/to/modpack.zip")
        zip_row.addWidget(self.zip_path_input, stretch=1)
        browse_zip_btn = QPushButton(" Save As...")
        browse_zip_btn.setObjectName("SecondaryButton")
        browse_zip_btn.setIcon(IconEngine.get_icon("save", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        browse_zip_btn.setIconSize(QSize(14, 14))
        browse_zip_btn.clicked.connect(self._browse_zip_dest)
        zip_row.addWidget(browse_zip_btn)
        zip_opt_layout.addLayout(zip_row)
        layout.addWidget(self.zip_opt_widget)
        self.zip_opt_widget.setVisible(False)

        self.rb_zip.toggled.connect(self._on_mode_toggled)
        self.rb_instance.toggled.connect(self._on_mode_toggled)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("Ready to convert.")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet("font-size: 12px; font-style: italic;")
        layout.addWidget(self.status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        self.convert_btn = QPushButton(" Start Conversion")
        self.convert_btn.setObjectName("PrimaryButton")
        self.convert_btn.setIcon(IconEngine.get_icon("play_triangle", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        self.convert_btn.setIconSize(QSize(14, 14))
        self.convert_btn.clicked.connect(self._start_conversion)
        btn_row.addWidget(self.convert_btn)
        layout.addLayout(btn_row)

    def _browse_mrpack(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select .mrpack File", "", "Modrinth Modpack (*.mrpack);;All Files (*)")
        if file_path:
            self.file_input.setText(file_path)
            base_name = Path(file_path).stem.replace("_", " ").title()
            if not self.inst_name_input.text():
                self.inst_name_input.setText(base_name)
            if not self.zip_path_input.text():
                self.zip_path_input.setText(str(Path(file_path).with_suffix(".zip")))

    def _browse_zip_dest(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save .zip Package", self.zip_path_input.text() or "modpack.zip", "Zip Archives (*.zip)")
        if file_path:
            self.zip_path_input.setText(file_path)

    def _on_mode_toggled(self):
        is_zip = self.rb_zip.isChecked()
        self.zip_opt_widget.setVisible(is_zip)
        self.instance_opt_widget.setVisible(not is_zip)

    def _start_conversion(self):
        mrpack_file = self.file_input.text().strip()
        if not mrpack_file or not Path(mrpack_file).exists():
            QMessageBox.warning(self, "Input Required", "Please select a valid .mrpack file.")
            return

        mode = "zip" if self.rb_zip.isChecked() else "instance"
        target_name = self.zip_path_input.text().strip() if mode == "zip" else self.inst_name_input.text().strip()

        if not target_name:
            QMessageBox.warning(self, "Input Required", "Please specify a valid destination name or path.")
            return

        self.convert_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("Starting converter worker...")

        # If a previous worker is still running (rapid double-click), bail out
        # rather than orphaning the C++ QThread.
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(
                self, "Already Converting",
                "A .mrpack conversion is already in progress. Please wait for it to finish."
            )
            return

        if mode == "zip":
            self.worker = MRPackConverterWorker(
                mrpack_path=mrpack_file,
                mode=mode,
                output_path=target_name,
                instance_mgr=self.instance_mgr
            )
        else:
            self.worker = MRPackConverterWorker(
                mrpack_path=mrpack_file,
                mode=mode,
                instance_name=target_name,
                instance_mgr=self.instance_mgr
            )
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_progress(self, pct: int, msg: str):
        self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    def _on_finished(self, success: bool, msg: str):
        self.convert_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        if success:
            self.progress_bar.setValue(100)
            self.status_lbl.setText("Conversion completed successfully!")
            QMessageBox.information(self, "Success", msg)
            self.accept()
        else:
            self.progress_bar.setValue(0)
            self.status_lbl.setText("Conversion failed.")
            QMessageBox.critical(self, "Error", msg)


class InstanceDialog(QDialog):
    """Dialog to create or edit a Minecraft instance with advanced loader, JVM args, and custom Java path."""

    def __init__(self, parent=None, config: ConfigManager = None, title: str = "Instance Settings",
                 name: str = "", loader: str = "Vanilla", version: str = "1.20.4",
                 max_ram: int = 4096, java_path: str = "auto", jvm_args: str = "",
                 folder_name: str = "", instance_mgr: InstanceManager = None,
                 loader_version: str = ""):
        super().__init__(parent)
        self.config = config
        self.folder_name = folder_name
        self.instance_mgr = instance_mgr
        self.logger = Logger.get_instance()
        self.version_mgr = VersionManager.get_instance(config.neurax_dir / "cache") if config else None
        self._initial_loader_version = (loader_version or "").strip()

        self.setWindowTitle(title)
        self.resize(500, 680)

        sys_ram, _ = get_system_ram_info()
        max_allocable = max(4096, sys_ram - 1024)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # AI Radar info banner
        self.ai_radar_lbl = QLabel("AI Version Radar: Active")
        self.ai_radar_lbl.setStyleSheet("color: #00FF99; font-size: 11px; font-weight: bold;")
        layout.addWidget(self.ai_radar_lbl)

        # Instance Name
        layout.addWidget(QLabel("Instance Name:"))
        self.name_input = QLineEdit(name)
        self.name_input.setPlaceholderText("e.g. Fabric 1.20.4 SMP")
        layout.addWidget(self.name_input)

        # Mod Loader
        layout.addWidget(QLabel("Mod Loader:"))
        self.loader_combo = QComboBox()
        self.loader_combo.addItems(["Vanilla", "Fabric", "Forge", "NeoForge", "Quilt"])
        self.loader_combo.setCurrentText(loader)
        self.loader_combo.currentIndexChanged.connect(self._on_loader_changed)
        layout.addWidget(self.loader_combo)

        # Loader Software Version (separate from Minecraft version).
        # Always shows the latest available upstream version for the
        # currently-selected loader, and lets the user pin a specific one.
        layout.addWidget(QLabel("Loader Version:"))
        loader_row = QHBoxLayout()
        self.loader_version_combo = QComboBox()
        self.loader_version_combo.setToolTip(
            "Specific software version of the selected mod loader. "
            "Leave on '(latest available)' to always use the newest one."
        )
        self.loader_version_combo.addItem("(latest available)", "")
        loader_row.addWidget(self.loader_version_combo, stretch=1)
        self.loader_latest_btn = QPushButton(" Latest")
        self.loader_latest_btn.setObjectName("SecondaryButton")
        self.loader_latest_btn.setIcon(
            IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor("#00F0FF"), 14)
        )
        self.loader_latest_btn.setIconSize(QSize(14, 14))
        self.loader_latest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.loader_latest_btn.clicked.connect(self._use_latest_loader)
        loader_row.addWidget(self.loader_latest_btn)
        self.loader_reset_btn = QPushButton(" Reset")
        self.loader_reset_btn.setObjectName("SecondaryButton")
        self.loader_reset_btn.setIcon(
            IconEngine.get_icon("trash", QColor("#94A3B8"), QColor("#FF3366"), 14)
        )
        self.loader_reset_btn.setIconSize(QSize(14, 14))
        self.loader_reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.loader_reset_btn.clicked.connect(self._reset_loader_version)
        loader_row.addWidget(self.loader_reset_btn)
        layout.addLayout(loader_row)

        self.loader_status_lbl = QLabel("Loader version: uses upstream latest")
        self.loader_status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        layout.addWidget(self.loader_status_lbl)
        self._loader_workers = []  # keep refs so threads aren't GC'd early

        # Filter Checkboxes
        layout.addWidget(QLabel("Version Filters:"))
        filter_grid = QVBoxLayout()
        row1 = QHBoxLayout()
        self.cb_releases = QCheckBox("Releases")
        self.cb_releases.setChecked(self.config.get("show_releases", True) if self.config else True)
        self.cb_snapshots = QCheckBox("Snapshots")
        self.cb_snapshots.setChecked(self.config.get("show_snapshots", False) if self.config else False)
        self.cb_beta = QCheckBox("Beta")
        self.cb_beta.setChecked(self.config.get("show_beta", False) if self.config else False)
        self.cb_alpha = QCheckBox("Alpha")
        self.cb_alpha.setChecked(self.config.get("show_alpha", False) if self.config else False)
        row1.addWidget(self.cb_releases)
        row1.addWidget(self.cb_snapshots)
        row1.addWidget(self.cb_beta)
        row1.addWidget(self.cb_alpha)
        filter_grid.addLayout(row1)

        row2 = QHBoxLayout()
        self.cb_indev = QCheckBox("Indev/Infdev")
        self.cb_indev.setChecked(self.config.get("show_indev", False) if self.config else False)
        self.cb_aprilfools = QCheckBox("April Fools")
        self.cb_aprilfools.setChecked(self.config.get("show_aprilfools", False) if self.config else False)
        self.cb_historic = QCheckBox("Historic")
        self.cb_historic.setChecked(self.config.get("show_historic", False) if self.config else False)
        row2.addWidget(self.cb_indev)
        row2.addWidget(self.cb_aprilfools)
        row2.addWidget(self.cb_historic)
        filter_grid.addLayout(row2)
        layout.addLayout(filter_grid)

        for cb in (self.cb_releases, self.cb_snapshots, self.cb_beta, self.cb_alpha, self.cb_indev, self.cb_aprilfools, self.cb_historic):
            cb.toggled.connect(self.populate_versions)

        # Minecraft Version Dropdown
        layout.addWidget(QLabel("Minecraft Version:"))
        self.version_combo = QComboBox()
        layout.addWidget(self.version_combo)

        # RAM Slider
        self.max_ram_slider = RamSlider("Memory Allocation", 1024, max_allocable, min(max_ram, max_allocable))
        layout.addWidget(self.max_ram_slider)

        # Java Executable
        layout.addWidget(QLabel("Java Executable Runtime:"))
        java_row = QHBoxLayout()
        self.java_combo = QComboBox()
        self.java_combo.addItem("Auto Detect (System Default)", "auto")
        for jname, jpath in JavaFinder.find_java_installations():
            self.java_combo.addItem(f"{jname} ({jpath})", jpath)

        matched = False
        for i in range(self.java_combo.count()):
            if self.java_combo.itemData(i) == java_path:
                self.java_combo.setCurrentIndex(i)
                matched = True
                break
        if not matched and java_path and java_path != "auto":
            self.java_combo.addItem(f"Custom ({java_path})", java_path)
            self.java_combo.setCurrentIndex(self.java_combo.count() - 1)

        java_row.addWidget(self.java_combo, stretch=1)
        browse_btn = QPushButton(" Browse...")
        browse_btn.setObjectName("SecondaryButton")
        browse_btn.setIcon(IconEngine.get_icon("folder", QColor("#94A3B8"), QColor("#00F0FF"), 14))
        browse_btn.setIconSize(QSize(14, 14))
        browse_btn.clicked.connect(self._browse_java)
        java_row.addWidget(browse_btn)
        layout.addLayout(java_row)

        # JVM Arguments
        layout.addWidget(QLabel("JVM Arguments (FPS Optimization):"))
        self.jvm_input = QLineEdit(jvm_args)
        self.jvm_input.setPlaceholderText("Custom JVM Flags")
        layout.addWidget(self.jvm_input)

        # Buttons
        btn_row = QHBoxLayout()
        if self.folder_name:
            folder_btn = QPushButton(" Folder")
            folder_btn.setObjectName("SecondaryButton")
            folder_btn.setIcon(IconEngine.get_icon("folder", QColor("#94A3B8"), QColor("#00F0FF"), 14))
            folder_btn.setIconSize(QSize(14, 14))
            folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            folder_btn.clicked.connect(self._open_folder)
            btn_row.addWidget(folder_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("SecondaryButton")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save Instance")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setIcon(IconEngine.get_icon("save", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        save_btn.setIconSize(QSize(14, 14))
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        if self.version_mgr:
            self.version_mgr.versions_updated.connect(self._on_ai_version_update)
            self.version_mgr.start_monitoring(poll_interval=300)

        self.populate_versions()
        if version:
            idx = self.version_combo.findText(version)
            if idx >= 0:
                self.version_combo.setCurrentIndex(idx)
            else:
                self.version_combo.addItem(version)
                self.version_combo.setCurrentText(version)

        # Loader-version list: seed the dropdown with whatever was saved
        # (passed in via `loader_version`), then kick an async fetch so the
        # latest versions show up as soon as the network call returns.
        if self._initial_loader_version:
            self.loader_version_combo.addItem(self._initial_loader_version, self._initial_loader_version)
            self.loader_version_combo.setCurrentIndex(self.loader_version_combo.count() - 1)
        self._update_loader_status_label()
        self._refresh_loader_versions()

    def done(self, r):
        if hasattr(self, "version_mgr") and self.version_mgr:
            try:
                self.version_mgr.versions_updated.disconnect(self._on_ai_version_update)
            except Exception:
                pass
        super().done(r)

    def _on_ai_version_update(self, info: dict):
        latest_snap = info.get("latest_snapshot", "")
        loaders = info.get("loaders", {})
        fab = loaders.get("Fabric", "")
        # Pull the latest loader versions too so the chip in this dialog
        # always matches what the AI Radar thinks is newest.
        loader_versions_radar = info.get("loader_versions", {}) or {}
        if loader_versions_radar:
            # Re-fetch the loader list so the user sees the AI's picks
            # highlighted without us hard-coding anything here.
            self._refresh_loader_versions()
        if latest_snap:
            self.ai_radar_lbl.setText(f"Live AI Radar: Active | Latest Snapshot: {latest_snap}" + (f" | Fabric: {fab}" if fab else ""))
        self.populate_versions()

    # ----- Loader-version picker -----
    def _on_loader_changed(self, _index: int):
        # Switching loader resets the pinned version. The user can pick a
        # new one from the now-refreshed dropdown.
        self.loader_version_combo.blockSignals(True)
        self.loader_version_combo.clear()
        self.loader_version_combo.addItem("(latest available)", "")
        self.loader_version_combo.blockSignals(False)
        self._update_loader_status_label()
        self._refresh_loader_versions()

    def _refresh_loader_versions(self):
        loader_name = self.loader_combo.currentText().strip().lower()
        if not loader_name or loader_name == "vanilla":
            self.loader_version_combo.setEnabled(False)
            self.loader_latest_btn.setEnabled(False)
            self.loader_reset_btn.setEnabled(False)
            self.loader_status_lbl.setText("Loader version: N/A (Vanilla)")
            return
        self.loader_version_combo.setEnabled(True)
        self.loader_latest_btn.setEnabled(True)
        self.loader_reset_btn.setEnabled(True)
        worker = _LoaderListFetchWorker(loader_name, self)
        worker.finished_with_data.connect(self._on_loader_versions_loaded)
        self._loader_workers.append(worker)
        worker.start()

    def _on_loader_versions_loaded(self, loader_name: str, versions: list):
        # Drop the placeholder + any seed we added, then refill with the
        # upstream list. Preserve the user's currently-selected pin.
        current_pin = self.loader_version_combo.currentData() or self._initial_loader_version or ""
        self.loader_version_combo.blockSignals(True)
        self.loader_version_combo.clear()
        self.loader_version_combo.addItem("(latest available)", "")
        for v in versions:
            self.loader_version_combo.addItem(v, v)
        if current_pin:
            idx = self.loader_version_combo.findData(current_pin)
            if idx >= 0:
                self.loader_version_combo.setCurrentIndex(idx)
            else:
                # Pin doesn't exist on the upstream list anymore — keep it
                # visible so the user understands the gap.
                self.loader_version_combo.addItem(current_pin, current_pin)
                self.loader_version_combo.setCurrentIndex(self.loader_version_combo.count() - 1)
        self.loader_version_combo.blockSignals(False)
        self._update_loader_status_label(versions)

    def _use_latest_loader(self):
        self.loader_version_combo.setCurrentIndex(0)  # "(latest available)"
        self._update_loader_status_label()

    def _reset_loader_version(self):
        self._use_latest_loader()

    def _update_loader_status_label(self, versions: list = None):
        loader_name = self.loader_combo.currentText().strip().lower()
        if loader_name in ("", "vanilla"):
            self.loader_status_lbl.setText("Loader version: N/A (Vanilla)")
            return
        sel = self.loader_version_combo.currentData() or ""
        if sel:
            self.loader_status_lbl.setText(f"Loader version: pinned to {sel}")
            self.loader_status_lbl.setStyleSheet("color: #00FF99; font-size: 11px; font-weight: 700;")
        else:
            latest = ""
            if versions:
                latest = versions[0] if isinstance(versions[0], str) else ""
            if latest:
                self.loader_status_lbl.setText(f"Loader version: upstream latest ({latest})")
            else:
                self.loader_status_lbl.setText("Loader version: uses upstream latest")
            self.loader_status_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")

    def _open_folder(self):
        if self.folder_name:
            if self.instance_mgr:
                folder_path = self.instance_mgr.instances_dir / self.folder_name
            else:
                folder_path = get_dot_neurax_dir() / "instances" / self.folder_name
            folder_path.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_path)))

    def _browse_java(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Java Binary", "", "Executable (*.exe);;All Files (*)")
        if file_path:
            ver = JavaFinder.get_java_version(file_path)
            self.java_combo.addItem(f"Custom {ver} ({file_path})", file_path)
            self.java_combo.setCurrentIndex(self.java_combo.count() - 1)
            self.logger.user_action(f"Selected custom Java executable in Instance Dialog: {file_path}")

    def populate_versions(self):
        if not hasattr(self, 'version_combo'):
            return
        current_selected = self.version_combo.currentText()
        self.version_combo.clear()
        if not self.version_mgr:
            self.version_combo.addItem("1.20.4")
            return

        vers = self.version_mgr.get_filtered_versions(
            show_releases=self.cb_releases.isChecked(),
            show_snapshots=self.cb_snapshots.isChecked(),
            show_beta=self.cb_beta.isChecked(),
            show_alpha=self.cb_alpha.isChecked(),
            show_indev=self.cb_indev.isChecked(),
            show_aprilfools=self.cb_aprilfools.isChecked(),
            show_historic=self.cb_historic.isChecked()
        )
        for v in vers:
            self.version_combo.addItem(v)
        if current_selected:
            idx = self.version_combo.findText(current_selected)
            if idx >= 0:
                self.version_combo.setCurrentIndex(idx)

    def get_data(self):
        loader_version = ""
        try:
            loader_version = self.loader_version_combo.currentData() or ""
        except Exception:
            loader_version = ""
        return {
            "name": self.name_input.text().strip(),
            "loader": self.loader_combo.currentText(),
            "version": self.version_combo.currentText() or "1.20.4",
            "max_ram": self.max_ram_slider.value(),
            "java_path": self.java_combo.currentData() or "auto",
            "jvm_args": self.jvm_input.text().strip(),
            "loader_version": loader_version.strip() if isinstance(loader_version, str) else "",
        }


class InstancesView(QWidget):
    """Instance Management View: Create, Delete, Configure Loader Instances, Convert .mrpack, and Sync Global Data."""

    def __init__(self, config: ConfigManager, instance_mgr: InstanceManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.instance_mgr = instance_mgr
        self.logger = Logger.get_instance()
        self.version_mgr = VersionManager.get_instance(config.neurax_dir / "cache")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Header Row
        header = QHBoxLayout()
        title = QLabel("Instance Management")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()

        ai_badge = QLabel("Live AI Version Radar Active")
        ai_badge.setStyleSheet("""
            background-color: rgba(0, 255, 153, 0.12);
            color: #00FF99;
            border: 1px solid rgba(0, 255, 153, 0.35);
            border-radius: 6px;
            padding: 4px 10px;
            font-size: 11px;
            font-weight: 800;
        """)
        header.addWidget(ai_badge)

        accent = self.config.get("accent_color", "#00F0FF")
        mrpack_btn = QPushButton(" Convert .mrpack")
        mrpack_btn.setObjectName("SecondaryButton")
        mrpack_btn.setIcon(IconEngine.get_icon("package", QColor("#94A3B8"), QColor(accent), 14))
        mrpack_btn.setIconSize(QSize(14, 14))
        mrpack_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        mrpack_btn.clicked.connect(self.open_mrpack_converter)
        header.addWidget(mrpack_btn)

        loader_btn = QPushButton(" Loader Versions")
        loader_btn.setObjectName("SecondaryButton")
        loader_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        loader_btn.setIconSize(QSize(14, 14))
        loader_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        loader_btn.setToolTip("Pin Fabric / Quilt / Forge / NeoForge loader versions")
        loader_btn.clicked.connect(self.open_loader_versions)
        header.addWidget(loader_btn)

        sync_btn = QPushButton(" Global Sync")
        sync_btn.setObjectName("SecondaryButton")
        sync_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor(accent), 14))
        sync_btn.setIconSize(QSize(14, 14))
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.clicked.connect(self.run_global_sync)
        header.addWidget(sync_btn)

        create_btn = QPushButton(" New Instance")
        create_btn.setObjectName("PrimaryButton")
        create_btn.setIcon(IconEngine.get_icon("plus", QColor("#FFFFFF"), QColor("#FFFFFF"), 14))
        create_btn.setIconSize(QSize(14, 14))
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self.create_instance_dialog)
        header.addWidget(create_btn)
        layout.addLayout(header)

        # Instance List Container
        card = GlassCard()
        card_layout = QVBoxLayout(card)
        
        self.inst_list = QListWidget()
        self.inst_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        card_layout.addWidget(self.inst_list)

        # Action Bar
        actions = QHBoxLayout()
        edit_btn = QPushButton(" Edit Selected")
        edit_btn.setObjectName("SecondaryButton")
        edit_btn.setIcon(IconEngine.get_icon("edit", QColor("#94A3B8"), QColor(accent), 14))
        edit_btn.setIconSize(QSize(14, 14))
        edit_btn.clicked.connect(self.edit_selected)
        actions.addWidget(edit_btn)

        del_btn = QPushButton(" Delete Instance")
        del_btn.setObjectName("SecondaryButton")
        del_btn.setIcon(IconEngine.get_icon("trash", QColor("#94A3B8"), QColor("#FF3366"), 14))
        del_btn.setIconSize(QSize(14, 14))
        del_btn.clicked.connect(self.delete_selected)
        actions.addWidget(del_btn)
        actions.addStretch()
        
        card_layout.addLayout(actions)
        layout.addWidget(card)

        self.version_mgr.start_monitoring(poll_interval=300)
        self.reload_list()
        self.instance_mgr.instances_changed.connect(self.reload_list)
        self.config.config_changed.connect(self._on_config_changed)

    def _on_config_changed(self, key: str, value: object):
        if key == "analytics":
            self.reload_list()

    def reload_list(self):
        self.inst_list.clear()
        instances = self.instance_mgr.list_instances()
        analytics = self.config.get("analytics", {})
        accent = self.config.get("accent_color", "#00F0FF")
        for inst in instances:
            loader = inst.get("loader", "Vanilla")
            inst_analytics = analytics.get(inst.get("name", ""), {})
            if not inst_analytics and inst.get("folder_name") in analytics:
                inst_analytics = analytics.get(inst.get("folder_name"), {})
            total_sec = inst_analytics.get("total_seconds", 0) if isinstance(inst_analytics, dict) else 0
            item = QListWidgetItem(f"{inst['name']}  [{loader} {inst['version']}]  |  RAM: {inst['max_ram']}MB  |  Total Played: {format_playtime(total_sec)}")
            item.setIcon(IconEngine.get_icon("instances", QColor("#8A94A6"), QColor(accent), 18))
            item.setData(Qt.ItemDataRole.UserRole, inst["folder_name"])
            self.inst_list.addItem(item)

    def open_mrpack_converter(self):
        self.logger.user_action("Opened .mrpack Converter Dialog")
        dialog = MRPackDialog(self, config=self.config, instance_mgr=self.instance_mgr)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload_list()

    def open_loader_versions(self):
        """Open the Loader Version Manager for the currently-selected instance."""
        item = self.inst_list.currentItem()
        folder_name = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not folder_name:
            folder_name = self.config.get("selected_instance", "Default")
        inst = self.instance_mgr.get_instance(folder_name) if folder_name else None
        if not inst:
            inst = {"name": folder_name or "Default", "version": "1.20.4",
                    "folder_name": folder_name or "Default", "loader": "Vanilla",
                    "game_dir": str(self.instance_mgr.instances_dir / (folder_name or "Default") / ".minecraft")}
        self.logger.user_action(f"Opened Loader Versions Dialog for instance '{inst.get('folder_name')}'")
        dialog = LoaderVersionsDialog(self, config=self.config, instance_data=inst)
        dialog.exec()

    def run_global_sync(self):
        self.logger.user_action("Triggered manual Global Sync from InstancesView")
        ok, msg = self.instance_mgr.sync_global_data(self.config)
        if ok:
            QMessageBox.information(self, "Global Sync Complete", msg)
        else:
            QMessageBox.warning(self, "Global Sync Notice", msg)

    def create_instance_dialog(self):
        self.logger.user_action("Opened New Instance Dialog")
        dialog = InstanceDialog(self, config=self.config, title="New Instance", jvm_args=self.config.get("jvm_args", ""))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if data["name"]:
                new_folder = self.instance_mgr.create_instance(
                    name=data["name"],
                    version=data["version"],
                    loader=data["loader"],
                    max_ram=data["max_ram"],
                    java_path=data["java_path"],
                    jvm_args=data["jvm_args"],
                    loader_version=data.get("loader_version", "")
                )
                self.config.set("selected_instance", new_folder)
                self.logger.user_action(f"Created instance '{data['name']}' ({data['loader']} {data['version']})")

    def edit_selected(self):
        item = self.inst_list.currentItem()
        if not item:
            QMessageBox.information(self, "Edit Instance", "Please select an instance to edit.")
            return
        folder_name = item.data(Qt.ItemDataRole.UserRole)
        self.logger.user_action(f"Opened Edit Dialog for instance '{folder_name}'")
        inst = self.instance_mgr.get_instance(folder_name)
        dialog = InstanceDialog(
            self, config=self.config, title=f"Edit {folder_name}",
            name=inst["name"], loader=inst.get("loader", "Vanilla"),
            version=inst["version"], max_ram=inst["max_ram"],
            java_path=inst.get("java_path", "auto"), jvm_args=inst.get("jvm_args", ""),
            loader_version=inst.get("loader_version", ""),
            folder_name=folder_name, instance_mgr=self.instance_mgr
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.instance_mgr.update_instance(
                folder_name,
                name=data["name"],
                loader=data["loader"],
                version=data["version"],
                max_ram=data["max_ram"],
                java_path=data["java_path"],
                jvm_args=data["jvm_args"],
                loader_version=data.get("loader_version", "")
            )
            self.logger.user_action(f"Updated instance '{folder_name}' settings")

    def delete_selected(self):
        item = self.inst_list.currentItem()
        if not item:
            QMessageBox.information(self, "Delete Instance", "Please select an instance to delete.")
            return
        folder_name = item.data(Qt.ItemDataRole.UserRole)
        if folder_name == "Default":
            QMessageBox.warning(self, "Delete Instance", "Cannot delete the Default instance.")
            return
        reply = QMessageBox.question(
            self, "Delete Instance", f"Are you sure you want to delete '{folder_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.logger.user_action(f"Deleted instance '{folder_name}'")
            if self.config.get("selected_instance") == folder_name:
                self.config.set("selected_instance", "Default")
            self.instance_mgr.delete_instance(folder_name)
