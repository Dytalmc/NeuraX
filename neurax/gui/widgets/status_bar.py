from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve

class StatusBarWidget(QWidget):
    """Real-time async download and launch status progress widget with animated bar transitions."""

    def __init__(self, config=None, parent=None):
        super().__init__(parent)
        self.config = config
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        info_row = QHBoxLayout()
        self.status_lbl = QLabel("Ready to launch")
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 600;")
        
        self.speed_lbl = QLabel("")
        self.speed_lbl.setStyleSheet("font-size: 12px; font-weight: bold;")
        
        info_row.addWidget(self.status_lbl)
        info_row.addStretch()
        info_row.addWidget(self.speed_lbl)
        layout.addLayout(info_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setValue(0)
        
        # Dynamic style init
        accent = "#00F0FF"
        if self.config:
            accent = self.config.get("accent_color", "#00F0FF")
            self.config.config_changed.connect(self._on_config_changed)

        self._update_theme_style(accent)
        layout.addWidget(self.progress_bar)

        self.prog_anim = QPropertyAnimation(self.progress_bar, b"value", self)
        self.prog_anim.setDuration(150)
        self.prog_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    def _on_config_changed(self, key: str, value: object):
        if key == "accent_color":
            self._update_theme_style(str(value))

    def _update_theme_style(self, accent_color: str):
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                border: none;
            }}
            QProgressBar::chunk {{
                background: {accent_color};
                border-radius: 4px;
            }}
        """)

    def update_status(self, percent: int, text: str, speed: str = ""):
        self.prog_anim.stop()
        self.prog_anim.setStartValue(self.progress_bar.value())
        self.prog_anim.setEndValue(percent)
        self.prog_anim.start()
        self.status_lbl.setText(text)
        self.speed_lbl.setText(speed)