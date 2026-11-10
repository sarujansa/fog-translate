"""A fast chat: every message must be in a picture that is sent, also when the service answers slowly.

The chat is simulated (11 visible lines, the program looks every 0.5 s, the service takes ``latency`` seconds).
A message counts as covered when one of the pictures of a request shows its line completely.
"""
import random
from datetime import datetime
from types import SimpleNamespace

import pytest

from fogtranslate.config import Settings
from fogtranslate.engine import BACKLOG_MAX, Engine
from fogtranslate.translate import Result
from test_core import READ, _chat_lines

WORDS = "gen hook heal camp tunnel gg wp noob killer surv flash pallet loop save run basement exit gate totem".split()
H, LINE, VISIBLE = 260, 22, 11
GAME = SimpleNamespace(client=(0, 0, 3440, 1440), minimized=False)


def simulate(rate, n, latency, service="claude"):
    rng = random.Random(1)
    msgs = ["P%d: %s %d" % (i % 5, " ".join(rng.sample(WORDS, 3)), i) for i in range(n)]
    s = Settings()
    s["region"] = [0.02, 0.6, 0.3, 0.3]
    s["service"] = service
    s["daily_cap"] = 5000
    t = [0.0]
    frames = {}                                   # id(frame) → (frame kept alive, ids shown)
    covered, stats = set(), {"requests": 0, "max_parts": 0}

    class Worker:
        busy = False

        def submit(self, picture):
            self.busy = True
            parts = eng._backlog + [eng._pending]
            stats["requests"] += 1
            stats["max_parts"] = max(stats["max_parts"], len(parts))
            assert picture.shape[0] >= sum(p.shape[0] for p in parts)
            for part in parts:
                frame = part if part.base is None else part.base
                ids = frames[id(frame)][1]
                top = H - part.shape[0]
                for k, mid in enumerate(reversed(ids)):          # k-th line from the bottom
                    if H - 8 - LINE * (k + 1) >= top:
                        covered.add(mid)
            return True

    worker = Worker()
    eng = Engine(s, worker, clock=lambda: t[0], now=lambda: datetime(2026, 11, 10, 20, 0))
    done_at = None
    while t[0] < n / rate + 20:
        shown = min(n, int(t[0] * rate))
        ids = list(range(max(0, shown - VISIBLE), shown))
        img = _chat_lines([msgs[i] for i in ids])
        frames[id(img)] = (img, ids)
        before = stats["requests"]
        eng.look(GAME, True, lambda box: img)
        if stats["requests"] > before:
            done_at = t[0] + latency
        if done_at is not None and t[0] >= done_at:
            worker.busy = False
            eng.answer(Result([READ], 0.0))
            done_at = None
        t[0] += 0.5
    return sorted(set(range(n)) - covered), stats


@pytest.mark.parametrize("rate,n,latency,service", [
    (0.2, 10, 1.5, "claude"),          # a calm lobby
    (1.0, 20, 1.5, "claude"),
    (3.0, 30, 1.5, "claude"),          # everybody types at once
    (3.0, 30, 4.0, "claude"),          # … and the service is slow
    (3.0, 30, 1.5, "gemini"),          # Gemini's free tier: 6.5 s between requests
])
def test_no_message_is_lost(rate, n, latency, service):
    missed, stats = simulate(rate, n, latency, service)
    assert missed == [], (missed, stats)
    assert stats["max_parts"] <= BACKLOG_MAX + 1


def test_a_calm_chat_still_sends_single_small_pictures():
    missed, stats = simulate(0.2, 10, 1.5)
    assert missed == [] and stats["max_parts"] == 1 and stats["requests"] == 10
