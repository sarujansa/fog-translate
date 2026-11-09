"""The program's logo, drawn with QPainter (no image file to ship): two speech bubbles – a grey one with
foreign "text" and an amber one with the translation – over a wisp of fog. Amber is the colour of the language
tag in the overlay."""
from __future__ import annotations

import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

SIZES = (16, 24, 32, 48, 64, 128, 256)
AMBER = QColor(255, 196, 92)
GREY = QColor(138, 147, 163)
DARK = QColor(20, 22, 28)
APP_ID = "FogTranslate.App"


def _bubble(x, y, w, h, r, tail_x, tail_left: bool) -> QPainterPath:
    """A rounded box with a small tail at the bottom (pointing left or right)."""
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    tail = QPainterPath()
    base = y + h - 1
    if tail_left:
        tail.moveTo(tail_x, base)
        tail.lineTo(tail_x - w * 0.10, base + h * 0.30)
        tail.lineTo(tail_x + w * 0.16, base)
    else:
        tail.moveTo(tail_x, base)
        tail.lineTo(tail_x + w * 0.10, base + h * 0.30)
        tail.lineTo(tail_x - w * 0.16, base)
    tail.closeSubpath()
    return path.united(tail)


def paint(p: QPainter, s: float):
    """The logo into a square of side ``s`` at (0, 0)."""
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    # background tile with a faint fog gradient
    bg = QLinearGradient(0, 0, 0, s)
    bg.setColorAt(0.0, QColor(36, 40, 50))
    bg.setColorAt(1.0, DARK)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.22, s * 0.22)

    # back bubble: the foreign line (grey, with "scribble" lines)
    back = _bubble(s * 0.12, s * 0.14, s * 0.50, s * 0.34, s * 0.08, s * 0.24, True)
    p.setBrush(GREY)
    p.drawPath(back)
    if s >= 32:
        p.setPen(QPen(DARK, max(1.0, s * 0.035), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, frac in enumerate((0.70, 0.48)):
            y = s * (0.255 + i * 0.105)
            p.drawLine(QPointF(s * 0.20, y), QPointF(s * (0.20 + 0.34 * frac), y))
        p.setPen(Qt.PenStyle.NoPen)

    # front bubble: the translation (amber), with a dark outline to separate it from the back one
    front = _bubble(s * 0.36, s * 0.40, s * 0.52, s * 0.34, s * 0.08, s * 0.76, False)
    p.setPen(QPen(DARK, max(1.0, s * 0.03)))
    p.setBrush(AMBER)
    p.drawPath(front)
    p.setPen(Qt.PenStyle.NoPen)
    # a check-like arrow inside: "understood"
    if s >= 24:
        pen = QPen(DARK, max(1.2, s * 0.05), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                   Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        arrow = QPainterPath(QPointF(s * 0.48, s * 0.57))
        arrow.lineTo(QPointF(s * 0.74, s * 0.57))
        arrow.moveTo(QPointF(s * 0.66, s * 0.495))
        arrow.lineTo(QPointF(s * 0.745, s * 0.57))
        arrow.lineTo(QPointF(s * 0.66, s * 0.645))
        p.drawPath(arrow)
        p.setPen(Qt.PenStyle.NoPen)

    # fog: two soft, gently waving bands along the bottom
    if s >= 24:
        for y, alpha, x0, x1, width in ((0.855, 60, 0.08, 0.66, 0.055), (0.915, 38, 0.34, 0.92, 0.05)):
            p.setPen(QPen(QColor(215, 222, 235, alpha), s * width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            w = x1 - x0
            wisp = QPainterPath(QPointF(s * x0, s * y))
            wisp.cubicTo(QPointF(s * (x0 + w * 0.3), s * (y - 0.018)), QPointF(s * (x0 + w * 0.7), s * (y + 0.018)),
                         QPointF(s * x1, s * y))
            p.drawPath(wisp)
        p.setPen(Qt.PenStyle.NoPen)


def pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    paint(p, float(size))
    p.end()
    return pm


def icon() -> QIcon:
    ic = QIcon()
    for n in SIZES:
        ic.addPixmap(pixmap(n))
    return ic


def set_app_id():
    """Windows: own taskbar group and icon instead of Python's (affects only this process)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass
