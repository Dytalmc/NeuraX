from PyQt6.QtCore import QObject, QEvent, Qt, QPoint, QPointF, QRectF
from PyQt6.QtWidgets import QAbstractButton
from PyQt6.QtGui import QColor, QIcon, QPixmap
from neurax.gui.icons import IconEngine

def create_monochrome_icon(icon_type: str, color: QColor = None, hover_color: QColor = QColor("#00F0FF"), size: int = 32, mode: str = "dark") -> QIcon:
    """Seamless facade delegating to the high-performance IconEngine with theme mode awareness."""
    if color is None:
        color = QColor("#FFFFFF") if mode == "dark" else QColor("#1E293B")
    return IconEngine.get_icon(icon_type, color, hover_color, size)


class ButtonHoverFilter(QObject):
    """Global event filter providing hover cursors specifically for buttons."""

    def eventFilter(self, obj, event):
        if isinstance(obj, QAbstractButton) and obj.isEnabled():
            if event.type() == QEvent.Type.Enter:
                obj.setCursor(Qt.CursorShape.PointingHandCursor)
        return super().eventFilter(obj, event)


class Theme:
    """Cyber-Glassmorphic Luxury Dual Theme Engine (Dark & Pure White Light Mode) with dynamic accent color propagation."""

    CYAN = "#00F0FF"
    PURPLE = "#A100FF"
    EMERALD = "#00FF99"
    ORANGE = "#FF6600"

    ACCENTS = {
        "Cyan": CYAN,
        "Purple": PURPLE,
        "Emerald": EMERALD,
        "Orange": ORANGE
    }

    MODES = ["dark", "light"]

    @staticmethod
    def get_text_color(mode: str = "dark") -> str:
        return "#FFFFFF" if mode == "dark" else "#000000"

    @staticmethod
    def get_muted_text_color(mode: str = "dark") -> str:
        return "#FFFFFF" if mode == "dark" else "#1E293B"

    @staticmethod
    def get_bg_color(mode: str = "dark") -> str:
        return "#07090E" if mode == "dark" else "#FFFFFF"

    @staticmethod
    def get_card_bg(mode: str = "dark") -> str:
        return "rgba(13, 16, 23, 0.88)" if mode == "dark" else "#FFFFFF"

    @staticmethod
    def get_icon_color(mode: str = "dark") -> QColor:
        return QColor("#FFFFFF") if mode == "dark" else QColor("#1E293B")

    @classmethod
    def get_stylesheet(cls, accent_color: str = CYAN, mode: str = "dark") -> str:
        is_dark = (mode == "dark")
        color = QColor(accent_color)

        dark_color = color.darker(150).name()
        hover_color = color.lighter(125).name()
        semi_trans = f"rgba({color.red()}, {color.green()}, {color.blue()}, 0.15)"
        semi_trans_hover = f"rgba({color.red()}, {color.green()}, {color.blue()}, 0.28)"
        glow_shadow = f"rgba({color.red()}, {color.green()}, {color.blue()}, 0.35)"
        svg_color = f"%23{color.red():02x}{color.green():02x}{color.blue():02x}"

        if is_dark:
            # DARK MODE PALETTE (ALL TEXT WHITE, ALL BACKGROUNDS DARK)
            bg_main = "#07090E"
            bg_surface = "rgba(13, 16, 23, 0.88)"
            bg_surface_hover = "rgba(20, 25, 36, 0.95)"
            border_subtle = "rgba(255, 255, 255, 0.10)"
            border_input = "rgba(255, 255, 255, 0.15)"
            text_primary = "#FFFFFF"
            text_secondary = "#FFFFFF"
            text_muted = "#F1F5F9"
            input_bg = "rgba(18, 22, 31, 0.85)"
            input_bg_focus = "rgba(23, 29, 42, 0.95)"
            dropdown_bg = "#0A0D14"
            dropdown_item_color = "#FFFFFF"
            list_item_bg = "rgba(14, 17, 24, 0.75)"
            btn_sec_bg = "rgba(255, 255, 255, 0.06)"
            btn_sec_hover = semi_trans
            btn_sec_border = "rgba(255, 255, 255, 0.14)"
            nav_bg = "rgba(10, 13, 19, 0.92)"
            nav_text = "#FFFFFF"
            scroll_bg = "rgba(7, 9, 14, 0.6)"
            scroll_handle = "rgba(255, 255, 255, 0.22)"
            chk_bg = "#090B10"
            chk_border = "rgba(255, 255, 255, 0.35)"
            chk_tick_stroke = "%23FFFFFF"
            tab_bar_bg = "rgba(14, 18, 26, 0.75)"
            header_bar_bg = "rgba(13, 16, 23, 0.85)"
            console_bg = "#05070B"
            console_color = "#00FF99"
        else:
            # PURE WHITE LIGHT MODE PALETTE (ALL BACKGROUNDS 100% WHITE, ALL TEXT BLACK)
            bg_main = "#FFFFFF"
            bg_surface = "#FFFFFF"
            bg_surface_hover = "#FFFFFF"
            border_subtle = "rgba(0, 0, 0, 0.14)"
            border_input = "rgba(0, 0, 0, 0.22)"
            text_primary = "#000000"
            text_secondary = "#000000"
            text_muted = "#1E293B"
            input_bg = "#FFFFFF"
            input_bg_focus = "#FFFFFF"
            dropdown_bg = "#FFFFFF"
            dropdown_item_color = "#000000"
            list_item_bg = "#FFFFFF"
            btn_sec_bg = "#FFFFFF"
            btn_sec_hover = semi_trans
            btn_sec_border = "rgba(0, 0, 0, 0.20)"
            nav_bg = "#FFFFFF"
            nav_text = "#000000"
            scroll_bg = "#FFFFFF"
            scroll_handle = "rgba(0, 0, 0, 0.25)"
            chk_bg = "#FFFFFF"
            chk_border = "rgba(0, 0, 0, 0.35)"
            chk_tick_stroke = "%23FFFFFF"
            tab_bar_bg = "#FFFFFF"
            header_bar_bg = "#FFFFFF"
            console_bg = "#111827"
            console_color = "#00FF99"

        return f"""
        QMainWindow, QDialog {{
            background-color: {bg_main};
            color: {text_primary};
            font-family: 'Segoe UI', 'Inter', -apple-system, sans-serif;
            font-size: 13px;
        }}

        QWidget {{
            color: {text_primary};
            font-family: 'Segoe UI', 'Inter', sans-serif;
            font-size: 13px;
        }}

        QWidget#centralWidget, QWidget#rightPane, QWidget#scrollWidget {{
            background-color: {bg_main};
            color: {text_primary};
        }}

        QScrollArea {{
            background-color: {bg_main};
            background: {bg_main};
            border: none;
        }}

        QScrollArea > QWidget > QWidget {{
            background-color: {bg_main};
            background: {bg_main};
        }}

        /* Universal Text Labels */
        QLabel {{
            color: {text_primary};
            font-family: 'Segoe UI', 'Inter', sans-serif;
        }}

        /* Glass & Surface Panels */
        QFrame#GlassCard, QFrame#HeaderBar {{
            background-color: {bg_surface};
            border: 1px solid {border_subtle};
            border-radius: 14px;
        }}

        QFrame#NavPanel {{
            background-color: {nav_bg};
            border: 1px solid {border_subtle};
            border-radius: 14px;
        }}

        QFrame#GlassCard:hover {{
            background-color: {bg_surface_hover};
            border: 1.5px solid {accent_color};
        }}

        /* Checkboxes */
        QCheckBox {{
            color: {text_primary};
            spacing: 8px;
            font-size: 13px;
            font-weight: 500;
        }}
        QCheckBox::indicator {{
            width: 17px;
            height: 17px;
            background-color: {chk_bg};
            border: 1.5px solid {chk_border};
            border-radius: 5px;
        }}
        QCheckBox::indicator:hover {{
            border-color: {accent_color};
        }}
        QCheckBox::indicator:checked {{
            background-color: {accent_color};
            border: 1.5px solid {accent_color};
            image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M2 6l3 3 5-5' stroke='{chk_tick_stroke}' stroke-width='2.4' stroke-linecap='round' stroke-linejoin='round' fill='none'/></svg>");
        }}
        QCheckBox::indicator:checked:hover {{
            background-color: {hover_color};
            border-color: {hover_color};
        }}

        /* Radio Buttons */
        QRadioButton {{
            color: {text_primary};
            spacing: 8px;
            font-size: 13px;
            font-weight: 500;
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            background-color: {chk_bg};
            border: 1.5px solid {chk_border};
            border-radius: 8px;
        }}
        QRadioButton::indicator:checked {{
            background-color: {accent_color};
            border: 1.5px solid {accent_color};
        }}

        /* Modern Custom Scrollbars */
        QScrollBar:vertical {{
            border: none;
            background: {scroll_bg};
            width: 8px;
            border-radius: 4px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {scroll_handle};
            min-height: 24px;
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {accent_color};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QScrollBar:horizontal {{
            border: none;
            background: {scroll_bg};
            height: 8px;
            border-radius: 4px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background: {scroll_handle};
            min-width: 24px;
            border-radius: 4px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {accent_color};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            background: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}

        /* Inputs & Modern Dropdowns */
        QLineEdit, QSpinBox, QTextBrowser, QTextEdit {{
            background-color: {input_bg};
            border: 1.5px solid {border_input};
            border-radius: 8px;
            padding: 6px 12px;
            min-height: 24px;
            color: {text_primary};
            font-size: 13px;
        }}
        QLineEdit:focus, QTextBrowser:focus, QTextEdit:focus {{
            border: 1.5px solid {accent_color};
            background-color: {input_bg_focus};
        }}

        QPlainTextEdit {{
            background-color: {console_bg};
            color: {console_color};
            border: 1.5px solid {border_input};
            border-radius: 8px;
            padding: 8px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
        }}
        QPlainTextEdit:focus {{
            border: 1.5px solid {accent_color};
        }}

        QComboBox {{
            background-color: {input_bg};
            border: 1.5px solid {border_input};
            border-radius: 8px;
            padding: 6px 12px;
            min-height: 24px;
            color: {text_primary};
            font-size: 13px;
            font-weight: 600;
        }}
        QComboBox:hover {{
            border-color: {accent_color};
        }}
        QComboBox:focus, QComboBox:on {{
            border: 1.5px solid {accent_color};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 26px;
            border-left: none;
        }}
        QComboBox::down-arrow {{
            image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'><path d='M2 4l4 4 4-4' stroke='{svg_color}' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round' fill='none'/></svg>");
            width: 12px;
            height: 12px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {dropdown_bg};
            border: 1.5px solid {accent_color};
            border-radius: 8px;
            color: {dropdown_item_color};
            selection-background-color: {semi_trans_hover};
            selection-color: {text_primary};
            padding: 6px;
            outline: none;
        }}
        QComboBox QAbstractItemView::item {{
            min-height: 28px;
            padding: 4px 10px;
            border-radius: 6px;
            color: {dropdown_item_color};
        }}
        QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {{
            background-color: {semi_trans};
            color: {text_primary};
            font-weight: bold;
        }}

        /* Buttons */
        QPushButton#PrimaryButton {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {accent_color}, stop:1 {dark_color});
            color: #FFFFFF;
            font-weight: 800; 
            font-size: 13px;
            border: 1px solid {accent_color};
            border-radius: 8px;
            padding: 8px 20px;
            min-height: 28px;
            letter-spacing: 0.5px;
        }}
        QPushButton#PrimaryButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {hover_color}, stop:1 {accent_color});
            border-color: {hover_color};
            color: #FFFFFF;
        }}
        QPushButton#PrimaryButton:pressed {{
            background-color: {dark_color};
            color: #FFFFFF;
        }}
        QPushButton#PrimaryButton:disabled {{
            background-color: rgba(120, 120, 120, 0.25);
            border-color: rgba(120, 120, 120, 0.35);
            color: rgba(255, 255, 255, 0.6);
        }}

        QPushButton#SecondaryButton {{
            background-color: {btn_sec_bg};
            border: 1.5px solid {btn_sec_border};
            color: {text_primary};
            border-radius: 8px;
            padding: 6px 14px;
            font-size: 13px;
            min-height: 22px;
            font-weight: 600;
        }}
        QPushButton#SecondaryButton:hover {{
            background-color: {btn_sec_hover};
            border-color: {accent_color};
            color: {text_primary};
        }}
        QPushButton#SecondaryButton:pressed {{
            background-color: {semi_trans_hover};
        }}
        QPushButton#SecondaryButton[active="true"] {{
            background-color: {semi_trans_hover};
            border: 1.5px solid {accent_color};
            color: {accent_color};
            font-weight: 800;
        }}

        /* Mode Selection Buttons */
        QPushButton#ModeButton {{
            background-color: {btn_sec_bg};
            border: 1.5px solid {btn_sec_border};
            color: {text_primary};
            border-radius: 8px;
            padding: 8px 16px;
            font-size: 13px;
            font-weight: 700;
        }}
        QPushButton#ModeButton:hover {{
            border-color: {accent_color};
            background-color: {semi_trans};
        }}
        QPushButton#ModeButton[active="true"] {{
            background-color: {semi_trans_hover};
            border: 1.5px solid {accent_color};
            color: {accent_color};
            font-weight: 800;
        }}

        /* Nav Bar Buttons */
        QPushButton#NavButton {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {nav_text};
            text-align: left;
            padding: 10px 16px;
            font-size: 13px;
            font-weight: 700;
            min-height: 24px;
        }}
        QPushButton#NavButton:hover {{
            background-color: {btn_sec_hover};
            color: {text_primary};
        }}
        QPushButton#NavButton[active="true"] {{
            background-color: transparent;
            color: {accent_color};
            font-weight: 800;
            border: none;
        }}

        /* Sub Tab Bar */
        QFrame#SubTabBar {{
            background-color: {tab_bar_bg};
            border: 1.5px solid {border_subtle};
            border-radius: 12px;
        }}
        QPushButton#SubTabButton {{
            background: transparent;
            border: none;
            border-radius: 8px;
            color: {text_primary};
            text-align: center;
            padding: 8px 18px;
            font-size: 13px;
            font-weight: 700; 
            min-height: 22px;
        }}
        QPushButton#SubTabButton:hover {{
            color: {accent_color};
        }}
        QPushButton#SubTabButton[active="true"] {{
            color: {accent_color};
            font-weight: 800;
        }}

        /* Sliders */
        QSlider::groove:horizontal {{
            height: 6px;
            background: {border_input};
            border-radius: 3px;
        }}
        QSlider::sub-page:horizontal {{
            background: {accent_color};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {text_primary};
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {accent_color};
        }}

        /* Unified List Widgets */
        QListWidget {{
            background: transparent;
            border: none;
            outline: none;
        }}
        QListWidget:focus {{
            outline: none;
            border: none;
        }}
        QListWidget::item {{
            background: {list_item_bg};
            border: 1.5px solid {border_subtle};
            border-radius: 10px;
            padding: 12px 14px;
            margin-bottom: 8px;
            font-size: 13px;
            font-weight: 600;
            color: {text_primary};
            outline: none;
        }}
        QListWidget::item:hover {{
            background: {btn_sec_hover};
            border-color: {accent_color};
            color: {text_primary};
            outline: none;
        }}
        QListWidget::item:selected {{
            background: {semi_trans};
            border-color: {accent_color};
            color: {text_primary};
            font-weight: 700;
            outline: none;
        }}

        /* Tree Widgets */
        QTreeWidget {{
            background-color: {list_item_bg};
            border: 1.5px solid {border_subtle};
            border-radius: 8px;
            padding: 6px;
            color: {text_primary};
        }}
        QTreeWidget::item {{
            color: {text_primary};
            padding: 4px;
            border-radius: 4px;
        }}
        QTreeWidget::item:hover {{
            background-color: {semi_trans};
        }}
        QTreeWidget::item:selected {{
            background-color: {semi_trans_hover};
            color: {accent_color};
            font-weight: bold;
        }}

        /* Progress Bars */
        QProgressBar {{
            background: {border_input};
            border-radius: 3px;
            border: none;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent_color}, stop:1 {hover_color});
            border-radius: 3px;
        }}
        """
