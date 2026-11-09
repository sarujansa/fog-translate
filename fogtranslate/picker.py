"""Marking the chat region: a dimmed full-size window over the DBD picture, drag a box, release = done,
Esc / right click = cancel. Only the own window takes the mouse – nothing is sent to the game.

Every pixel of this window stays at least slightly opaque: on Windows a fully transparent pixel of a translucent
window lets the click through to the window below (the game) – the old box was such a hole, so pressing inside
it never reached the picker and the region could not be marked anew (Saru, 09.11.2026)."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import geometry, qtgeom


def _span(a: QPoint, b: QPoint) -> QRect:
    """The box between two points; width = |dx| (QRect(a, b) would count both end points, one pixel more)."""
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()), abs(a.x() - b.x()), abs(a.y() - b.y()))


class RegionPicker(QWidget):
    def __init__(self, client, done, current=None, scale: float | None = None):
        """``client`` = (x, y, w, h) of the game picture on screen in physical pixels; ``done(rel_or_None)``.
        The window itself works in Qt coordinates (physical / ``scale``)."""
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.client = tuple(client)
        self.scale = scale or qtgeom.ratio()
        self.view = geometry.viewport(self.client[2], self.client[3])
        self._done = done
        self._start: QPoint | None = None
        self._box: QRect | None = None
        if current is not None:
            self._box = QRect(*qtgeom.to_qt(geometry.from_relative(current, self.view), self.scale))
        self.setGeometry(*qtgeom.to_qt(self.client, self.scale))
        self.setCursor(Qt.CursorShape.CrossCursor)

    DIM = QColor(0, 0, 0, 120)
    INSIDE = QColor(255, 196, 92, 28)          # never alpha 0 (see module docstring)

    def start(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()
        self.grabMouse()
        self.grabKeyboard()

    def closeEvent(self, event):
        self.releaseMouse()
        self.releaseKeyboard()
        super().closeEvent(event)

    def _finish(self, rel):
        self.close()
        self._done(rel)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.position().toPoint()
            self._box = _span(self._start, self._start)
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self._finish(None)

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._box = _span(self._start, e.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._box is not None:
            if self._start is not None:
                self._box = _span(self._start, e.position().toPoint())
            b = self._box.normalized()
            self._start = None
            physical = qtgeom.from_qt((b.x(), b.y(), b.width(), b.height()), self.scale)
            rel = geometry.to_relative(physical, self.view)
            if rel is not None:
                self._finish(rel)
            else:
                self._box = None
                self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), self.DIM)
        if self._box is not None:
            b = self._box.normalized()
            p.fillRect(b, self.INSIDE)                 # lighter, but still catches the mouse
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.setPen(QPen(QColor(255, 196, 92), 2))
            p.drawRect(b)
            if self._start is None:
                f = QFont()
                f.setPixelSize(15)
                p.setFont(f)
                p.drawText(b.adjusted(0, -22, 0, 0).topLeft() + QPoint(2, 0), "current area – drag a new one")
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        f = QFont()
        f.setPixelSize(22)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.drawText(self.rect().adjusted(0, 40, 0, 0), int(Qt.AlignmentFlag.AlignHCenter),
                   "Drag a box around the chat  ·  Esc / right click = cancel")
        p.end()
