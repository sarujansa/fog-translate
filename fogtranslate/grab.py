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
