"""The loop without Qt: look at the region, ask Claude when something new has settled, keep what to show.

Rules: look only while DBD is the active window (then the region shows the game, not another program); at most
one request at a time, at least ``min_gap_s`` apart, at most ``daily_cap`` a day.
"""
from __future__ import annotations

import functools
import threading
import time
from datetime import datetime

from . import geometry
from .change import MIN_TEXT_PX, ChangeGate, differs, scroll_shift
from .lines import ChatLine, Transcript
from .translate import Result, TranslateError

KEEP_SHOWN = 6
KEEP_AT = 0.35                   # scrolled this share of the area since the last kept picture → keep another one
BACKLOG_MAX = 4                  # kept pictures waiting for the next request (older ones are dropped)
SEAM = 6                         # dark rows between stacked pictures
ERROR_WAIT_S = 10.0              # after any other failed request
QUOTA_WAIT_S = 60.0              # after a "limit reached" answer, wait at least this long
SERVICE_GAP_S = {"gemini": 6.5}  # Gemini's free tier allows about 10 requests a minute
EMPTY_WAIT_S = 15.0              # after an answer without any message: wait, doubled each time in a row …
EMPTY_MAX_S = 300.0              # … up to this (the area shows something that is not chat)
GONE_LOOKS = 2                   # looks in a row without chat text before the chat counts as gone
BILLED_ERRORS = ("answer", "refused")   # the service answered (and charged), but nothing usable came back


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return fn(self, *args, **kwargs)
    return wrapper


class Engine:
    """Used from two threads: the look thread (``look``) and the window (``answer``, ``visible``) – one lock."""

    def __init__(self, settings, worker, clock=time.monotonic, now=datetime.now):
        self.lock = threading.RLock()
        self.settings = settings
        self.worker = worker
        self.clock = clock
        self.now = now
        self.gate = ChangeGate()
        self.transcript = Transcript()
        self.shown: dict[str, float] = {}      # key of a message on screen → when it (last) changed
        self.status = "idle"         # idle | no_region | no_game | background | covered | watching | asking | cap | error
        self.error = ""
        self._last_request = -1e9
        self._not_before = -1e9      # after a limit answer
        self._pending = None
        self._backlog: list = []     # earlier pictures whose lines may have scrolled out of the current one
        self._ref = None             # text of the newest picture that is kept or sent
        self._open = 0               # requests sent, answer not yet counted (counted in the window's thread)
        self.last_counts = {}       # numbers of the last answer, for the log (never text)
        self.last_seconds = 0.0     # how long the last answer took
        self.last_sent = None        # the last picture sent (in memory only) – "Letzten Ausschnitt zeigen"
        self.chat_seen = False       # the marked area shows chat text right now (the overlay follows this)
        self._gone = 0               # looks in a row without chat text
        self._empty = 0              # answers in a row that read no message at all

    @_locked
    def region_on_screen(self, game) -> tuple[int, int, int, int] | None:
        rel = self.settings["region"]
        if game is None or rel is None:
            return None
        cx, cy, cw, ch = game.client
        x, y, w, h = geometry.from_relative(rel, geometry.window_space(cw, ch))
        return cx + x, cy + y, w, h

    @_locked
    def look(self, game, in_front: bool, grab, region_free=None) -> None:
        """One tick. ``grab(box)`` returns the BGR picture of a screen box. With DBD behind another window the
        region is read only when ``read_background`` is on and ``region_free(game, box)`` says nothing lies over
        it – otherwise the picture could be another program's window, and that must never be sent."""
        if self.settings["region"] is None:
            self.status = "no_region"
            self._chat_gone()
            return
        if game is None or game.minimized:
            self.status = "no_game"
            self.gate.reset()
            self._ref = None
            self._chat_gone()
            return
        box = self.region_on_screen(game)
        if not in_front:
            if not self.settings["read_background"]:
                self.status = "background"
                self._chat_gone()
                return
            if region_free is None or not region_free(game, box):
                self.status = "covered"
                self._chat_gone()
                return
        img = grab(box)
        if img is None:
            return
        if self._pending is not None and self._pending.shape[1:] != img.shape[1:]:
            self._forget()                   # the area changed size (marked again, window resized)
        if self.status in ("idle", "no_game", "background", "covered", "no_region"):
            self.status = "watching"
        fired = self.gate.look(img)
        mask = self.gate.last_mask
        if self.gate.stats.get("chat"):
            self.chat_seen, self._gone = True, 0
        else:                                # one look without text can be a line scrolling or the chat fading in
            self._gone += 1
            if self._gone >= GONE_LOOKS:
                self.chat_seen = False
        # A fast chat: before lines scroll out of the area, keep a picture of them for the next request
        # (simulated 10.11.2026: 6 messages/s with a 4 s answer lost 27 of 60 without this). ``_ref`` is the text
        # of the oldest picture not yet safe; "far" = the chat moved KEEP_AT of the area since then.
        far = self._moved_far(mask, img.shape[0])
        if not self.gate.stats.get("chat"):
            # no written lines in the area (chat closed, the game behind it): nothing is kept or sent – what
            # already waits may still go out
            self._try_send()
            return
        if self._pending is not None:
            if far:
                self._keep(img, mask)        # the unsent picture goes to the backlog, this one is the new one
            elif fired:
                self._pending = img          # still shows the unsent lines (moved less than KEEP_AT)
            self._try_send()
            return
        if fired:
            top = self.gate.crop_top
            self._pending = img[top:] if 0 < top < img.shape[0] - 8 else img     # only the new lines
            self._ref = mask
        elif far:
            self._keep(img, mask)            # a request is under way or the text never settles
        self._try_send()

    def _chat_gone(self):
        """The area is not looked at (no game, covered, in the background): nothing of the chat is seen."""
        self.chat_seen, self._gone = False, 0

    @_locked
    def chat_shown(self) -> bool:
        """Whether translations may be on screen: always without ``hide_without_chat``, else only while the marked
        area shows the chat (in a match, in menus without chat or with a window over it there is nothing to
        translate, and the overlay would cover something else)."""
        return self.chat_seen or not self.settings["hide_without_chat"]

    def _moved_far(self, mask, height: int) -> bool:
        ref = self._ref
        if ref is None or mask is None or int(ref.sum()) < MIN_TEXT_PX or int(mask.sum()) < MIN_TEXT_PX:
            return False
        if not differs(ref, mask):
            return False
        shift = scroll_shift(ref, mask)
        return shift is None or shift >= KEEP_AT * height

    def _forget(self):
        """Drop what waits to be sent and what counts as sent: pictures of another size cannot be stacked."""
        self.gate.reset()
        self._pending = None
        self._backlog = []
        self._ref = None

    @_locked
    def new_area(self):
        """The chat area was marked again: start over with it."""
        self._forget()
        self.transcript.clear()
        self.shown.clear()

    @_locked
    def cap_raised(self):
        """The daily limit was raised above today's count: go on and read the chat again."""
        if self.status == "cap":
            self.status = "watching"
            self.gate.reset()

    @_locked
    def starting(self, worker):
        self.worker = worker
        self.status, self.error = "starting", ""

    @_locked
    def started(self):
        if self.status == "starting":
            self.status = "idle"

    @_locked
    def failed(self, error):
        self.status, self.error = "error", error.kind

    def _keep(self, img, mask):
        """The unsent picture moves to the backlog, the current one becomes the pending one."""
        if self._pending is not None:
            self._backlog.append(self._pending)
            del self._backlog[:-BACKLOG_MAX]
        self._pending = img
        self._ref = mask
        self.gate.mark_sent(mask)

    def _stacked(self):
        """Backlog (oldest first) and the pending picture as one picture, top to bottom."""
        if not self._backlog:
            return self._pending
        import numpy as np
        parts = []
        for part in self._backlog + [self._pending]:
            if parts:
                parts.append(np.zeros((SEAM, part.shape[1], 3), part.dtype))
            parts.append(part)
        return np.vstack(parts)

    def _try_send(self):
        if self._pending is None:
            return
        t = self.clock()
        gap = max(float(self.settings["min_gap_s"]), SERVICE_GAP_S.get(self.settings["service"], 0.0))
        if self.worker.busy or t - self._last_request < gap or t < self._not_before:
            return
        day = self.now().strftime("%Y-%m-%d")
        if self.settings.requests_today(day) + self._open >= int(self.settings["daily_cap"]):
            self.status = "cap"
            self._pending = None
            self._backlog = []
            return
        picture = self._stacked()
        if self.worker.submit(picture):
            self._open += 1
            self.last_sent = picture
            self._last_request = t
            self._pending = None
            self._backlog = []
            self.status = "asking"

    @_locked
    def answer(self, outcome) -> bool:
        """A finished request (in the Qt thread). True when the transcript changed."""
        n = self.now()
        self._open = max(0, self._open - 1)
        if isinstance(outcome, TranslateError):
            if outcome.kind in BILLED_ERRORS:
                self.settings.count_request(n.strftime("%Y-%m-%d"), n.strftime("%Y-%m"), 0.0)
            self.status = "error"
            self.error = outcome.kind
            self.last_counts = {}
            # the picture of that request never arrived: forget what counts as sent, so the whole chat goes out
            # again – after a pause, so a lasting error (no key, no network) is not hammered every 2 s
            self._forget()
            wait = QUOTA_WAIT_S if outcome.kind == "quota" else ERROR_WAIT_S
            self._not_before = self.clock() + wait
            return False
        assert isinstance(outcome, Result)
        self.settings.count_request(n.strftime("%Y-%m-%d"), n.strftime("%Y-%m"), outcome.cost_usd)
        self.status = "watching"
        self.error = ""
        if outcome.lines:
            self._empty = 0
        else:
            # the service found no message in what was sent: whatever the area shows, asking again at once only
            # costs – wait longer each time until an answer reads something
            self._empty += 1
            self._not_before = self.clock() + min(EMPTY_WAIT_S * 2 ** (self._empty - 1), EMPTY_MAX_S)
        added, replaced = self.transcript.add(outcome.lines)
        self.last_counts = {"read": len(outcome.lines), "foreign": sum(1 for ln in outcome.lines if ln.translate),
                            "new": len(added), "replaced": len(replaced),
                            "seconds": round(float(getattr(outcome, "seconds", 0.0)), 2)}
        self.last_seconds = float(getattr(outcome, "seconds", 0.0))
        t = self.clock()
        for old_key, line in replaced.items():
            self.shown.pop(old_key, None)
            self.shown[line.key()] = t
        for line in added:
            self.shown[line.key()] = t
        return bool(added or replaced)

    def wanted(self, line: ChatLine) -> bool:
        return line.translate or bool(self.settings["show_all"])

    @_locked
    def messages(self) -> list[ChatLine]:
        """The transcript as the window lists it."""
        return [ln for ln in self.transcript.entries if self.wanted(ln)]

    @_locked
    def visible(self) -> list[ChatLine]:
        """Messages for the overlay: the latest ``KEEP_SHOWN`` translations, as long as something new came within
        ``show_s`` – a running view of the chat, not just the last change (Saru, 09.11.2026: the Chinese lines
        had faded already when the next English line arrived, so they looked untranslated)."""
        limit = self.clock() - float(self.settings["show_s"])
        self.shown = {k: t for k, t in self.shown.items() if t >= limit}
        if not self.shown:
            return []
        return [ln for ln in self.transcript.entries if self.wanted(ln)][-KEEP_SHOWN:]
