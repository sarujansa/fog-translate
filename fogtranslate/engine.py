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
from .change import ChangeGate
from .lines import ChatLine, Transcript
from .translate import Result, TranslateError

KEEP_SHOWN = 8
QUOTA_WAIT_S = 60.0              # after a "limit reached" answer, wait at least this long
SERVICE_GAP_S = {"gemini": 6.5}  # Gemini's free tier allows about 10 requests a minute


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
        self.last_sent = None        # the last picture sent (in memory only) – "Letzten Ausschnitt zeigen"

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
            return
        if game is None or game.minimized:
            self.status = "no_game"
            self.gate.reset()
            return
        box = self.region_on_screen(game)
        if not in_front:
            if not self.settings["read_background"]:
                self.status = "background"
                return
            if region_free is None or not region_free(game, box):
                self.status = "covered"
                return
        img = grab(box)
        if img is None:
            return
        if self.status in ("idle", "no_game", "background", "covered", "no_region"):
            self.status = "watching"
        if not self.gate.look(img):
            if self._pending is not None:
                self._try_send()
            return
        self._pending = img
        self._try_send()

    def _try_send(self):
        t = self.clock()
        gap = max(float(self.settings["min_gap_s"]), SERVICE_GAP_S.get(self.settings["service"], 0.0))
        if self.worker.busy or t - self._last_request < gap or t < self._not_before:
            return
        day = self.now().strftime("%Y-%m-%d")
        if self.settings.requests_today(day) >= int(self.settings["daily_cap"]):
            self.status = "cap"
            self._pending = None
            return
        if self.worker.submit(self._pending):
            self.last_sent = self._pending
            self._last_request = t
            self._pending = None
            self.status = "asking"

    @_locked
    def answer(self, outcome) -> bool:
        """A finished request (in the Qt thread). True when the transcript changed."""
        n = self.now()
        if isinstance(outcome, TranslateError):
            self.status = "error"
            self.error = outcome.kind
            if outcome.kind == "quota":
                self._not_before = self.clock() + QUOTA_WAIT_S
            return False
        assert isinstance(outcome, Result)
        self.settings.count_request(n.strftime("%Y-%m-%d"), n.strftime("%Y-%m"), outcome.cost_usd)
        self.status = "watching"
        self.error = ""
        added, replaced = self.transcript.add(outcome.lines)
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
        """Messages for the overlay: the newest ones that changed within ``show_s``."""
        limit = self.clock() - float(self.settings["show_s"])
        self.shown = {k: t for k, t in self.shown.items() if t >= limit}
        out = [ln for ln in self.transcript.entries if ln.key() in self.shown and self.wanted(ln)]
        return out[-KEEP_SHOWN:]
