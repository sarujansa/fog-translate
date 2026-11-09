"""Control window and the Qt side of the loop."""
from __future__ import annotations

import logging
import queue
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QVBoxLayout, QWidget)

from . import __version__, geometry, ollama, services, translate, window
from .config import Settings
from .engine import Engine
from .looper import Looper
from .overlay import TranslationOverlay
from .picker import RegionPicker

log = logging.getLogger(__name__)

STATUS = {
    "idle": "Gestoppt.",
    "no_region": "Noch kein Chat-Bereich markiert.",
    "no_game": "Dead by Daylight nicht gefunden – wartet.",
    "background": "DBD ist nicht im Vordergrund – pausiert.",
    "starting": "Startet …",
    "watching": "Beobachtet den Chat …",
    "asking": "Frage Claude …",
    "cap": "Tageslimit an Anfragen erreicht – pausiert bis morgen.",
    "error": "Fehler",
}
ERRORS = {
    "key": "API-Key fehlt oder ist ungültig.",
    "quota": "Limit, Kontingent oder Guthaben beim Dienst erreicht.",
    "net": "Keine Verbindung zum Dienst.",
    "refused": "Der Dienst hat diese Anfrage abgelehnt.",
    "answer": "Antwort des Dienstes nicht lesbar.",
    "model": "Modell nicht gefunden – Namen prüfen (bei Ollama: „ollama pull <Modell>“).",
    "server": "Ollama läuft nicht (oder ein anderer Port ist eingestellt).",
    "other": "Unerwarteter Fehler (siehe Log).",
}
NOTICES = {
    "claude": ("Das Bild des markierten Bereichs (kann Spielernamen und Nachrichten anderer Spieler zeigen) wird "
               "zum Übersetzen an Anthropic geschickt – mit deinem eigenen API-Key, auf deine Kosten."),
    "gemini": ("Das Bild des markierten Bereichs (kann Spielernamen und Nachrichten anderer Spieler zeigen) wird "
               "zum Übersetzen an Google geschickt. In der kostenlosen Stufe darf Google die Daten zur "
               "Verbesserung seiner Produkte nutzen und Menschen können sie lesen."),
    "ollama": ("Ollama läuft auf deinem PC – das Bild verlässt den Rechner nicht. Ollama installieren "
               "(ollama.com) und ein Bildmodell laden, z. B. „ollama pull qwen2.5vl:7b“ (ca. 6 GB, braucht eine "
               "Grafikkarte mit ≥ 8 GB) oder „gemma3:4b“ für schwächere Karten."),
}


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
        self.looper: Looper | None = None
        self.game = None
        self.overlay = TranslationOverlay(settings["font_px"])
        self.picker = None
        self._build()
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
        self.shot_btn = QPushButton("Letzten Ausschnitt zeigen", clicked=self.show_last_picture)
        self.run_btn = QPushButton("Starten", clicked=self.toggle)
        row.addWidget(self.pick_btn)
        row.addWidget(self.shot_btn)
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
        grid.addWidget(QLabel("Dienst:"), 1, 0)
        self.service = QComboBox()
        for sid, (label, _cloud) in services.SERVICES.items():
            self.service.addItem(label, sid)
        self.service.setCurrentIndex(list(services.SERVICES).index(s["service"]))
        self.service.currentIndexChanged.connect(self._service_changed)
        grid.addWidget(self.service, 1, 1)
        grid.addWidget(QLabel("Modell:"), 2, 0)
        model_row = QHBoxLayout()
        self.model = QComboBox()
        self.model.activated.connect(self._settings_changed)
        self._edit_hooked = None
        model_row.addWidget(self.model, 1)
        self.local_btn = QPushButton("Lokale Modelle laden", clicked=self._load_local_models)
        model_row.addWidget(self.local_btn)
        grid.addLayout(model_row, 2, 1)
        self.key_label = QLabel("API-Key:")
        grid.addWidget(self.key_label, 3, 0)
        key_row = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(self.key)
        self.key_btn = QPushButton("Speichern", clicked=self._save_key)
        key_row.addWidget(self.key_btn)
        grid.addLayout(key_row, 3, 1)
        self.key_link = QLabel()
        self.key_link.setOpenExternalLinks(True)
        self.key_link.setTextFormat(Qt.TextFormat.RichText)
        grid.addWidget(self.key_link, 4, 1)
        root.addLayout(grid)

        self.show_all = QCheckBox("Auch Zeilen in meiner Sprache zeigen")
        self.show_all.setChecked(bool(s["show_all"]))
        self.show_all.toggled.connect(self._settings_changed)
        root.addWidget(self.show_all)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)
        self.accept = QCheckBox("Verstanden")
        self.accept.toggled.connect(self._settings_changed)
        root.addWidget(self.accept)

        self.history = QListWidget()
        root.addWidget(self.history, 1)
        self.costs = QLabel()
        root.addWidget(self.costs)
        self.resize(560, 560)
        self._service_ui()

    def _service_ui(self):
        """Model list, key row and notice for the chosen service."""
        s = self.settings
        service = s["service"]
        self._filling = True
        self.model.clear()
        for mid, label in services.model_choices(service):
            self.model.addItem(label, mid)
        current = s[services.MODEL_SETTING[service]]
        i = self.model.findData(current)
        if i < 0:
            self.model.addItem(current, current)
            i = self.model.count() - 1
        self.model.setCurrentIndex(i)
        self.model.setEditable(service != "claude")
        edit = self.model.lineEdit()
        if edit is not None and edit is not self._edit_hooked:
            edit.editingFinished.connect(self._settings_changed)
            self._edit_hooked = edit
        cloud = services.is_cloud(service)
        for w in (self.key_label, self.key, self.key_btn, self.key_link):
            w.setVisible(cloud)
        self.local_btn.setVisible(service == "ollama")
        self.key.clear()
        self.key.setPlaceholderText("gespeichert" if s.has_stored_key(service) else "API-Key einfügen")
        if cloud:
            url = services.KEY_URL[service]
            self.key_link.setText('Key holen: <a href="%s">%s</a>' % (url, url))
        self.notice.setText(NOTICES[service])
        self.accept.setVisible(cloud)
        self.accept.setChecked(s.accepted(service))
        self._filling = False

    def _model_text(self) -> str:
        i = self.model.currentIndex()
        text = self.model.currentText().strip()
        if i >= 0 and self.model.itemText(i) == text and self.model.itemData(i):
            return str(self.model.itemData(i))
        return text

    def _service_changed(self):
        self.settings["service"] = self.service.currentData()
        self.settings.save()
        self._service_ui()
        if self.running:
            self._start_worker()
        self._refresh()

    def _settings_changed(self):
        if getattr(self, "_filling", False):
            return
        s = self.settings
        service = s["service"]
        s["target"] = self.target.currentData()
        model = self._model_text()
        if services.valid_model(service, model):
            s[services.MODEL_SETTING[service]] = model
        s["show_all"] = self.show_all.isChecked()
        if services.is_cloud(service):
            s.set_accepted(service, self.accept.isChecked())
        s.save()
        if self.running:
            self._start_worker()
        self._refresh()

    def _load_local_models(self):
        names = ollama.installed_models(int(self.settings["ollama_port"]))
        if not names:
            self.status.setText(ERRORS["server"] + " Oder noch kein Modell geladen.")
            return
        self._filling = True
        current = self._model_text()
        self.model.clear()
        for n in names:
            self.model.addItem(n, n)
        i = self.model.findData(current)
        self.model.setCurrentIndex(i if i >= 0 else 0)
        self._filling = False
        self._settings_changed()
        self.status.setText("%d lokale Modelle gefunden." % len(names))

    def _save_key(self):
        text = self.key.text().strip()
        service = self.settings["service"]
        if not text or not services.is_cloud(service):
            return
        stored = self.settings.set_api_key(service, text)
        self.key.clear()
        self.key.setPlaceholderText("gespeichert" if stored else "nur für diese Sitzung")
        if self.running:
            self._start_worker()
        self._refresh()

    def show_last_picture(self):
        """The picture last sent to the service, exactly as cut out (only in memory, never a file)."""
        img = self.engine.last_sent
        if img is None:
            self.status.setText("Noch nichts gesendet – erst starten und im Chat schreiben lassen.")
            return
        from PySide6.QtGui import QImage, QPixmap
        import numpy as np
        rgb = np.ascontiguousarray(np.asarray(img)[..., 2::-1])
        h, w = rgb.shape[:2]
        pic = QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())
        view = QLabel()
        view.setWindowTitle("Gesendeter Ausschnitt – %d × %d px" % (w, h))
        view.setPixmap(pic)
        view.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._picture_view = view
        view.show()

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
    def _start_looper(self):
        """(Re)start the look thread; it builds the translator itself, so the window never waits."""
        self._stop_looper()
        self.engine.worker = NoWorker()
        self.engine.status, self.engine.error = "starting", ""
        settings = self.settings
        log.info("Start: Dienst %s", settings["service"])
        self.looper = Looper(self.engine, lambda: services.make(settings), self.results.put, settings["look_s"])
        self.looper.start()

    def _stop_looper(self):
        if self.looper is not None:
            self.looper.stop()
            self.looper = None

    def _start_worker(self):            # settings changed while running
        self._start_looper()

    def toggle(self):
        if self.running:
            self.running = False
            self._stop_looper()
            self.engine.status = "idle"
            self.overlay.hide()
        else:
            service = self.settings["service"]
            if not self.settings.accepted(service):
                self.status.setText("Bitte erst den Hinweis unten bestätigen.")
                return
            self.running = True
            self._start_looper()
        self._refresh()

    def _pump(self):
        while True:
            try:
                kind, value = self.results.get_nowait()
            except queue.Empty:
                break
            if kind == "tick":
                self.game = value
            elif kind == "started":
                if self.engine.status == "starting":
                    self.engine.status = "idle"
            elif kind == "start_failed":
                self.running = False
                self._stop_looper()
                self.engine.status, self.engine.error = "error", value.kind
            elif kind == "answer":
                new = self.engine.answer(value)
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
        text = STATUS.get(e.status, e.status) if self.running or e.status not in ("watching", "starting") \
            else STATUS["idle"]
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
        self._stop_looper()
        self.overlay.close()
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
    from . import icon
    icon.set_app_id()
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setWindowIcon(icon.icon())
    settings = Settings()
    win = MainWindow(settings)
    win.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    win.show()
    return app.exec()
