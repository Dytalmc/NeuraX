import math
from typing import Dict, Tuple, Optional
from PyQt6.QtCore import Qt, QPointF, QRectF, QSize
from PyQt6.QtGui import QColor, QIcon, QPixmap, QPainter, QPen, QBrush, QPolygonF, QPainterPath

class IconEngine:
    """High-Performance Scalable Vector Icon Engine for NeuraX.
    Renders sharp, mathematical vector geometry using anti-aliased QPainterPath
    and supports dynamic accent color tinting across normal, hover, and active states.
    """

    AVAILABLE_ICONS = {
        "play", "instances", "versions", "servers", "modrinth", "skins", "gallery",
        "news", "settings", "new_server", "afk", "hamburger", "bug", "ai_radar",
        "crash_analyzer", "plus", "refresh", "trash", "edit", "copy", "folder",
        "search", "download", "check", "warning", "close", "save", "terminal",
        "shield", "cloud", "lock", "unlock", "sparkles", "cpu", "ram", "globe",
        "zap", "package", "cube", "link", "chevron_down", "chevron_up",
        "chevron_right", "chevron_left", "play_triangle", "stop_square",
        "sun", "moon", "palette"
    }

    _cache: Dict[Tuple[str, str, str, int], QIcon] = {}

    @classmethod
    def get_icon(cls, icon_type: str, color: QColor = QColor("#8A94A6"), hover_color: QColor = QColor("#00F0FF"), size: int = 32) -> QIcon:
        """Retrieve cached vector QIcon with normal and hover states."""
        key = (icon_type, color.name(QColor.NameFormat.HexArgb), hover_color.name(QColor.NameFormat.HexArgb), size)
        if key in cls._cache:
            return cls._cache[key]

        icon = QIcon()

        # Normal State Pixmap
        pix_normal = cls.get_pixmap(icon_type, color, size)
        icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)

        # Hover / Active / Selected State Pixmap
        pix_hover = cls.get_pixmap(icon_type, hover_color, size)
        icon.addPixmap(pix_hover, QIcon.Mode.Active, QIcon.State.Off)
        icon.addPixmap(pix_hover, QIcon.Mode.Selected, QIcon.State.Off)

        # Disabled State Pixmap
        disabled_c = QColor(color)
        disabled_c.setAlpha(80)
        pix_disabled = cls.get_pixmap(icon_type, disabled_c, size)
        icon.addPixmap(pix_disabled, QIcon.Mode.Disabled, QIcon.State.Off)

        cls._cache[key] = icon
        return icon

    @classmethod
    def get_pixmap(cls, icon_type: str, color: QColor, size: int = 32) -> QPixmap:
        """Render individual vector pixmap with anti-aliasing."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        scale_factor = size / 32.0
        painter.scale(scale_factor, scale_factor)

        pen = QPen(color)
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        cls._draw_vector_shape(painter, icon_type, color)
        painter.end()

        return pixmap

    @classmethod
    def _draw_vector_shape(cls, p: QPainter, name: str, c: QColor):
        p.setBrush(QBrush(Qt.GlobalColor.transparent))

        if name == "play":
            # Sleek Gamepad Controller
            path = QPainterPath()
            path.moveTo(7, 12)
            path.cubicTo(7, 8, 25, 8, 25, 12)
            path.cubicTo(27, 18, 26, 25, 23, 25)
            path.cubicTo(20, 25, 18, 20, 16, 20)
            path.cubicTo(14, 20, 12, 25, 9, 25)
            path.cubicTo(6, 25, 5, 18, 7, 12)
            p.drawPath(path)
            # D-pad cross & Action buttons
            p.drawLine(10, 13, 10, 17)
            p.drawLine(8, 15, 12, 15)
            p.drawEllipse(19, 13, 2, 2)
            p.drawEllipse(22, 15, 2, 2)

        elif name == "instances":
            # Isometric 3D Hex Crate / Package
            p.drawPolygon(QPolygonF([QPointF(16, 5), QPointF(26, 11), QPointF(16, 17), QPointF(6, 11)]))
            p.drawLine(6, 11, 6, 22)
            p.drawLine(26, 11, 26, 22)
            p.drawLine(16, 17, 16, 28)
            p.drawLine(6, 22, 16, 28)
            p.drawLine(26, 22, 16, 28)

        elif name == "versions":
            # Cyber Lightning Bolt
            path = QPainterPath()
            path.moveTo(18, 4)
            path.lineTo(8, 16)
            path.lineTo(15, 16)
            path.lineTo(13, 28)
            path.lineTo(24, 14)
            path.lineTo(17, 14)
            path.closeSubpath()
            p.setBrush(QBrush(c))
            p.drawPath(path)
            p.setBrush(QBrush(Qt.GlobalColor.transparent))

        elif name == "servers":
            # High-Tech Server Rack
            p.drawRoundedRect(5, 6, 22, 7, 2, 2)
            p.drawRoundedRect(5, 15, 22, 7, 2, 2)
            p.drawRoundedRect(5, 24, 22, 4, 1, 1)
            p.drawEllipse(8, 9, 2, 2)
            p.drawEllipse(8, 18, 2, 2)
            p.drawLine(13, 9, 23, 9)
            p.drawLine(13, 18, 23, 18)

        elif name == "modrinth":
            # Modrinth Hexagonal Shield Node
            hex_pts = QPolygonF([
                QPointF(16, 4), QPointF(26, 10), QPointF(26, 22),
                QPointF(16, 28), QPointF(6, 22), QPointF(6, 10)
            ])
            p.drawPolygon(hex_pts)
            p.drawLine(11, 11, 11, 21)
            p.drawLine(21, 11, 21, 21)
            p.drawLine(11, 11, 16, 16)
            p.drawLine(21, 11, 16, 16)

        elif name == "skins":
            # User Avatar / Persona Glyph
            p.drawEllipse(11, 6, 10, 10)
            path = QPainterPath()
            path.moveTo(5, 27)
            path.cubicTo(5, 20, 11, 18, 16, 18)
            path.cubicTo(21, 18, 27, 20, 27, 27)
            p.drawPath(path)

        elif name == "gallery":
            # Shutter Camera / Photo Canvas
            p.drawRoundedRect(5, 8, 22, 17, 3, 3)
            p.drawEllipse(19, 11, 3, 3)
            p.drawPolyline(QPolygonF([QPointF(7, 22), QPointF(13, 15), QPointF(17, 20), QPointF(21, 16), QPointF(25, 22)]))

        elif name == "news":
            # Megaphone Broadcast
            p.drawPolygon(QPolygonF([QPointF(6, 14), QPointF(16, 9), QPointF(16, 23), QPointF(6, 18)]))
            p.drawLine(11, 16, 9, 24)
            p.drawArc(19, 11, 8, 10, -45 * 16, 90 * 16)

        elif name == "settings":
            # Precision Engineering Cog
            p.drawEllipse(10, 10, 12, 12)
            p.drawEllipse(13, 13, 6, 6)
            for i in range(8):
                rad = i * math.pi / 4
                x1 = 16.0 + 6.0 * math.cos(rad)
                y1 = 16.0 + 6.0 * math.sin(rad)
                x2 = 16.0 + 10.0 * math.cos(rad)
                y2 = 16.0 + 10.0 * math.sin(rad)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        elif name == "new_server":
            # Server Terminal with Plus Overlay
            p.drawRoundedRect(5, 5, 22, 11, 2, 2)
            p.drawEllipse(8, 10, 2, 2)
            p.drawLine(13, 10, 22, 10)
            p.drawLine(16, 19, 16, 27)
            p.drawLine(12, 23, 20, 23)

        elif name == "afk":
            # Pulse Sleep Clock
            p.drawEllipse(6, 6, 20, 20)
            p.drawLine(16, 16, 16, 11)
            p.drawLine(16, 16, 20, 16)

        elif name == "hamburger":
            p.drawLine(6, 10, 26, 10)
            p.drawLine(6, 16, 26, 16)
            p.drawLine(6, 22, 26, 22)

        elif name == "bug":
            p.drawEllipse(10, 11, 12, 14)
            p.setBrush(QBrush(c))
            p.drawEllipse(13, 6, 6, 6)
            p.setBrush(QBrush(Qt.GlobalColor.transparent))
            p.drawLine(10, 14, 5, 12)
            p.drawLine(10, 18, 4, 18)
            p.drawLine(10, 22, 5, 24)
            p.drawLine(22, 14, 27, 12)
            p.drawLine(22, 18, 28, 18)
            p.drawLine(22, 22, 27, 24)
            p.drawLine(16, 12, 16, 25)

        elif name in ("ai_radar", "ai"):
            # Neural Circuit / AI Brain Node
            p.drawEllipse(12, 12, 8, 8)
            p.drawEllipse(5, 8, 4, 4)
            p.drawEllipse(23, 8, 4, 4)
            p.drawEllipse(5, 20, 4, 4)
            p.drawEllipse(23, 20, 4, 4)
            p.drawLine(QPointF(8.5, 9.5), QPointF(12.5, 13.5))
            p.drawLine(QPointF(23.5, 9.5), QPointF(19.5, 13.5))
            p.drawLine(QPointF(8.5, 20.5), QPointF(12.5, 17.5))
            p.drawLine(QPointF(23.5, 20.5), QPointF(19.5, 17.5))

        elif name == "crash_analyzer":
            # Diagnostic Stethoscope / Crosshair Shield
            p.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(26, 9), QPointF(26, 18), QPointF(16, 28), QPointF(6, 18), QPointF(6, 9)]))
            p.drawLine(16, 10, 16, 18)
            p.drawPoint(16, 22)

        elif name == "plus":
            p.drawLine(16, 7, 16, 25)
            p.drawLine(7, 16, 25, 16)

        elif name == "refresh":
            p.drawArc(7, 7, 18, 18, 30 * 16, 290 * 16)
            p.drawLine(22, 10, 26, 10)
            p.drawLine(26, 6, 26, 10)

        elif name == "trash":
            p.drawLine(7, 9, 25, 9)
            p.drawLine(12, 6, 20, 6)
            p.drawPolyline(QPolygonF([QPointF(9, 9), QPointF(10, 26), QPointF(22, 26), QPointF(23, 9)]))
            p.drawLine(13, 13, 13, 22)
            p.drawLine(19, 13, 19, 22)

        elif name == "edit":
            path = QPainterPath()
            path.moveTo(6, 26)
            path.lineTo(11, 25)
            path.lineTo(24, 12)
            path.lineTo(20, 8)
            path.lineTo(7, 21)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "copy":
            p.drawRoundedRect(11, 6, 14, 17, 2, 2)
            p.drawPolyline(QPolygonF([QPointF(8, 10), QPointF(6, 10), QPointF(6, 26), QPointF(20, 26), QPointF(20, 24)]))

        elif name == "folder":
            p.drawPolygon(QPolygonF([QPointF(5, 8), QPointF(12, 8), QPointF(15, 11), QPointF(27, 11), QPointF(27, 25), QPointF(5, 25)]))

        elif name == "search":
            p.drawEllipse(7, 7, 13, 13)
            p.drawLine(17, 17, 26, 26)

        elif name == "download":
            p.drawLine(16, 6, 16, 20)
            p.drawPolyline(QPolygonF([QPointF(10, 14), QPointF(16, 20), QPointF(22, 14)]))
            p.drawLine(7, 25, 25, 25)

        elif name == "check":
            p.drawPolyline(QPolygonF([QPointF(7, 16), QPointF(13, 22), QPointF(25, 9)]))

        elif name == "warning":
            p.drawPolygon(QPolygonF([QPointF(16, 5), QPointF(27, 25), QPointF(5, 25)]))
            p.drawLine(16, 12, 16, 18)
            p.drawPoint(16, 21)

        elif name == "close":
            p.drawLine(8, 8, 24, 24)
            p.drawLine(24, 8, 8, 24)

        elif name == "save":
            p.drawPolygon(QPolygonF([QPointF(6, 6), QPointF(22, 6), QPointF(26, 10), QPointF(26, 26), QPointF(6, 26)]))
            p.drawRect(10, 6, 10, 7)
            p.drawRect(9, 16, 14, 10)

        elif name == "terminal":
            p.drawRoundedRect(5, 6, 22, 20, 3, 3)
            p.drawPolyline(QPolygonF([QPointF(9, 12), QPointF(13, 16), QPointF(9, 20)]))
            p.drawLine(15, 20, 21, 20)

        elif name == "shield":
            p.drawPolygon(QPolygonF([QPointF(16, 4), QPointF(26, 8), QPointF(26, 18), QPointF(16, 28), QPointF(6, 18), QPointF(6, 8)]))

        elif name == "cloud":
            path = QPainterPath()
            path.moveTo(8, 22)
            path.cubicTo(4, 22, 4, 16, 9, 15)
            path.cubicTo(9, 10, 17, 8, 20, 13)
            path.cubicTo(26, 12, 28, 18, 25, 22)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "lock":
            p.drawRoundedRect(7, 13, 18, 14, 3, 3)
            p.drawArc(10, 5, 12, 14, 0, 180 * 16)
            p.drawEllipse(15, 18, 2, 2)
            p.drawLine(16, 20, 16, 23)

        elif name == "sparkles":
            p.drawLine(16, 5, 16, 27)
            p.drawLine(5, 16, 27, 16)
            p.drawLine(9, 9, 23, 23)
            p.drawLine(9, 23, 23, 9)

        elif name == "cpu":
            p.drawRoundedRect(9, 9, 14, 14, 2, 2)
            p.drawRect(12, 12, 8, 8)
            p.drawLine(5, 13, 9, 13)
            p.drawLine(5, 19, 9, 19)
            p.drawLine(23, 13, 27, 13)
            p.drawLine(23, 19, 27, 19)
            p.drawLine(13, 5, 13, 9)
            p.drawLine(19, 5, 19, 9)
            p.drawLine(13, 23, 13, 27)
            p.drawLine(19, 23, 19, 27)

        elif name == "ram":
            p.drawRoundedRect(5, 11, 22, 10, 2, 2)
            p.drawLine(9, 11, 9, 7)
            p.drawLine(13, 11, 13, 7)
            p.drawLine(17, 11, 17, 7)
            p.drawLine(21, 11, 21, 7)
            p.drawLine(9, 21, 9, 25)
            p.drawLine(13, 21, 13, 25)
            p.drawLine(17, 21, 17, 25)
            p.drawLine(21, 21, 21, 25)

        elif name == "globe":
            p.drawEllipse(6, 6, 20, 20)
            p.drawLine(6, 16, 26, 16)
            p.drawArc(9, 6, 14, 20, 0, 360 * 16)

        elif name == "play_triangle":
            p.setBrush(QBrush(c))
            p.drawPolygon(QPolygonF([QPointF(11, 8), QPointF(24, 16), QPointF(11, 24)]))

        elif name == "stop_square":
            p.setBrush(QBrush(c))
            p.drawRoundedRect(8, 8, 16, 16, 2, 2)

        elif name == "chevron_right":
            p.drawPolyline(QPolygonF([QPointF(12, 9), QPointF(19, 16), QPointF(12, 23)]))

        elif name == "chevron_left":
            p.drawPolyline(QPolygonF([QPointF(20, 9), QPointF(13, 16), QPointF(20, 23)]))

        elif name == "chevron_down":
            p.drawPolyline(QPolygonF([QPointF(9, 12), QPointF(16, 19), QPointF(23, 12)]))

        elif name == "sun":
            # Sun for Light Mode
            p.drawEllipse(10, 10, 12, 12)
            for i in range(8):
                rad = i * math.pi / 4
                x1 = 16.0 + 8.0 * math.cos(rad)
                y1 = 16.0 + 8.0 * math.sin(rad)
                x2 = 16.0 + 11.5 * math.cos(rad)
                y2 = 16.0 + 11.5 * math.sin(rad)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        elif name == "moon":
            # Crescent Moon for Dark Mode
            path = QPainterPath()
            path.moveTo(22, 6)
            path.cubicTo(12, 6, 8, 14, 8, 20)
            path.cubicTo(8, 26, 14, 28, 20, 27)
            path.cubicTo(12, 25, 12, 12, 22, 6)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "palette":
            # Color Palette
            path = QPainterPath()
            path.moveTo(16, 5)
            path.cubicTo(24, 5, 27, 10, 27, 16)
            path.cubicTo(27, 23, 22, 27, 17, 27)
            path.cubicTo(15, 27, 13, 25, 14, 23)
            path.cubicTo(14.5, 21.5, 16, 21, 16, 19)
            path.cubicTo(16, 17, 14, 16, 12, 16)
            path.cubicTo(8, 16, 5, 18, 5, 14)
            path.cubicTo(5, 8, 10, 5, 16, 5)
            path.closeSubpath()
            p.drawPath(path)
            p.drawEllipse(10, 9, 2, 2)
            p.drawEllipse(16, 8, 2, 2)
            p.drawEllipse(22, 11, 2, 2)
            p.drawEllipse(22, 17, 2, 2)

        else:
            # Fallback Dot / Node
            p.drawEllipse(12, 12, 8, 8)
