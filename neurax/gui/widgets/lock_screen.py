import math
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
<<<<<<< HEAD
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer, pyqtProperty
=======
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QTimer
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QPixmap
from neurax.gui.icons import IconEngine

class LockScreenOverlay(QWidget):
<<<<<<< HEAD
    """An immersive, highly animated fullscreen lock screen overlay for NeuraX launcher.

    Two flavours of lock:

    1. **Local AFK lock** (`launcher_locked` config flag). The launcher
       itself can clear it via the unlock button.
    2. **Remote lock from nx.py**. The launcher CANNOT clear it from
       inside the UI; only nx.py (running on any machine with the
       Supabase anon key) can do that. The unlock button is hidden
       in this mode.

    Both modes share the same visual: pulsing shield, red glow, slide-in,
    grid background. A short shake animation fires whenever a remote
    unlock check fails, so the user gets immediate feedback that the
    admin hasn't lifted the lock yet.
    """
=======
    """An immersive, highly animated fullscreen lock screen overlay for NeuraX launcher."""
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.is_active = False
<<<<<<< HEAD
        # Source of the active lock: "local" or "remote". Controls
        # whether the unlock button is shown.
        self._lock_source = "local"
        # Custom message supplied by the remote admin. Empty string
        # means "use the default subtitle".
        self._remote_message = ""

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Don't let the layout engine shrink us — we always fill the
        # parent and ignore the inner QVBoxLayout's minimum-size
        # preference (which would otherwise cap us at the glow card's
        # ~540×510 area and leave the rest of the window clickable).
        self.setMinimumSize(0, 0)
        self.hide()

        # Track parent resizes. The overlay's job is to fill the
        # parent at all times, so we install ourselves as an event
        # filter on the parent and resize ourselves on every
        # ``QEvent.Resize`` it receives. This is what makes the lock
        # screen follow window maximising / restoring / DPI changes
        # without a custom resizeEvent on the parent.
        if parent is not None:
            try:
                parent.installEventFilter(self)
                self._parent_ref = parent
            except Exception:
                self._parent_ref = None
        else:
            self._parent_ref = None

=======
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        # UI elements
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(40, 40, 40, 40)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.glow_card = QWidget(self)
<<<<<<< HEAD
        self.glow_card.setFixedSize(460, 440)
        self.glow_card.setObjectName("LockCard")

        # Glow Card Layout
        card_layout = QVBoxLayout(self.glow_card)
        card_layout.setContentsMargins(30, 40, 30, 30)
        card_layout.setSpacing(14)
=======
        self.glow_card.setFixedSize(450, 400)
        self.glow_card.setObjectName("LockCard")
        
        # Glow Card Layout
        card_layout = QVBoxLayout(self.glow_card)
        card_layout.setContentsMargins(30, 40, 30, 30)
        card_layout.setSpacing(20)
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
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
<<<<<<< HEAD
        self.subtitle_lbl.setStyleSheet("font-size: 13px; color: #E2E8F0;")
        self.subtitle_lbl.setWordWrap(True)
        card_layout.addWidget(self.subtitle_lbl)

        # Custom message from the remote admin — only populated when a
        # remote lock is active. Initially empty/hidden.
        self.message_lbl = QLabel("")
        self.message_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_lbl.setStyleSheet(
            "font-size: 13px; color: #FCA5A5; padding: 10px 14px; "
            "background-color: rgba(255, 51, 102, 0.10); "
            "border: 1px solid rgba(255, 51, 102, 0.45); "
            "border-radius: 8px;"
        )
        self.message_lbl.setWordWrap(True)
        self.message_lbl.hide()
        card_layout.addWidget(self.message_lbl)

        # Footer caption telling the user how to recover (different
        # copy per lock source).
        self.footer_lbl = QLabel("")
        self.footer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer_lbl.setStyleSheet("font-size: 11px; color: #64748B; padding-top: 4px;")
        self.footer_lbl.setWordWrap(True)
        card_layout.addWidget(self.footer_lbl)

        # Unlock button — local-mode only. We always create it so the
        # layout doesn't reflow when toggling lock source, but we hide
        # it under remote lock.
=======
        self.subtitle_lbl.setStyleSheet("font-size: 13px;")
        self.subtitle_lbl.setWordWrap(True)
        card_layout.addWidget(self.subtitle_lbl)

        # Unlock button
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
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
<<<<<<< HEAD
        # Horizontal shake when the launcher re-checks a still-locked
        # state. Triggers a short back-and-forth animation of the card.
        self._shake_timer = None  # type: ignore[var-annotated]

    # ------------------------------------------------------------------ API
    def show_locked(self, source: str = "local", message: str = ""):
        """Show the lock overlay.

        ``source`` is either ``"local"`` (AFK lock, unlock button
        visible) or ``"remote"`` (lock from nx.py, unlock button
        hidden). ``message`` is the optional custom message the admin
        set; it appears on the overlay card.

        Geometry: the overlay always fills its parent's full rect so
        clicks anywhere in the window are blocked. We DO NOT animate
        ``pos`` (top-left corner) because that used to leave the
        overlay visually anchored at (0, 0) with its size still
        determined by the constructor-time parent rect — which on a
        cold restart is often (0, 0, 0, 0), making the overlay appear
        only in the top-left corner until something triggered a
        resize. Instead we animate windowOpacity for the fade-in
        effect and let geometry track the parent.
        """
        if self.is_active:
            # Already showing — update message in case the admin
            # changed it, and re-apply the source rules.
            self.set_lock_source(source, message)
            return
        self.is_active = True
        self.set_lock_source(source, message)
        # Make sure we cover the parent area BEFORE show() runs, so the
        # first paint is full-area and no clicks leak through to
        # widgets behind us.
        self._sync_to_parent()
=======

    def show_locked(self):
        if self.is_active:
            return
        self.is_active = True
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.show()
        self.raise_()
        self.setFocus()
        self.grabKeyboard()
        self.pulse_timer.start()

<<<<<<< HEAD
        # Opacity fade-in (cleaner than the old slide, and never
        # mis-positions the overlay).
        self.setWindowOpacity(0.0)
        self.anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.anim.setDuration(350)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.start()
        # Fire the initial shake so the user immediately sees that
        # something dramatic happened.
        self._shake()

    def _sync_to_parent(self) -> None:
        """Resize ourselves to fill the parent's full rect.

        Called on every ``showEvent`` AND whenever the parent resizes
        (via the event filter installed in ``__init__``). The overlay
        is parented to ``MainWindow.centralWidget()``, so this is the
        central area — nav bar, header, status bar, everything in the
        launcher window. Click events landing on any of those widgets
        are intercepted here first.
        """
        parent = self.parentWidget()
        if parent is None:
            return
        try:
            # ``parent.rect()`` is in parent's coordinate space;
            # ``setGeometry`` without parent-coord translation is fine
            # because we are a direct child of ``parent``.
            self.setGeometry(parent.rect())
        except Exception:
            # Best effort — never let geometry sync crash the overlay.
            pass

    def showEvent(self, event):
        """Re-sync geometry every time we become visible.

        On cold restart the parent's rect at construction time may be
        (0, 0, 0, 0) because Qt hasn't run a layout yet. By the time
        ``showEvent`` fires (the launcher is about to render), the
        parent has a real size and we can latch onto it. This is what
        makes the overlay fill the screen on first paint, instead of
        sitting at (0, 0) at default size until something forces a
        relayout.
        """
        super().showEvent(event)
        self._sync_to_parent()

    def hideEvent(self, event):
        """Drop focus + keyboard grab when we go away so the rest of
        the UI works again."""
        try:
            self.releaseKeyboard()
        except Exception:
            pass
        super().hideEvent(event)

    def eventFilter(self, obj, event):
        """Re-sync our geometry every time the parent resizes.

        This is what makes the lock fill the window when the launcher
        is maximised, restored, or DPI-changed. We only care about
        ``QEvent.Resize`` on the parent widget — every other event
        passes through unmodified.
        """
        try:
            if obj is getattr(self, "_parent_ref", None) and event.type() == event.Type.Resize:
                # Don't fight an in-progress manual setsetGeometry
                # (e.g. during _enforce_remote_lock); just sync once
                # the parent has finished resizing.
                self._sync_to_parent()
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def set_lock_source(self, source: str, message: str = ""):
        """Update the source + custom message without re-running the
        slide-in animation. Safe to call every heartbeat."""
        self._lock_source = source if source in ("local", "remote") else "local"
        self._remote_message = (message or "").strip()
        if self._lock_source == "remote":
            self.unlock_btn.hide()
            if self._remote_message:
                self.message_lbl.setText(self._remote_message)
                self.message_lbl.show()
            else:
                self.message_lbl.setText("")
                self.message_lbl.hide()
            self.footer_lbl.setText(
                "This launcher was locked remotely via nx.py.\n"
                "Only the admin who locked this device can unlock it."
            )
            self.title_lbl.setText("LOCKED REMOTELY")
            self.title_lbl.setStyleSheet(
                "font-size: 22px; font-weight: 900; color: #FF3366; letter-spacing: 3px;"
            )
        else:
            self.unlock_btn.show()
            self.message_lbl.hide()
            self.footer_lbl.setText(
                "This lock was set locally — tap UNLOCK LAUNCHER below to use the launcher again."
            )
            self.title_lbl.setText("LAUNCHER LOCKED")
            self.title_lbl.setStyleSheet(
                "font-size: 22px; font-weight: 900; color: #FF3366; letter-spacing: 3px;"
            )

    def is_remote_lock(self) -> bool:
        return self.is_active and self._lock_source == "remote"

    def notify_still_locked(self):
        """Called when a heartbeat re-check confirms the device is
        still locked. Briefly shakes the card so the user gets a
        visual cue that the admin hasn't lifted the lock."""
        if not self.is_active or self._lock_source != "remote":
            return
        self._shake()
=======
        # Smooth slide & fade-in animation
        self.move(0, -50)
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(400)
        self.anim.setStartValue(QPoint(0, -100))
        self.anim.setEndValue(QPoint(0, 0))
        self.anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self.anim.start()
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    def hide_unlocked(self):
        if not self.is_active:
            return
        self.is_active = False
        self.pulse_timer.stop()
        self.releaseKeyboard()
<<<<<<< HEAD

=======
        
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.anim = QPropertyAnimation(self, b"pos", self)
        self.anim.setDuration(300)
        self.anim.setStartValue(QPoint(0, 0))
        self.anim.setEndValue(QPoint(0, -self.height()))
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim.finished.connect(self.hide)
        self.anim.start()

<<<<<<< HEAD
    # ------------------------------------------------------------------ internal
    def _unlock_clicked(self):
        # Only the local AFK lock can be cleared from inside the
        # launcher. Remote locks deliberately have no button — the
        # method just no-ops to be safe in case the button ever
        # appears (e.g. via a network glitch).
        if self._lock_source != "local":
            self._shake()
            return
        self.config.set("launcher_locked", False)
        self.hide_unlocked()

    def _shake(self):
        """Run a short horizontal shake on the glow card to make the
        lock screen feel alive."""
        try:
            card = self.glow_card
            origin = card.pos()
            if self._shake_timer is not None:
                try:
                    self._shake_timer.stop()
                except Exception:
                    pass
            anim = QPropertyAnimation(card, b"pos", self)
            anim.setDuration(280)
            anim.setKeyValueAt(0.00, origin)
            anim.setKeyValueAt(0.10, origin + QPoint(-8, 0))
            anim.setKeyValueAt(0.25, origin + QPoint(7, 0))
            anim.setKeyValueAt(0.45, origin + QPoint(-5, 0))
            anim.setKeyValueAt(0.65, origin + QPoint(3, 0))
            anim.setKeyValueAt(1.00, origin)
            anim.start()
            self._shake_timer = anim
        except Exception:
            pass

=======
    def _unlock_clicked(self):
        self.config.set("launcher_locked", False)
        self.hide_unlocked()

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    def _pulse_tick(self):
        self.pulse_angle += 0.05
        pulse_scale = 1.0 + 0.08 * math.sin(self.pulse_angle)
        icon_size = max(48, int(64 * pulse_scale))
        self.icon_lbl.setPixmap(IconEngine.get_pixmap("shield", QColor("#FF3366"), icon_size))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

<<<<<<< HEAD
        # Draw a beautiful dark glassmorphic background overlay. Use a
        # red tint when remote-locked so the visual is unmistakable.
        if self._lock_source == "remote":
            base = QColor(15, 5, 8)
            accent = QColor("#FF3366")
        else:
            base = QColor(5, 5, 8)
            accent = QColor(self.config.get("accent_color", "#00F0FF"))

        bg_alpha = int(225 + 10 * math.sin(self.pulse_angle))
        painter.fillRect(self.rect(), QColor(base.red(), base.green(), base.blue(), bg_alpha))

        # Draw tech-lines
        pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 40))
        pen.setWidth(1)
        painter.setPen(pen)

=======
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
        
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        # Grid lines
        spacing = 40
        for x in range(0, self.width(), spacing):
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), spacing):
            painter.drawLine(0, y, self.width(), y)

        # Draw cool glowing card
        card_rect = self.glow_card.geometry()
        painter.setBrush(QBrush(QColor(15, 15, 22, 240)))
<<<<<<< HEAD

        glow_width = int(2.0 + 1.5 * math.sin(self.pulse_angle))
        pen_glow = QPen(QColor(accent.red(), accent.green(), accent.blue(), 180))
        pen_glow.setWidth(glow_width)
        painter.setPen(pen_glow)

        painter.drawRoundedRect(card_rect, 16, 16)

    def keyPressEvent(self, event):
        # Eat all key events to prevent bypassing. The only escape
        # from a remote lock is for nx.py to clear the flag.
=======
        
        glow_width = int(2.0 + 1.5 * math.sin(self.pulse_angle))
        pen_glow = QPen(QColor(c.red(), c.green(), c.blue(), 180))
        pen_glow.setWidth(glow_width)
        painter.setPen(pen_glow)
        
        painter.drawRoundedRect(card_rect, 16, 16)

    def keyPressEvent(self, event):
        # Eat all key events to prevent bypassing
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        event.accept()

    def mousePressEvent(self, event):
        # Eat mouse presses outside unlock
        event.accept()
