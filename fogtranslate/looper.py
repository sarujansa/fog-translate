"""The look thread: everything that can take time runs here, never in the window's thread.

Building the translator (the Claude SDK takes seconds to import on Windows, longer while a virus scanner checks
the files on the first start), finding the DBD window, grabbing the region and comparing pictures. The window
only gets messages through ``post`` (a queue it empties with a timer).
"""
from __future__ import annotations

import logging
import threading
import time

from . import window
from .translate import TranslateError, Worker

log = logging.getLogger(__name__)
GAME_EVERY_S = 1.0


class Looper(threading.Thread):
    def __init__(self, engine, make_translator, post, interval: float, grabber_factory=None,
                 find_game=window.find_game, in_front=window.game_in_front):
        super().__init__(name="look", daemon=True)
        self.engine = engine
        self.make_translator = make_translator
        self.post = post
        self.interval = max(0.2, float(interval))
        self.stop_event = threading.Event()
        self._grabber_factory = grabber_factory
        self._find_game = find_game
        self._in_front = in_front

    def stop(self):
        self.stop_event.set()

    def run(self):
        t0 = time.monotonic()
        try:
            translator = self.make_translator()
        except TranslateError as e:
            self.post(("start_failed", e))
            return
        except Exception as e:
            log.exception("Übersetzer nicht gestartet")
            self.post(("start_failed", TranslateError("other", type(e).__name__)))
            return
        if self.stop_event.is_set():
            return
        self.engine.worker = Worker(translator, lambda outcome: self.post(("answer", outcome)))
        log.info("Übersetzer bereit nach %.1f s", time.monotonic() - t0)
        self.post(("started", None))
        grabber = None
        game, game_at = None, -1e9
        try:
            if self._grabber_factory is None:
                from .grab import Grabber
                self._grabber_factory = Grabber
            try:
                grabber = self._grabber_factory()
            except Exception as e:
                log.exception("Bildschirmaufnahme nicht gestartet")
                self.post(("start_failed", TranslateError("other", type(e).__name__)))
                return
            while not self.stop_event.is_set():
                now = time.monotonic()
                if game is None or now - game_at >= GAME_EVERY_S:
                    game, game_at = self._find_game(), now
                try:
                    self.engine.look(game, self._in_front(game), grabber.grab)
                except Exception:
                    log.exception("Blick fehlgeschlagen")
                self.post(("tick", game))
                self.stop_event.wait(self.interval)
        finally:
            if grabber is not None:
                grabber.close()
