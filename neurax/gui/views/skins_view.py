from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QScrollArea
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor
from neurax.gui.widgets.glass_card import GlassCard
from neurax.gui.widgets.skin_view import SkinView
from neurax.gui.icons import IconEngine
from neurax.core.config import ConfigManager
from neurax.core.auth import AuthManager
from neurax.core.logger import Logger

class SkinsView(QWidget):
    """Skin Customization View with skin preview, choose skin, upload to Microsoft, and reset default skin options."""

    def __init__(self, config: ConfigManager, auth_mgr: AuthManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.auth_mgr = auth_mgr
        self.logger = Logger.get_instance()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Skin & Cape Customization")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        main_layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background: transparent;")
        content_layout = QHBoxLayout(scroll_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(20)

        # Left Card: Live Skin & Cape Preview
        left_card = GlassCard()
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(20, 20, 20, 20)

        preview_lbl = QLabel("OFFICIAL MINECRAFT SKIN & CAPE PREVIEW")
        preview_lbl.setStyleSheet("font-size: 12px; font-weight: 800; letter-spacing: 1px;")
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(preview_lbl)

        self.skin_preview = SkinView(self.config, view_mode="both")
        left_layout.addWidget(self.skin_preview)

        self.status_file_lbl = QLabel(self._get_skin_status_text())
        self.status_file_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        self.status_file_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_file_lbl.setWordWrap(True)
        left_layout.addWidget(self.status_file_lbl)

        content_layout.addWidget(left_card, stretch=1)

        # Right Card: Options Section
        right_card = GlassCard()
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(25, 25, 25, 25)
        right_layout.setSpacing(18)

        opts_lbl = QLabel("Skin Management")
        opts_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(opts_lbl)

        # 1. Choose Skin
        choose_btn = QPushButton(" Choose Skin PNG...")
        choose_btn.setObjectName("PrimaryButton")
        choose_btn.setIcon(IconEngine.get_icon("folder", QColor("#FFFFFF"), QColor("#FFFFFF"), 16))
        choose_btn.setIconSize(QSize(16, 16))
        choose_btn.setMinimumHeight(38)
        choose_btn.clicked.connect(self._browse_skin_file)
        right_layout.addWidget(choose_btn)

        # 2. Upload to Microsoft / Mojang
        upload_mojang_btn = QPushButton(" Upload & Equip Skin on Mojang Account")
        upload_mojang_btn.setObjectName("SecondaryButton")
        upload_mojang_btn.setIcon(IconEngine.get_icon("cloud", QColor("#94A3B8"), QColor("#00F0FF"), 16))
        upload_mojang_btn.setIconSize(QSize(16, 16))
        upload_mojang_btn.setMinimumHeight(38)
        upload_mojang_btn.clicked.connect(self._upload_to_mojang)
        right_layout.addWidget(upload_mojang_btn)

        # 3. Reset Default Skin
        reset_btn = QPushButton(" Reset to Mojang Default Skin")
        reset_btn.setObjectName("SecondaryButton")
        reset_btn.setIcon(IconEngine.get_icon("refresh", QColor("#94A3B8"), QColor("#00F0FF"), 16))
        reset_btn.setIconSize(QSize(16, 16))
        reset_btn.setMinimumHeight(38)
        reset_btn.clicked.connect(self._reset_default_skin)
        right_layout.addWidget(reset_btn)

        right_layout.addStretch()
        content_layout.addWidget(right_card, stretch=2)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll, stretch=1)

        self.config.config_changed.connect(self._on_config_changed)

    def _on_config_changed(self, key: str, value: object):
        if key in ("custom_skin_path", "username", "uuid"):
            self.status_file_lbl.setText(self._get_skin_status_text())
            self.skin_preview.reload_skin()

    def _get_skin_status_text(self) -> str:
        custom_path = self.config.get("custom_skin_path", "")
        if custom_path and Path(custom_path).exists():
            return f"Custom File (Pending Upload): {Path(custom_path).name}"
        username = self.config.get("username", "NeuraPlayer")
        token = self.config.get("access_token", "0")
        if token != "0" and self.config.get("auth_mode") == "microsoft":
            return f"Equipped Mojang Skin: {username}"
        return "Default Minecraft Skin"

    def _browse_skin_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Skin Texture PNG", "", "PNG Image (*.png)")
        if file_path:
            self.logger.user_action(f"Selected custom skin file: '{file_path}'")
            # config.set fires config_changed → _on_config_changed, which already
            # refreshes the status label and calls skin_preview.reload_skin().
            # Calling reload_skin() here as well would race two threads against
            # each other, so we deliberately do NOT do it.
            self.config.set("custom_skin_path", file_path)

    def _upload_to_mojang(self):
        custom_path = self.config.get("custom_skin_path", "")
        if not custom_path or not Path(custom_path).exists():
            QMessageBox.warning(self, "Upload Skin", "Please choose a valid local PNG skin file first.")
            return
        token = self.config.get("access_token", "0")
        if not token or token == "0" or self.config.get("auth_mode") != "microsoft":
            QMessageBox.warning(self, "Microsoft Login Required", "You must be logged into a Microsoft account to upload and equip a skin.")
            return
        model = self.config.get("skin_model", "classic")
        self.logger.user_action(f"Uploading and equipping skin on official Mojang account: {custom_path}")
        try:
            self.auth_mgr.upload_skin_to_mojang(custom_path, model)
            self.logger.info("Skin successfully uploaded and equipped on official Mojang account.")
            self.config.set("custom_skin_path", "")
            self.status_file_lbl.setText(self._get_skin_status_text())
            self.skin_preview.reload_skin()
            QMessageBox.information(self, "Skin Upload", "Skin successfully uploaded and equipped on your official Mojang Minecraft account!")
        except Exception as e:
            self.logger.error(f"Skin upload failed: {e}")
            QMessageBox.critical(self, "Upload Error", str(e))

    def _reset_default_skin(self):
        self.logger.user_action("Resetting to official Mojang default skin")
        self.config.set("custom_skin_path", "")
        token = self.config.get("access_token", "0")
        if token and token != "0" and self.config.get("auth_mode") == "microsoft":
            try:
                self.auth_mgr.reset_skin_mojang()
                self.logger.info("Reset to default Mojang skin successfully.")
                self.status_file_lbl.setText(self._get_skin_status_text())
                self.skin_preview.reload_skin()
                QMessageBox.information(self, "Reset Skin", "Reset to your official default Mojang skin.")
            except Exception as e:
                self.logger.error(f"Reset skin failed: {e}")
                QMessageBox.critical(self, "Reset Error", str(e))
        else:
            self.status_file_lbl.setText(self._get_skin_status_text())
            self.skin_preview.reload_skin()
            QMessageBox.information(self, "Reset Skin", "Reset local skin texture.")
