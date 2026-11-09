"""The translation window: frameless, always on top, click-through, never takes focus.

It shows up in screenshots and recordings (Saru's wish). The program never reads it back: the look thread blacks
out its rectangle (``grab.blank``). Optionally (``hide_in_captures``) it is excluded from capture on Windows
(``WDA_EXCLUDEFROMCAPTURE``, own window only).
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from . import qtgeom
from .lines import ChatLine

PAD = 10
ROW_GAP = 2
MSG_GAP = 8
MAX_W = 720
BG = QColor(12, 12, 16, 215)
SENDER = QColor(150, 160, 175)
TEXT = QColor(245, 245, 245)
LANG = QColor(255, 196, 92)
ORIGINAL = QColor(150, 150, 150)


def exclude_from_capture(widget, on: bool) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.SetWindowDisplayAffinity.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    user32.SetWindowDisplayAffinity.restype = ctypes.c_int
    # 0x11 = WDA_EXCLUDEFROMCAPTURE, 0 = WDA_NONE
    return bool(user32.SetWindowDisplayAffinity(ctypes.c_void_p(int(widget.winId())), 0x11 if on else 0))


class TranslationOverlay(QWidget):
    def __init__(self, font_px: int = 18, show_original: bool = True):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.show_original = show_original
        self.lines: list[ChatLine] = []
        self.set_font_px(font_px)
        self.hide_in_captures = False
        self._affinity = None
        self.rect_on_screen = None           # (x, y, w, h) while shown – read by the look thread

    def set_font_px(self, px: int):
        self.font_main = QFont("Segoe UI" if sys.platform == "win32" else "Sans")
        self.font_main.setPixelSize(max(10, int(px)))
        self.font_small = QFont(self.font_main)
        self.font_small.setPixelSize(max(9, int(px * 0.75)))

    def rows(self, line: ChatLine):
        """[(parts, font)] – parts = [(text, colour)]: header (tag + name), translation, original (small)."""
        tag = [(line.language.upper() + "  ", LANG)] if line.translate else []
        out = [(tag + [(line.sender or "System", SENDER)], self.font_small)]
        out.append(([(line.translation if line.translate else line.text, TEXT)], self.font_main))
        if self.show_original and line.translate and line.translation != line.text:
            out.append(([(line.text, ORIGINAL)], self.font_small))
        return out

    def _height(self, text: str, font, width: int) -> int:
        fm = QFontMetrics(font)
        return fm.boundingRect(QRect(0, 0, width, 100000), int(Qt.TextFlag.TextWordWrap), text).height()

    def layout_size(self, lines) -> tuple[int, int]:
        inner = MAX_W - 2 * PAD
        w = 0
        h = PAD
        for n, line in enumerate(lines):
            for parts, font in self.rows(line):
                text = "".join(t for t, _ in parts)
                fm = QFontMetrics(font)
                w = max(w, min(inner, fm.horizontalAdvance(text) + 2))
                h += self._height(text, font, inner) + ROW_GAP
            h += MSG_GAP if n < len(lines) - 1 else 0
        return w + 2 * PAD, h + PAD - ROW_GAP

    def show_lines(self, lines, spot_for_size):
        """``spot_for_size((w, h)) → (x, y)`` in physical screen pixels; hidden when there is nothing to show."""
        self.lines = list(lines)
        if not self.lines:
            self.rect_on_screen = None
            self.hide()
            return
        r = qtgeom.ratio()
        w, h = self.layout_size(self.lines)                     # Qt pixels
        pw, ph = qtgeom.from_qt((w, h), r)
        x, y = spot_for_size((pw, ph))
        qx, qy = qtgeom.to_qt((x, y), r)
        self.setGeometry(qx, qy, w, h)
        self.rect_on_screen = (x, y, pw, ph)                    # physical, for blacking it out
        if not self.isVisible():
            self.show()
        if self._affinity is not self.hide_in_captures:
            exclude_from_capture(self, self.hide_in_captures)
            self._affinity = self.hide_in_captures
        self.update()

    def hideEvent(self, event):
        self.rect_on_screen = None
        super().hideEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BG)
        p.drawRoundedRect(self.rect(), 8, 8)
        width = self.width() - 2 * PAD
        y = PAD
        for n, line in enumerate(self.lines):
            for parts, font in self.rows(line):
                p.setFont(font)
                text = "".join(t for t, _ in parts)
                height = self._height(text, font, width)
                if len(parts) == 1:
                    p.setPen(parts[0][1])
                    p.drawText(QRect(PAD, y, width, height), int(Qt.TextFlag.TextWordWrap), text)
                else:                                # header: one short line in several colours
                    fm = QFontMetrics(font)
                    x = PAD
                    for part, colour in parts:
                        p.setPen(colour)
                        p.drawText(x, y + fm.ascent(), fm.elidedText(part, Qt.TextElideMode.ElideRight,
                                                                      PAD + width - x))
                        x += fm.horizontalAdvance(part)
                y += height + ROW_GAP
            y += MSG_GAP
        p.end()
