"""Marking the chat region on a still picture of the game.

The program takes one screenshot of the DBD window and shows it in an ordinary window; the user drags a box on
it and clicks Save. Nothing lies over the game, nothing competes with the game for the mouse, and the picture's
pixels are the screen's pixels, so no Qt/Windows scaling conversion is involved.

(Until 0.6.1 a translucent window over the game was used. On Saru's PC the box could not be set anew there –
the clicks did not reach that window over DBD, 09.11.2026.)
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import geometry
from .i18n import tr

AMBER = QColor(255, 196, 92)


def _span(a: QPoint, b: QPoint) -> QRect:
    """The box between two points; width = |dx| (QRect(a, b) would count both end points, one pixel more)."""
    return QRect(min(a.x(), b.x()), min(a.y(), b.y()), abs(a.x() - b.x()), abs(a.y() - b.y()))


class Canvas(QWidget):
    """The still picture, scaled to fit; boxes are kept in picture pixels."""

    def __init__(self, picture: np.ndarray, box=None, changed=None):
        super().__init__()
        rgb = np.ascontiguousarray(np.asarray(picture)[..., 2::-1])          # BGR → RGB
        h, w = rgb.shape[:2]
        self.image = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self.pic_w, self.pic_h = w, h
        self.box = QRect(*box) if box else None       # picture pixels
        self._start = None
        self._changed = changed or (lambda: None)
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMinimumSize(320, 180)

    # picture ↔ widget
    def _fit(self) -> QRectF:
        s = min(self.width() / self.pic_w, self.height() / self.pic_h)
        w, h = self.pic_w * s, self.pic_h * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def to_picture(self, pos) -> QPoint:
        f = self._fit()
        x = (pos.x() - f.x()) * self.pic_w / f.width()
        y = (pos.y() - f.y()) * self.pic_h / f.height()
        return QPoint(int(round(min(max(x, 0), self.pic_w))), int(round(min(max(y, 0), self.pic_h))))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = self.to_picture(e.position())
            self.box = _span(self._start, self._start)
            self.update()

    def mouseMoveEvent(self, e):
        if self._start is not None:
            self.box = _span(self._start, self.to_picture(e.position()))
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._start is not None:
            self.box = _span(self._start, self.to_picture(e.position()))
            self._start = None
            self.update()
            self._changed()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(16, 16, 20))
        f = self._fit()
        p.drawImage(f, self.image)
        if self.box is not None and self.box.width() > 0:
            sx, sy = f.width() / self.pic_w, f.height() / self.pic_h
            r = QRectF(f.x() + self.box.x() * sx, f.y() + self.box.y() * sy, self.box.width() * sx,
                       self.box.height() * sy)
            p.fillRect(r, QColor(255, 196, 92, 40))
            p.setPen(QPen(AMBER, 2))
            p.drawRect(r)
        p.end()


class RegionPicker(QWidget):
    """``picture`` = BGR screenshot of the game's client area (its pixels are screen pixels);
    ``done(rel_or_None)`` – the box relative to the whole game window, or None when cancelled."""

    def __init__(self, picture, done, current=None):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle(tr("Mark chat area"))
        h, w = np.asarray(picture).shape[:2]
        self.view = geometry.window_space(w, h)
        self._done = done
        self._finished = False
        box = geometry.from_relative(current, self.view) if current else None
        self.canvas = Canvas(picture, box, self._update_buttons)
        hint = QLabel(tr("Drag a box around the whole chat – a little wider than the longest line, including the "
                         "scroll bar. Then click Save."))
        hint.setWordWrap(True)
        self.save_btn = QPushButton(tr("Save"), clicked=self.save)
        self.save_btn.setDefault(True)
        cancel = QPushButton(tr("Cancel"), clicked=self.cancel)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_btn)
        root = QVBoxLayout(self)
        root.addWidget(hint)
        root.addWidget(self.canvas, 1)
        root.addLayout(buttons)
        self._update_buttons()

    def relative(self):
        b = self.canvas.box
        if b is None:
            return None
        return geometry.to_relative((b.x(), b.y(), b.width(), b.height()), self.view)

    def _update_buttons(self):
        self.save_btn.setEnabled(self.relative() is not None)

    def start(self, screen_size=None):
        """Show it large: ~80 % of the screen, keeping the picture's shape."""
        sw, sh = screen_size or (1600, 900)
        s = min(0.8 * sw / self.canvas.pic_w, 0.8 * sh / self.canvas.pic_h, 1.0)
        self.resize(int(self.canvas.pic_w * s) + 24, int(self.canvas.pic_h * s) + 90)
        self.show()
        self.raise_()
        self.activateWindow()

    def save(self):
        rel = self.relative()
        if rel is not None:
            self._end(rel)

    def cancel(self):
        self._end(None)

    def _end(self, rel):
        if self._finished:
            return
        self._finished = True
        self.close()
        self._done(rel)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancel()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.save()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, event):
        if not self._finished:                      # closed with the window's ×
            self._finished = True
            self._done(None)
        super().closeEvent(event)
