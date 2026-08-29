from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt
from neurax.core.skin import SkinDownloader
from neurax.core.config import ConfigManager

class SkinView(QWidget):
    """Widget for loading and displaying player skin & official Mojang cape model renders with dynamic scale on resize."""

    # Strong references to retired SkinDownloader workers, kept until each one
    # has actually finished. This prevents Python from garbage-collecting the
    # PyQt6 wrapper (and triggering "QThread: Destroyed while thread '' is still
    # running") when the user picks a new skin while a previous download is
    # still in flight. See reload_skin() for the lifecycle.
    _retired_workers: list = []

    def __init__(self, config: ConfigManager, view_mode: str = "front", parent=None):
        super().__init__(parent)
        self.config = config
        self.view_mode = view_mode
        self.worker = None
        self._current_image = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(40, 60)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label)

        self.reload_skin()

    def reload_skin(self):
        # If a previous worker is still running, detach it safely:
        #   1. Disconnect the `loaded` signal so a late completion doesn't call
        #      back into this widget with a stale result.
        #   2. Park it on the class-level retirement list with a one-shot
        #      finished-handler that cleans it up once the C++ thread actually
        #      exits, so Python's GC won't drop the wrapper mid-run.
        if self.worker is not None:
            prev = self.worker
            self.worker = None
            try:
                prev.loaded.disconnect(self.display_skin)
            except (TypeError, RuntimeError):
                # Already disconnected, or the C++ object is gone — both fine.
                pass
            SkinView._retired_workers.append(prev)

            def _retire_finished():
                try:
                    SkinView._retired_workers.remove(prev)
                except ValueError:
                    pass
                prev.deleteLater()

            try:
                prev.finished.connect(_retire_finished)
            except (TypeError, RuntimeError):
                # Thread already finished between our check and now — clean up
                # immediately instead of waiting for a signal that won't come.
                SkinView._retired_workers.remove(prev)
                prev.deleteLater()

        uuid_str = self.config.get("uuid", "steve")
        cache_dir = self.config.neurax_dir / "cache" / "skins"
        custom_skin_path = self.config.get("custom_skin_path", "")
        model = self.config.get("skin_model", "classic")
        second_layer = self.config.get("skin_second_layer", True)
        auth_mode = self.config.get("auth_mode", "microsoft")
        username = self.config.get("username", "")

        self.worker = SkinDownloader(
            uuid_str=uuid_str,
            cache_dir=cache_dir,
            custom_skin_path=custom_skin_path,
            model=model,
            second_layer=second_layer,
            view_mode=self.view_mode,
            auth_mode=auth_mode,
            username=username
        )
        self.worker.loaded.connect(self.display_skin)
        self.worker.start()

    def display_skin(self, image: QImage):
        self._current_image = image
        if image and not image.isNull():
            self.update_pixmap_scale()
        else:
            self.image_label.setText("[Skin Preview]")
            self.image_label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 14px;")

    def update_pixmap_scale(self):
        if self._current_image and not self._current_image.isNull():
            pixmap = QPixmap.fromImage(self._current_image)
            available_h = max(40, self.height() - 10)
            max_limit = 180 if self.view_mode == "both" else 220
            target_h = min(available_h, max_limit)
            scaled = pixmap.scaledToHeight(target_h, Qt.TransformationMode.FastTransformation)
            self.image_label.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_pixmap_scale()
