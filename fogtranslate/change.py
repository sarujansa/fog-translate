"""Pure: decides when the chat region shows new text, so the service is asked only then.

Only *text* is compared, not the whole picture: a pixel counts as text when it is clearly brighter than its
neighbourhood (sharp bright strokes) **and** sits on the chat's near-black panel (something dark right next to it). The lobby behind the chat moves all the time (fire, characters, smoke) –
comparing raw pixels, the picture never "settled" and nothing was ever sent once the marked box reached past the
chat panel (Saru, 09.11.2026). Soft glow and figures behind the darkened panel have no sharp edges and drop out.

A request is due when the text differs from the text last sent and
* has stayed the same for ``SETTLE_LOOKS`` looks (no request while a line scrolls in), or
* has kept changing for ``MAX_WAIT_LOOKS`` looks anyway (something in the box never stops moving).
A box with almost no text (chat hidden, loading screen) is never sent.
"""
from __future__ import annotations

import numpy as np

EDGE = 40.0              # grey levels a text pixel is brighter than the mean around it
MIN_BRIGHT = 110.0       # text in the DBD chat is light (white, yellow, green, orange)
WINDOW = 7               # side of the neighbourhood for that mean
DARK = 55.0              # the chat panel: a text pixel has something this dark within its neighbourhood
LONG = 30                # a straight run this long is an edge (panel border, scroll bar), not a letter
CHANGED_SHARE = 0.0005   # share of the box whose text must differ to count as "different"
MIN_CHANGED_PX = 60      # … and at least this many pixels (flicker: < 45; a short line like "gg": ~150)
MIN_TEXT_PX = 60         # fewer text pixels = nothing to read
SETTLE_LOOKS = 2         # equal looks in a row before a request
MAX_WAIT_LOOKS = 4       # changed text is sent after this many looks even if the box never settles


def grey(img: np.ndarray) -> np.ndarray:
    a = np.asarray(img)
    if a.ndim == 3:
        return a[..., :3].astype(np.float32) @ np.array([0.114, 0.587, 0.299], np.float32)
    return a.astype(np.float32)


def _box_mean(g: np.ndarray, k: int) -> np.ndarray:
    """Mean over a k×k neighbourhood (integral image, edges padded)."""
    p = k // 2
    padded = np.pad(g, p, mode="edge")
    s = np.pad(padded.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    h, w = g.shape
    total = s[k:k + h, k:k + w] - s[:h, k:k + w] - s[k:k + h, :w] + s[:h, :w]
    return total / (k * k)


def _box_min(g: np.ndarray, k: int) -> np.ndarray:
    """Minimum over a k×k neighbourhood (separable: rows, then columns)."""
    p = k // 2
    padded = np.pad(g, p, mode="edge")
    rows = np.lib.stride_tricks.sliding_window_view(padded, k, axis=1).min(axis=-1)
    return np.lib.stride_tricks.sliding_window_view(rows, k, axis=0).min(axis=-1)


def _long_runs(m: np.ndarray, n: int, axis: int) -> np.ndarray:
    """Pixels that belong to a straight run of at least ``n`` set pixels along ``axis``."""
    length = m.shape[axis]
    if length < n:
        return np.zeros_like(m)
    full = np.lib.stride_tricks.sliding_window_view(m, n, axis=axis).all(axis=-1)    # window starts
    out = np.zeros_like(m)
    for k in range(n):                                    # spread each full window over its n pixels
        if axis == 1:
            out[:, k:k + full.shape[1]] |= full
        else:
            out[k:k + full.shape[0], :] |= full
    return out


def text_mask(img: np.ndarray) -> np.ndarray:
    g = grey(img)
    m = (g > MIN_BRIGHT) & (g - _box_mean(g, WINDOW) > EDGE) & (_box_min(g, WINDOW) < DARK)
    return m & ~_long_runs(m, LONG, 1) & ~_long_runs(m, LONG, 0)


def _grow(m: np.ndarray) -> np.ndarray:
    """The mask grown by one pixel – a stroke read one pixel off is not a change."""
    out = m.copy()
    out[1:] |= m[:-1]
    out[:-1] |= m[1:]
    out[:, 1:] |= m[:, :-1]
    out[:, :-1] |= m[:, 1:]
    return out


def changed_px(a: np.ndarray | None, b: np.ndarray | None) -> int:
    """Text pixels in one mask with no text pixel near them in the other."""
    if a is None or b is None or a.shape != b.shape:
        return 10 ** 9
    return int(np.count_nonzero(a & ~_grow(b)) + np.count_nonzero(b & ~_grow(a)))


def differs(a, b) -> bool:
    if a is None or b is None or a.shape != b.shape:
        return True
    n = changed_px(a, b)
    return n >= MIN_CHANGED_PX and n > CHANGED_SHARE * a.size


class ChangeGate:
    def __init__(self, settle: int = SETTLE_LOOKS, max_wait: int = MAX_WAIT_LOOKS):
        self.settle = settle
        self.max_wait = max_wait
        self._last = None        # text of the previous look
        self._same = 0           # looks in a row with the same text
        self._sent = None        # text last handed out for a request
        self.crop_top = 0        # with the last True: first row worth sending (only the new lines)
        self._waiting = 0        # looks in a row whose text differed from the text sent
        self.stats = {}          # for the log: text px, change to last look / to sent

    def reset(self):
        self._last = self._sent = None
        self._same = self._waiting = 0

    def look(self, img: np.ndarray) -> bool:
        """Feed one look; True when this picture should be sent now."""
        m = text_mask(img)
        to_last = changed_px(self._last, m) if self._last is not None else -1
        if self._last is not None and not differs(self._last, m):
            self._same += 1
        else:
            self._same = 0
        self._last = m
        text = int(np.count_nonzero(m))
        new = differs(self._sent, m)
        self._waiting = self._waiting + 1 if new and text >= MIN_TEXT_PX else 0
        self.stats = {"text_px": text, "to_last": to_last, "settled": self._same + 1 >= self.settle,
                      "waiting": self._waiting}
        if text < MIN_TEXT_PX or not new:
            return False
        if self._same + 1 < self.settle and self._waiting < self.max_wait:
            return False
        self.crop_top = new_rows(self._sent, m)
        self._sent = m
        self._waiting = 0
        return True


# ---------------------------------------------------------------- only the new lines
MIN_KEPT = 0.3           # the earlier text must still be there for at least this share to trust an alignment
MAX_LOST = 0.06          # … and at most this share of it may be unexplained
MARGIN = 0.06            # rows above the first new text that are sent along (part of a line for context)


def new_rows(before: np.ndarray | None, now: np.ndarray) -> int:
    """First row of ``now`` (a text mask) that shows text ``before`` did not have – after finding how far the
    chat scrolled up (DBD pushes old lines up when a new one comes). 0 = send the whole area (first look, no
    trustworthy alignment, or everything is new)."""
    if before is None or before.shape != now.shape:
        return 0
    h = now.shape[0]
    total = int(np.count_nonzero(before))
    if total < MIN_TEXT_PX:
        return 0
    grown_now = _grow(now)
    best, best_share = None, 1.0
    for s in range(0, h):
        kept = before[s:]
        n = int(np.count_nonzero(kept))
        if n < MIN_KEPT * total:
            break
        share = np.count_nonzero(kept & ~grown_now[:h - s]) / n
        if share < best_share:
            best, best_share = s, share          # the scroll that explains the earlier text best
    if best is None or best_share > MAX_LOST:
        return 0
    moved = np.zeros_like(before)
    moved[:h - best] = before[best:]
    fresh = now & ~_grow(moved)
    rows = np.nonzero(fresh.sum(axis=1) >= 2)[0]
    if len(rows) == 0:
        return 0
    start = int(rows[0]) - int(MARGIN * h)
    return max(0, start)
