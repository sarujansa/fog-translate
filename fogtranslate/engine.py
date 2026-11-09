"""The loop without Qt: look at the region, ask Claude when something new has settled, keep what to show.

Rules: look only while DBD is the active window (then the region shows the game, not another program); at most
one request at a time, at least ``min_gap_s`` apart, at most ``daily_cap`` a day.
"""
from __future__ import annotations

import time
from datetime import datetime

from . import geometry
from .change import ChangeGate
from .lines import ChatLine, SeenLines
from .translate import Result, TranslateError

KEEP_SHOWN = 8


class Engine:
    def __init__(self, settings, worker, clock=time.monotonic, now=datetime.now):
        self.settings = settings
        self.worker = worker
        self.clock = clock
        self.now = now
        self.gate = ChangeGate()
        self.seen = SeenLines()
        self.shown: list[tuple[float, ChatLine]] = []
        self.status = "idle"         # idle | no_region | no_game | background | watching | asking | cap | error
        self.error = ""
        self._last_request = -1e9
        self._pending = None

    def region_on_screen(self, game) -> tuple[int, int, int, int] | None:
        rel = self.settings["region"]
        if game is None or rel is None:
            return None
        cx, cy, cw, ch = game.client
        x, y, w, h = geometry.from_relative(rel, geometry.viewport(cw, ch))
        return cx + x, cy + y, w, h

    def look(self, game, in_front: bool, grab) -> None:
        """One tick. ``grab(box)`` returns the BGR picture of a screen box."""
        if self.settings["region"] is None:
            self.status = "no_region"
            return
        if game is None or game.minimized:
            self.status = "no_game"
            self.gate.reset()
            return
        if not in_front:
            self.status = "background"
            return
        box = self.region_on_screen(game)
        img = grab(box)
        if img is None:
            return
        if self.status in ("idle", "no_game", "background", "no_region"):
            self.status = "watching"
        if not self.gate.look(img):
            if self._pending is not None:
                self._try_send()
            return
        self._pending = img
        self._try_send()

    def _try_send(self):
        t = self.clock()
        if self.worker.busy or t - self._last_request < float(self.settings["min_gap_s"]):
            return
        day = self.now().strftime("%Y-%m-%d")
        if self.settings.requests_today(day) >= int(self.settings["daily_cap"]):
            self.status = "cap"
            self._pending = None
            return
        if self.worker.submit(self._pending):
            self._last_request = t
            self._pending = None
            self.status = "asking"

    def answer(self, outcome) -> list[ChatLine]:
        """A finished request (in the Qt thread). Returns the newly shown lines."""
        n = self.now()
        if isinstance(outcome, TranslateError):
            self.status = "error"
            self.error = outcome.kind
            return []
        assert isinstance(outcome, Result)
        self.settings.count_request(n.strftime("%Y-%m-%d"), n.strftime("%Y-%m"), outcome.cost_usd)
        self.status = "watching"
        self.error = ""
        new = self.seen.new(outcome.lines)
        if not self.settings["show_all"]:
            new = [ln for ln in new if ln.translate]
        t = self.clock()
        self.shown.extend((t, ln) for ln in new)
        self.shown = self.shown[-KEEP_SHOWN:]
        return new

    def visible(self) -> list[ChatLine]:
        """Lines still on screen (newer than ``show_s``)."""
        limit = self.clock() - float(self.settings["show_s"])
        self.shown = [(t, ln) for t, ln in self.shown if t >= limit]
        return [ln for _, ln in self.shown]
