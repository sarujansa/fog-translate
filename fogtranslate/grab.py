"""Screen pixels of one box via mss (like OBS or Discord screen sharing). Create and use in one thread."""
from __future__ import annotations

import numpy as np


class Grabber:
    def __init__(self):
        import mss
        factory = getattr(mss, "MSS", None) or mss.mss
        self._sct = factory()

    def grab(self, box):
        if box is None:
            return None
        x, y, w, h = box
        shot = self._sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
        arr = np.frombuffer(shot.raw, dtype=np.uint8).reshape(shot.height, shot.width, 4)
        return np.ascontiguousarray(arr[..., :3])          # BGRA → BGR

    def close(self):
        try:
            self._sct.close()
        except Exception:
            pass


def blank(img, box, rects):
    """Black out every part of ``rects`` (screen coordinates) inside the picture of ``box`` – our own windows,
    so the program never reads (and never sends) its own translations."""
    if img is None or not rects:
        return img
    bx, by, bw, bh = box
    for rx, ry, rw, rh in rects:
        x0, y0 = max(rx, bx) - bx, max(ry, by) - by
        x1, y1 = min(rx + rw, bx + bw) - bx, min(ry + rh, by + bh) - by
        if x1 > x0 and y1 > y0:
            img[y0:y1, x0:x1] = 0
    return img
