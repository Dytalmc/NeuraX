import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap
from neurax.gui.icons import IconEngine

class LockScreenOverlay(QWidget):
    """An immersive, highly animated fullscreen lock screen overlay for NeuraX launcher."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.is_active = False
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

        # UI elements
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(40, 40, 40, 40)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.glow_card = QWidget(self)
        self.glow_card.setFixedSize(450, 400)
        self.glow_card.setObjectName("LockCard")
        
        # Glow Card Layout
        card_layout = QVBoxLayout(self.glow_card)
        card_layout.setContentsMargins(30, 40, 30, 30)
        card_layout.setSpacing(20)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Pulsing Padlock Icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setPixmap(IconEngine.get_pixmap("shield", QColor("#FF3366"), 64))
        card_layout.addWidget(self.icon_lbl)

        # Title / Warning
        self.title_lbl = QLabel("LAUNCHER LOCKED")
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet("font-size: 22px; font-weight: 900; color: #FF3366; letter-spacing: 3px;")
        card_layout.addWidget(self.title_lbl)

        self.subtitle_lbl = QLabel("This device has been locked from using NeuraX Launcher.")
        self.subtitle_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle_lbl.setStyleSheet("font-size: 13px;")
        self.subtitle_lbl.setWordWrap(True)
        card_layout.addWidget(self.subtitle_lbl)

        # Unlock button
        self.unlock_btn = QPushButton("UNLOCK LAUNCHER")
        self.unlock_btn.setObjectName("PrimaryButton")
        self.unlock_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.unlock_btn.setFixedSize(220, 42)
        self.unlock_btn.clicked.connect(self._unlock_clicked)
        card_layout.addWidget(self.unlock_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.layout.addWidget(self.glow_card)

        # Animation timer for cool pulsing
        self.pulse_timer = QTimer(self)
        self.pulse_timer.setInterval(30)
        self.pulse_timer.timeout.connect(self._pulse_tick)
        self.pulse_angle = 0.0

    def show_locked(self):
        if self.is_active:
            return
        self.is_active = True
        self.show()
        self.raise_()
        self.setFocus()
        self.grabKeyboard()
        self.pulse_timer.start()

        # Smooth slide & fade-in animation
        self.move(0, -50)
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(400)
        self.anim.setStartValue(QPoint(0, -100))
        self.anim.setEndValue(QPoint(0, 0))
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.start()

    def hide_unlocked(self):
        if not self.is_active:
            return
        self.is_active = False
        self.pulse_timer.stop()
        self.releaseKeyboard()
        
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(300)
        self.anim.setStartValue(QPoint(0, 0))
        self.anim.setEndValue(QPoint(0, -self.height()))
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim.finished.connect(self.hide)
        self.anim.start()

    def _unlock_clicked(self):
        self.config.set("launcher_locked", False)
        self.hide_unlocked()

    def _pulse_tick(self):
        self.pulse_angle += 0.05
        pulse_scale = 1.0 + 0.08 * math.sin(self.pulse_angle)
        icon_size = max(48, int(64 * pulse_scale))
        self.icon_lbl.setPixmap(IconEngine.get_pixmap("shield", QColor("#FF3366"), icon_size))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw a beautiful dark glassmorphic background overlay
        accent = self.config.get("accent_color", "#00F0FF")
        c = QColor(accent)
        
        # Pulse background overlay opacity
        bg_alpha = int(225 + 10 * math.sin(self.pulse_angle))
        painter.fillRect(self.rect(), QColor(5, 5, 8, bg_alpha))

        # Draw tech-lines
        pen = QPen(QColor(c.red(), c.green(), c.blue(), 40))
        pen.setWidth(1)
        painter.setPen(pen)
        
        # Grid lines
        spacing = 40
        for x in range(0, self.width(), spacing):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), spacing):
            painter.drawLine(0, y, self.width(), y)

        # Draw cool glowing card
        card_rect = self.glow_card.geometry()
        painter.setBrush(QBrush(QColor(15, 15, 22, 240)))
        
        glow_width = int(2.0 + 1.5 * math.sin(self.pulse_angle))
        pen_glow = QPen(QColor(c.red(), c.green(), c.blue(), 180))
        pen_glow.setWidth(glow_width)
        painter.setPen(pen_glow)
        
        painter.drawRoundedRect(card_rect, 16, 16)

    def keyPressEvent(self, event):
        # Eat all key events to prevent bypassing
        event.accept()

    def mousePressEvent(self, event):
        # Eat mouse presses outside unlock
        event.accept()
