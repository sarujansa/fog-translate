"""Control window and the Qt side of the loop."""
from __future__ import annotations

import logging
import queue
import sys
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QVBoxLayout, QWidget)

from . import __version__, geometry, translate, window
from .config import Settings
from .engine import Engine
from .overlay import TranslationOverlay
from .picker import RegionPicker

log = logging.getLogger(__name__)

STATUS = {
    "idle": "Gestoppt.",
    "no_region": "Noch kein Chat-Bereich markiert.",
    "no_game": "Dead by Daylight nicht gefunden – wartet.",
    "background": "DBD ist nicht im Vordergrund – pausiert.",
    "watching": "Beobachtet den Chat …",
    "asking": "Frage Claude …",
    "cap": "Tageslimit an Anfragen erreicht – pausiert bis morgen.",
    "error": "Fehler",
}
ERRORS = {
    "key": "API-Key fehlt oder ist ungültig.",
    "quota": "Limit oder Guthaben bei Anthropic erreicht.",
    "net": "Keine Verbindung zu Anthropic.",
    "refused": "Claude hat diese Anfrage abgelehnt.",
    "answer": "Antwort von Claude nicht lesbar.",
    "other": "Unerwarteter Fehler (siehe Log).",
}
NOTICE = ("Ich weiß: Das Bild des markierten Bereichs (kann Spielernamen zeigen) wird zum Übersetzen an Anthropic "
          "(Claude) geschickt – mit meinem eigenen API-Key, auf meine Kosten.")


class NoWorker:
    busy = False

    def submit(self, _img):
        return False


class MainWindow(QWidget):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.setWindowTitle("Fog Translate " + __version__)
        self.results: queue.Queue = queue.Queue()      # thread → window, emptied by a QTimer (no Qt signal)
        self.engine = Engine(settings, NoWorker())
        self.running = False
        self.game = None
        self._game_at = 0.0
        self._grabber = None
        self.overlay = TranslationOverlay(settings["font_px"])
        self.picker = None
        self._build()
        self.look_timer = QTimer(self, interval=int(float(settings["look_s"]) * 1000), timeout=self._look)
        self.pump_timer = QTimer(self, interval=200, timeout=self._pump)
        self.pump_timer.start()
        self._refresh()

    # ---------------------------------------------------------------- UI
    def _build(self):
        s = self.settings
        root = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        row = QHBoxLayout()
        self.pick_btn = QPushButton("Chat-Bereich markieren", clicked=self.pick_region)
        self.run_btn = QPushButton("Starten", clicked=self.toggle)
        row.addWidget(self.pick_btn)
        row.addWidget(self.run_btn)
        root.addLayout(row)

        grid = QGridLayout()
        grid.addWidget(QLabel("Übersetzen nach:"), 0, 0)
        self.target = QComboBox()
        for code in translate.LANGUAGES:
            self.target.addItem(code.upper(), code)
        self.target.setCurrentIndex(list(translate.LANGUAGES).index(s["target"]))
        self.target.currentIndexChanged.connect(self._settings_changed)
        grid.addWidget(self.target, 0, 1)
        grid.addWidget(QLabel("Modell:"), 1, 0)
        self.model = QComboBox()
        for mid, (label, *_rest) in translate.MODELS.items():
            self.model.addItem(label, mid)
        self.model.setCurrentIndex(list(translate.MODELS).index(s["model"]))
        self.model.currentIndexChanged.connect(self._settings_changed)
        grid.addWidget(self.model, 1, 1)
        grid.addWidget(QLabel("Anthropic API-Key:"), 2, 0)
        key_row = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("gespeichert" if s["api_key"] else "sk-ant-…")
        key_row.addWidget(self.key)
        key_row.addWidget(QPushButton("Speichern", clicked=self._save_key))
        grid.addLayout(key_row, 2, 1)
        root.addLayout(grid)

        self.show_all = QCheckBox("Auch Zeilen in meiner Sprache zeigen")
        self.show_all.setChecked(bool(s["show_all"]))
        self.show_all.toggled.connect(self._settings_changed)
        root.addWidget(self.show_all)
        notice = QLabel(NOTICE)
        notice.setWordWrap(True)
        root.addWidget(notice)
        self.accept = QCheckBox("Verstanden")
        self.accept.setChecked(bool(s["accepted"]))
        self.accept.toggled.connect(self._settings_changed)
        root.addWidget(self.accept)

        self.history = QListWidget()
        root.addWidget(self.history, 1)
        self.costs = QLabel()
        root.addWidget(self.costs)
        self.resize(520, 480)

    def _settings_changed(self):
        s = self.settings
        s["target"] = self.target.currentData()
        s["model"] = self.model.currentData()
        s["show_all"] = self.show_all.isChecked()
        s["accepted"] = self.accept.isChecked()
        s.save()
        if self.running:
            self._start_worker()
        self._refresh()

    def _save_key(self):
        text = self.key.text().strip()
        if not text:
            return
        stored = self.settings.set_api_key(text)
        self.key.clear()
        self.key.setPlaceholderText("gespeichert" if stored else "nur für diese Sitzung")
        if self.running:
            self._start_worker()
        self._refresh()

    # ---------------------------------------------------------------- region
    def pick_region(self):
        game = window.find_game()
        if game is not None and not game.minimized:
            client = game.client
        else:                                          # no DBD: mark on the primary screen (for testing)
            g = QApplication.primaryScreen().geometry()
            client = (g.x(), g.y(), g.width(), g.height())
        self.overlay.hide()
        self.picker = RegionPicker(client, self._picked, self.settings["region"])
        self.picker.start()

    def _picked(self, rel):
        self.picker = None
        if rel is not None:
            self.settings["region"] = list(rel)
            self.settings.save()
            self.engine.gate.reset()
            self.engine.seen.clear()
        self._refresh()

    # ---------------------------------------------------------------- loop
    def _start_worker(self):
        self.engine.worker = translate.Worker(
            translate.Translator(self.settings.api_key(), self.settings["model"], self.settings["target"]),
            self.results.put)

    def toggle(self):
        if self.running:
            self.running = False
            self.look_timer.stop()
            self.engine.status = "idle"
            self.overlay.hide()
        else:
            if not self.settings["accepted"]:
                self.status.setText("Bitte erst den Hinweis unten bestätigen.")
                return
            if not self.settings.api_key():
                self.status.setText(ERRORS["key"])
                return
            self._start_worker()
            self.running = True
            self.look_timer.start()
        self._refresh()

    def _look(self):
        now = time.monotonic()
        if self.game is None or now - self._game_at > 1.0:
            self.game = window.find_game()
            self._game_at = now
        if self._grabber is None:
            from .grab import Grabber
            self._grabber = Grabber()
        try:
            self.engine.look(self.game, window.game_in_front(self.game), self._grabber.grab)
        except Exception:
            log.exception("Blick fehlgeschlagen")
        self._refresh_overlay()
        self._refresh()

    def _pump(self):
        while True:
            try:
                outcome = self.results.get_nowait()
            except queue.Empty:
                break
            new = self.engine.answer(outcome)
            self.settings.save()
            for ln in new:
                self.history.addItem(_history_text(ln))
            while self.history.count() > 200:
                self.history.takeItem(0)
            if new:
                self.history.scrollToBottom()
        if self.running:
            self._refresh_overlay()
        self._refresh()

    def _refresh_overlay(self):
        box = self.engine.region_on_screen(self.game)
        lines = self.engine.visible() if self.running and box is not None else []
        if not lines or self.picker is not None:
            self.overlay.hide()
            return
        screen = QApplication.screenAt(self.overlay.geometry().center()) or QApplication.primaryScreen()
        g = screen.geometry()
        self.overlay.show_lines(lines, lambda size: geometry.overlay_spot(box, size,
                                                                          (g.x(), g.y(), g.width(), g.height())))

    def _refresh(self):
        e = self.engine
        text = STATUS.get(e.status, e.status) if self.running or e.status != "watching" else STATUS["idle"]
        if not self.running and self.settings["region"] is None:
            text = STATUS["no_region"]
        if e.status == "error":
            text = ERRORS.get(e.error, e.error)
        self.status.setText(text)
        self.run_btn.setText("Stoppen" if self.running else "Starten")
        now = datetime.now()
        spent = float(self.settings["spent"].get(now.strftime("%Y-%m"), 0.0))
        self.costs.setText("Heute %d Anfragen · diesen Monat ca. %.2f $ (geschätzt)"
                           % (self.settings.requests_today(now.strftime("%Y-%m-%d")), spent))

    def closeEvent(self, event):
        self.look_timer.stop()
        self.overlay.close()
        if self._grabber is not None:
            self._grabber.close()
        super().closeEvent(event)


def _history_text(ln) -> str:
    head = (ln.sender + ": ") if ln.sender else ""
    if ln.translate and ln.translation != ln.text:
        return "[%s] %s%s   ←  %s" % (ln.language.upper(), head, ln.translation, ln.text)
    return head + ln.text


def run(argv=None) -> int:
    import os
    # Qt coordinates = physical pixels, like the Win32 window rectangles and mss
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    app = QApplication.instance() or QApplication(argv or sys.argv)
    settings = Settings()
    win = MainWindow(settings)
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    win.show()
    return app.exec()
