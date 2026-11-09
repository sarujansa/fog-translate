"""Pure geometry: the 16:9 picture DBD draws inside its window, and regions relative to it.

DBD renders 16:9 centred (on 3440×1440: 2560×1440 with black bars of 440 px left and right). A region is stored
relative to that viewport (0..1), so it survives another window size or monitor.
"""
from __future__ import annotations

ASPECT = 16 / 9
MIN_SIZE = 0.02          # a region narrower/lower than 2 % of the viewport is a mis-click


def viewport(width: int, height: int) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the 16:9 picture inside a window of ``width``×``height`` (client coordinates)."""
    if width <= 0 or height <= 0:
        return 0, 0, 0, 0
    if width / height > ASPECT:                       # wider: bars left and right
        w = round(height * ASPECT)
        return (width - w) // 2, 0, w, height
    h = round(width / ASPECT)                         # taller: bars top and bottom
    return 0, (height - h) // 2, width, h


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
