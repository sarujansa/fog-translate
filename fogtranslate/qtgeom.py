"""Screen pixels ↔ Qt coordinates.

Win32 (window rectangles) and mss work in physical pixels. Qt works in "logical" pixels = physical / scale when
Windows display scaling is above 100 %. Mixing them made the captured area smaller than the marked one and shifted
it to the top left (Saru, 09.11.2026: every chat line cut off at the same place). Every place where a screen
rectangle meets a Qt window goes through these functions. ``QT_ENABLE_HIGHDPI_SCALING=0`` makes the ratio 1 where
Qt honours it; the conversion keeps working where it does not.
"""
from __future__ import annotations


def ratio() -> float:
    """Logical → physical factor of the primary screen (1.0 without scaling or without a screen)."""
    try:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        r = float(screen.devicePixelRatio()) if screen is not None else 1.0
    except Exception:
        return 1.0
    return r if r > 0 else 1.0


def to_qt(rect, r: float):
    """Physical (x, y, w, h) → Qt logical."""
    return tuple(int(round(v / r)) for v in rect)


def from_qt(rect, r: float):
    """Qt logical (x, y, w, h) → physical."""
    return tuple(int(round(v * r)) for v in rect)
