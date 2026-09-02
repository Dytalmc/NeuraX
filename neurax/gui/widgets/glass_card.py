from PyQt6.QtWidgets import QFrame
from PyQt6.QtCore import QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QColor

class GlassCard(QFrame):
    """Reusable Container with glass translucency and smooth hardware-accelerated transitions."""

    def __init__(self, parent=None, hover_glow: bool = True, accent_color: str = "#00F0FF"):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self.hover_glow = hover_glow
        self._glow_val = 0.0
        self._accent_color = QColor(accent_color)
        
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._update_glow)

    def set_accent_color(self, accent_color: str):
        self._accent_color = QColor(accent_color)

    def _update_glow(self, val):
        self._glow_val = float(val)

    def enterEvent(self, event):
        if self.hover_glow:
            self._anim.stop()
            self._anim.setStartValue(self._glow_val)
            self._anim.setEndValue(1.0)
            self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.hover_glow:
            self._anim.stop()
            self._anim.setStartValue(self._glow_val)
            self._anim.setEndValue(0.0)
            self._anim.start()
        super().leaveEvent(event)
