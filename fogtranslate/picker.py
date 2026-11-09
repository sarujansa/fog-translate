"""Marking the chat region: a dimmed full-size window over the DBD picture, drag a box, Enter/release = done,
Esc = cancel. Only the own window takes the mouse – nothing is sent to the game."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import geometry


class RegionPicker(QWidget):
    def __init__(self, client, done, current=None):
        """``client`` = (x, y, w, h) of the game picture on screen; ``done(rel_or_None)``."""
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.client = tuple(client)
        self.view = geometry.viewport(self.client[2], self.client[3])
        self._done = done
        self._start: QPoint | None = None
        self._box: QRect | None = None
        if current is not None:
            self._box = QRect(*geometry.from_relative(current, self.view))
        self.setGeometry(*self.client)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def start(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _finish(self, rel):
        self.close()
        self._done(rel)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = e.position().toPoint()
            self._box = QRect(self._start, self._start)
            self.update()
        elif e.button() == Qt.MouseButton.RightButton:
            self._finish(None)

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self._box = QRect(self._start, e.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._box is not None:
            b = self._box.normalized()
            self._start = None
            rel = geometry.to_relative((b.x(), b.y(), b.width(), b.height()), self.view)
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
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        if self._box is not None:
            b = self._box.normalized()
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(b, Qt.GlobalColor.transparent)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            p.setPen(QPen(QColor(255, 196, 92), 2))
            p.drawRect(b)
        f = QFont()
        f.setPixelSize(22)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.drawText(self.rect().adjusted(0, 40, 0, 0), int(Qt.AlignmentFlag.AlignHCenter),
                   "Chat-Bereich mit der Maus aufziehen  ·  Esc / Rechtsklick = abbrechen")
        p.end()
