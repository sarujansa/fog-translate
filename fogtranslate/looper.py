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
                 find_game=window.find_game, in_front=window.game_in_front, region_free=window.region_free,
                 own_rects=lambda: ()):
        super().__init__(name="look", daemon=True)
        self.engine = engine
        self.make_translator = make_translator
        self.post = post
        self.interval = max(0.2, float(interval))
        self.stop_event = threading.Event()
        self._grabber_factory = grabber_factory
        self._find_game = find_game
        self._in_front = in_front
        self._region_free = region_free
        self._own_rects = own_rects          # screen rects of our own windows (plain tuples, no Qt object)

    def stop(self):
        self.stop_event.set()

    def _failed(self, error):
        """A stopped looper (settings changed while it started) says nothing: its message would stop the new one."""
        if not self.stop_event.is_set():
            self.post(("start_failed", error))

    def _grab_without_us(self, grabber):
        from .grab import blank

        def grab(box):
            img = grabber.grab(box)
            return blank(img, box, list(self._own_rects())) if img is not None else None
        return grab

    def run(self):
        t0 = time.monotonic()
        try:
            translator = self.make_translator()
        except TranslateError as e:
            self._failed(e)
            return
        except Exception as e:
            log.exception("Übersetzer nicht gestartet")
            self._failed(TranslateError("other", type(e).__name__))
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
                self._failed(TranslateError("other", type(e).__name__))
                return
            while not self.stop_event.is_set():
                now = time.monotonic()
                if game is None or now - game_at >= GAME_EVERY_S:
                    game, game_at = self._find_game(), now
                try:
                    self.engine.look(game, self._in_front(game), self._grab_without_us(grabber),
                                     self._region_free)
                except Exception:
                    log.exception("Blick fehlgeschlagen")
                self.post(("tick", game))
                self.stop_event.wait(self.interval)
        finally:
            if grabber is not None:
                grabber.close()
