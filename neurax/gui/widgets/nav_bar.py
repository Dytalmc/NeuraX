from PyQt6.QtWidgets import QFrame, QVBoxLayout, QPushButton, QLabel, QHBoxLayout
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QRect, QEasingCurve, QSize
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen
from neurax.gui.icons import IconEngine

try:
    from users import CommunityChip as _CommunityChip
    _CHIP_OK = True
except Exception:
    _CHIP_OK = False
    _CommunityChip = None  # type: ignore

class NavButton(QPushButton):
    """Custom Navigation Button with dynamic vector icon and optional notification badge."""

    def __init__(self, text: str, icon_type: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("NavButton")
        self.icon_type = icon_type
        self.has_notification = False
        self.accent_color = "#00F0FF"
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_notification(self, active: bool):
        self.has_notification = active
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.has_notification:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor("#FF3366")))
            painter.setPen(QPen(QColor("#07090E"), 1.5))
            painter.drawEllipse(self.width() - 18, 12, 8, 8)
            painter.end()


class NavBar(QFrame):
    """Left Navigation Sidebar with vector QIcon tab indicators and animated glowing active indicator bar."""
    tab_changed = pyqtSignal(int)
<<<<<<< HEAD
=======
    community_chip_clicked = pyqtSignal()
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NavPanel")
        self.setFixedWidth(220)
        
        self.accent_color = "#00F0FF"
        self.theme_mode = "dark"
        self.buttons = []
        self.active_index = 0

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(12, 18, 12, 18)
        self.layout.setSpacing(6)

        # Brand Header with cyber glow
        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(12, 0, 12, 10)
        self.brand_lbl = QLabel("NEURAX")
        self.brand_lbl.setStyleSheet("font-size: 19px; font-weight: 900; color: #FFFFFF; letter-spacing: 4px;")
        brand_row.addWidget(self.brand_lbl)
        brand_row.addStretch()

        self.version_badge = QLabel("v4.0.0")
        self.version_badge.setStyleSheet(f"""
            background-color: rgba(0, 240, 255, 0.15);
            color: #00F0FF;
            border: 1px solid rgba(0, 240, 255, 0.4);
            border-radius: 6px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: 800;
        """)
        brand_row.addWidget(self.version_badge)
        self.layout.addLayout(brand_row)

        # Indicator bar
        self.indicator = QFrame(self)
        self.indicator.setObjectName("NavIndicator")
        self.indicator.setFixedWidth(3)
        self.indicator.setFixedHeight(28)
        self.indicator.setStyleSheet(f"background-color: {self.accent_color}; border-radius: 2px;")
        self.indicator.hide()

<<<<<<< HEAD
        # Tabs configuration — Community tab removed; only the sidebar chip
        # remains for the public online counter. Detailed community stats are
        # reachable via the standalone `nx.py` dashboard.
        self.tabs_config = [
            ("Play", "play"),
            ("Instances", "instances"),
=======
        # Tabs configuration
        self.tabs_config = [
            ("Play", "play"),
            ("Instances", "instances"),
            ("Versions", "versions"),
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
            ("Servers", "servers"),
            ("Modrinth", "modrinth"),
            ("Skins", "skins"),
            ("Gallery", "gallery"),
            ("Announcements", "news"),
            ("Settings", "settings"),
            ("New Server", "new_server"),
            ("AFK Zone", "afk")
        ]

        for idx, (name, icon_type) in enumerate(self.tabs_config):
            btn = NavButton(f"  {name}", icon_type, self)
            btn.clicked.connect(lambda checked, i=idx: self._on_btn_clicked(i))
            self.layout.addWidget(btn)
            self.buttons.append(btn)

        self.layout.addStretch()

        # Community chip — tiny "● N online" badge anchored at the bottom of
<<<<<<< HEAD
        # the sidebar. The chip keeps auto-refreshing every 5 minutes so the
        # live counter is always visible, but the in-launcher Community view
        # has been removed (the standalone `nx.py` dashboard replaces it).
=======
        # the sidebar. Click emits community_chip_clicked(index) so the main
        # window can switch to the Community view.
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
        self.community_chip = None
        if _CHIP_OK and _CommunityChip is not None:
            try:
                self.community_chip = _CommunityChip(self)
<<<<<<< HEAD
=======
                self.community_chip.clicked.connect(self._on_community_chip_clicked)
>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
                self.layout.addWidget(self.community_chip)
            except Exception:
                self.community_chip = None

        self.indicator_anim = QPropertyAnimation(self.indicator, b"geometry", self)
        self.indicator_anim.setDuration(180)
        self.indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_theme_mode(self, mode: str):
        self.theme_mode = mode
        text_color = "#FFFFFF" if mode == "dark" else "#000000"
        self.brand_lbl.setStyleSheet(f"font-size: 19px; font-weight: 900; color: {text_color}; letter-spacing: 4px;")
        self.set_accent_color(self.accent_color)

    def set_accent_color(self, color_hex: str):
        self.accent_color = color_hex
        c = QColor(color_hex)
        r, g, b = c.red(), c.green(), c.blue()
        self.indicator.setStyleSheet(f"background-color: {color_hex}; border-radius: 2px;")
        self.version_badge.setStyleSheet(f"""
            background-color: rgba({r}, {g}, {b}, 0.15);
            color: {color_hex};
            border: 1px solid {color_hex};
            border-radius: 6px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: 800;
        """)
        
        c = QColor(color_hex)
        normal_c = QColor("#FFFFFF") if self.theme_mode == "dark" else QColor("#1E293B")
        for idx, (name, icon_type) in enumerate(self.tabs_config):
            icon = IconEngine.get_icon(icon_type, normal_c, c, size=20)
            self.buttons[idx].setIcon(icon)
            self.buttons[idx].setIconSize(QSize(20, 20))
            self.buttons[idx].accent_color = color_hex
            
        self.set_active_tab(self.active_index)

    def _on_btn_clicked(self, index: int):
        self.set_active_tab(index)
        self.tab_changed.emit(index)

<<<<<<< HEAD
=======
    def _on_community_chip_clicked(self):
        """User clicked the '● N online' chip at the bottom of the sidebar."""
        # Bump the indicator onto the last real tab (AFK Zone) so the user
        # sees *some* nav feedback. The actual view switch is owned by the
        # main window, which listens to community_chip_clicked.
        if self.buttons:
            self.set_active_tab(len(self.buttons) - 1)
        self.community_chip_clicked.emit()

>>>>>>> 58ef251b48a95b0e95d454002d3ac1e332f91ab0
    def set_active_tab(self, index: int):
        if index < 0 or index >= len(self.buttons):
            return
        self.active_index = index
        self.indicator.show()

        for idx, btn in enumerate(self.buttons):
            active = (idx == index)
            btn.setChecked(active)
            btn.setProperty("active", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        btn = self.buttons[index]
        btn_geom = btn.geometry()
        if btn_geom.width() > 0 and btn_geom.height() > 0:
            target_rect = QRect(4, btn_geom.y() + (btn_geom.height() - 28) // 2, 4, 28)
            self.indicator_anim.stop()
            self.indicator_anim.setStartValue(self.indicator.geometry())
            self.indicator_anim.setEndValue(target_rect)
            self.indicator_anim.start()

    def set_announcement_notification(self, active: bool):
        for idx, (name, icon_type) in enumerate(self.tabs_config):
            if icon_type == "news" and idx < len(self.buttons):
                self.buttons[idx].set_notification(active)

    def refresh_community_chip(self):
        """Force the sidebar chip to re-fetch the online counter."""
        if self.community_chip is not None and hasattr(self.community_chip, "_refresh"):
            try:
                self.community_chip._refresh()
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.buttons:
            btn = self.buttons[self.active_index]
            btn_geom = btn.geometry()
            if btn_geom.width() > 0:
                self.indicator.setGeometry(4, btn_geom.y() + (btn_geom.height() - 28) // 2, 4, 28)
