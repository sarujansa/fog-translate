"""Pure: decides when the chat region shows something new and settled, so Claude is asked only then.

Each look is shrunk to a small grey picture. A request is due when the picture differs from the one last sent
and has stayed the same for ``SETTLE_LOOKS`` looks (no request in the middle of a fade or while a line scrolls
in). A nearly uniform picture (chat hidden, loading screen) is never sent.
"""
from __future__ import annotations

import numpy as np

SMALL_W = 160            # width of the comparison picture
PIXEL_DIFF = 18          # grey levels a pixel must change by to count
CHANGED_SHARE = 0.004    # share of changed pixels that makes a picture "different"
SETTLE_LOOKS = 2         # equal looks in a row before a request
MIN_CONTRAST = 12.0      # standard deviation below this = empty/uniform region


def small(img: np.ndarray) -> np.ndarray:
    """BGR or grey picture → small grey float picture (pure numpy, no cv2 needed)."""
    a = np.asarray(img)
    if a.ndim == 3:
        a = a[..., :3].astype(np.float32) @ np.array([0.114, 0.587, 0.299], np.float32)
    else:
        a = a.astype(np.float32)
    h, w = a.shape
    step = max(1, w // SMALL_W)
    return a[::step, ::step]


def differs(a: np.ndarray | None, b: np.ndarray | None) -> bool:
    if a is None or b is None or a.shape != b.shape:
        return True
    return float(np.mean(np.abs(a - b) > PIXEL_DIFF)) > CHANGED_SHARE


class ChangeGate:
    def __init__(self, settle: int = SETTLE_LOOKS):
        self.settle = settle
        self._last = None        # previous look
        self._same = 0           # looks in a row equal to the previous one
        self._sent = None        # look last handed out for a request

    def reset(self):
        self._last = self._sent = None
        self._same = 0

    def look(self, img: np.ndarray) -> bool:
        """Feed one look; True when this picture should be sent now."""
        s = small(img)
        if self._last is not None and not differs(self._last, s):
            self._same += 1
        else:
            self._same = 0
        self._last = s
        if self._same + 1 < self.settle:
            return False
        if float(s.std()) < MIN_CONTRAST:
            return False
        if not differs(self._sent, s):
            return False
        self._sent = s
        return True
