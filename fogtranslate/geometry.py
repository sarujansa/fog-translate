"""Pure geometry: regions relative to the game window.

A region is stored relative to the whole client area of the game window (0..1). Not relative to the 16:9
picture: in a match DBD renders 16:9 centred (on 3440×1440: 2560×1440 with black bars), but lobby, menus and the
result screen use the full width on ultrawide – the chat sits right of the 16:9 picture there, and clipping to
16:9 cut it off (Saru, 09.11.2026: the box always ended at x = 3000 of 3440).
"""
from __future__ import annotations

MIN_SIZE = 0.02          # a region narrower/lower than 2 % of the game window is a mis-click


def window_space(width: int, height: int) -> tuple[int, int, int, int]:
    """The space regions are relative to: the whole client area."""
    return 0, 0, max(0, int(width)), max(0, int(height))


def to_relative(box, view) -> tuple[float, float, float, float] | None:
    """A box (x, y, w, h) in window coordinates → relative to the viewport, clipped to it; None if too small."""
    vx, vy, vw, vh = view
    if vw <= 0 or vh <= 0:
        return None
    x0 = max(box[0], vx)
    y0 = max(box[1], vy)
    x1 = min(box[0] + box[2], vx + vw)
    y1 = min(box[1] + box[3], vy + vh)
    rel = ((x0 - vx) / vw, (y0 - vy) / vh, (x1 - x0) / vw, (y1 - y0) / vh)
    if rel[2] < MIN_SIZE or rel[3] < MIN_SIZE:
        return None
    return tuple(round(v, 5) for v in rel)


def from_relative(rel, view) -> tuple[int, int, int, int]:
    """A relative region → (x, y, w, h) in window coordinates."""
    vx, vy, vw, vh = view
    x = vx + round(rel[0] * vw)
    y = vy + round(rel[1] * vh)
    return x, y, max(1, round(rel[2] * vw)), max(1, round(rel[3] * vh))


def valid_region(rel) -> bool:
    try:
        x, y, w, h = (float(v) for v in rel)
    except (TypeError, ValueError):
        return False
    return 0 <= x < 1 and 0 <= y < 1 and MIN_SIZE <= w and MIN_SIZE <= h and x + w <= 1.0001 and y + h <= 1.0001


def placed_spot(box, size, screen) -> tuple[int, int]:
    """Where the translation window goes when the user chose a place: the top left corner of ``box``, moved only
    as far as needed to stay inside ``screen``. All in screen coordinates."""
    w, h = size
    sx, sy, sw, sh = screen
    x = min(max(box[0], sx), sx + sw - w)
    y = min(max(box[1], sy), sy + sh - h)
    return int(x), int(y)


def touches(a, b) -> bool:
    """Whether two boxes (x, y, w, h) share any area."""
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def overlay_spot(region, size, screen) -> tuple[int, int]:
    """Where the translation window goes: right above the region (left-aligned); below it if there is no room
    above; always inside ``screen`` (x, y, w, h). ``region`` and the result are screen coordinates."""
    rx, ry, rw, rh = region
    w, h = size
    sx, sy, sw, sh = screen
    gap = 6
    y = ry - h - gap
    if y < sy:
        y = ry + rh + gap
    x = min(max(rx, sx), sx + sw - w)
    y = min(max(y, sy), sy + sh - h)
    return int(x), int(y)
