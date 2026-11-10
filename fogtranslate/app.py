"""Control window and the Qt side of the loop."""
from __future__ import annotations

import logging
import queue
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QTextBrowser, QVBoxLayout, QWidget)

from . import __version__, geometry, ollama, qtgeom, services, translate, window
from .config import Settings
from .engine import Engine
from .looper import Looper
from .overlay import TranslationOverlay
from .picker import RegionPicker

log = logging.getLogger(__name__)

STATUS = {
    "idle": "Stopped.",
    "no_region": "No chat area marked yet.",
    "no_game": "Dead by Daylight not found – waiting.",
    "background": "DBD is not in the foreground – paused.",
    "covered": "A window covers the chat – paused until it is visible again.",
    "starting": "Starting …",
    "watching": "Watching the chat …",
    "no_chat": "Waiting for the chat … no text found in the marked area (never there? mark it again)",
    "asking": "Translating …",
    "cap": "Daily request limit reached – paused until tomorrow.",
    "error": "Error",
    "unconfirmed": "Stopped: please confirm the notice below for this service, then press Start.",
}
ERRORS = {
    "key": "API key missing or invalid.",
    "quota": "Rate limit, quota or credit of the service reached.",
    "net": "No connection to the service.",
    "refused": "The service declined this request.",
    "answer": "Could not read the service's answer.",
    "model": "Model not found – check the name (Ollama: \"ollama pull <model>\").",
    "server": "Ollama is not running (or a different port is set).",
    "other": "Unexpected error (see log).",
}
NOTICES = {
    "claude": ("The picture of the marked area (it can show player names and other players' messages) is sent to "
               "Anthropic for translation – with your own API key, at your own cost."),
    "gemini": ("The picture of the marked area (it can show player names and other players' messages) is sent to "
               "Google for translation. On the free tier Google may use the data to improve its products, and "
               "humans may read it."),
    "ollama": ("Ollama runs on your PC – the picture never leaves it. Install Ollama (ollama.com) and pull a vision "
               "model, e.g. \"ollama pull qwen2.5vl:7b\" (about 6 GB, needs a GPU with 8 GB or more) or "
               "\"gemma3:4b\" for smaller cards."),
}


MIN_CAP, MAX_CAP = 10, 5000


class NoWheelSpinBox(QSpinBox):
    """The mouse wheel never changes the limit while scrolling past it – only when the field has focus."""

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


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
        self.overlay.hide_in_captures = bool(settings["hide_in_captures"])
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
        self.test_btn = QPushButton("Test service", clicked=self.test_service)
        self.pick_btn = QPushButton("Mark chat area", clicked=self.pick_region)
        self.shot_btn = QPushButton("Show last capture", clicked=self.show_last_picture)
        self.run_btn = QPushButton("Start", clicked=self.toggle)
        row.addWidget(self.pick_btn)
        row.addWidget(self.shot_btn)
        row.addWidget(self.run_btn)
        root.addLayout(row)

        grid = QGridLayout()
        grid.addWidget(QLabel("Translate to:"), 0, 0)
        self.target = QComboBox()
        for code in translate.LANGUAGES:
            self.target.addItem("%s (%s)" % (translate.LANGUAGES[code], code.upper()), code)
        self.target.setCurrentIndex(list(translate.LANGUAGES).index(s["target"]))
        self.target.currentIndexChanged.connect(self._settings_changed)
        grid.addWidget(self.target, 0, 1)
        grid.addWidget(QLabel("Service:"), 1, 0)
        self.service = QComboBox()
        for sid, (label, _cloud) in services.SERVICES.items():
            self.service.addItem(label, sid)
        self.service.setCurrentIndex(list(services.SERVICES).index(s["service"]))
        self.service.currentIndexChanged.connect(self._service_changed)
        grid.addWidget(self.service, 1, 1)
        grid.addWidget(QLabel("Model:"), 2, 0)
        model_row = QHBoxLayout()
        self.model = QComboBox()
        self.model.activated.connect(self._settings_changed)
        self._edit_hooked = None
        model_row.addWidget(self.model, 1)
        self.local_btn = QPushButton("Load local models", clicked=self._load_local_models)
        model_row.addWidget(self.local_btn)
        grid.addLayout(model_row, 2, 1)
        self.key_label = QLabel("API key:")
        grid.addWidget(self.key_label, 3, 0)
        key_row = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        key_row.addWidget(self.key)
        self.key_btn = QPushButton("Save", clicked=self._save_key)
        key_row.addWidget(self.key_btn)
        key_row.addWidget(self.test_btn)
        grid.addLayout(key_row, 3, 1)
        self.key_link = QLabel()
        self.key_link.setOpenExternalLinks(True)
        self.key_link.setTextFormat(Qt.TextFormat.RichText)
        grid.addWidget(self.key_link, 4, 1)
        grid.addWidget(QLabel("Daily limit:"), 5, 0)
        limit_row = QHBoxLayout()
        self.daily_cap = NoWheelSpinBox()
        self.daily_cap.setRange(MIN_CAP, MAX_CAP)
        self.daily_cap.setSingleStep(50)
        self.daily_cap.setSuffix(" requests per day")
        self.daily_cap.setValue(int(s["daily_cap"]))
        self.daily_cap.valueChanged.connect(self._cap_changed)
        limit_row.addWidget(self.daily_cap)
        limit_row.addStretch(1)
        grid.addLayout(limit_row, 5, 1)
        grid.addWidget(QLabel("Overlay:"), 6, 0)
        look_row = QHBoxLayout()
        self.font_px = NoWheelSpinBox()
        self.font_px.setRange(10, 48)
        self.font_px.setPrefix("text size ")
        self.font_px.setSuffix(" px")
        self.font_px.setValue(int(s["font_px"]))
        self.font_px.valueChanged.connect(self._look_changed)
        self.show_s = NoWheelSpinBox()
        self.show_s.setRange(3, 600)
        self.show_s.setSingleStep(5)
        self.show_s.setPrefix("show for ")
        self.show_s.setSuffix(" s")
        self.show_s.setValue(int(float(s["show_s"])))
        self.show_s.valueChanged.connect(self._look_changed)
        look_row.addWidget(self.font_px)
        look_row.addWidget(self.show_s)
        look_row.addStretch(1)
        grid.addLayout(look_row, 6, 1)
        root.addLayout(grid)

        self.show_all = QCheckBox("Also show messages already in my language")
        self.show_all.setChecked(bool(s["show_all"]))
        self.show_all.toggled.connect(self._settings_changed)
        root.addWidget(self.show_all)
        self.background = QCheckBox("Also read while DBD is in the background (only while no window covers the chat)")
        self.background.setChecked(bool(s["read_background"]))
        self.background.toggled.connect(self._settings_changed)
        root.addWidget(self.background)
        self.auto_start = QCheckBox("Start automatically when Fog Translate opens")
        self.auto_start.setChecked(bool(s["auto_start"]))
        self.auto_start.toggled.connect(self._auto_changed)
        root.addWidget(self.auto_start)
        self.only_chat = QCheckBox("Show translations only while the chat is visible")
        self.only_chat.setChecked(bool(s["hide_without_chat"]))
        self.only_chat.toggled.connect(self._auto_changed)
        root.addWidget(self.only_chat)
        self.hide_caps = QCheckBox("Hide the translation in screenshots and recordings")
        self.hide_caps.setChecked(bool(s["hide_in_captures"]))
        self.hide_caps.toggled.connect(self._settings_changed)
        root.addWidget(self.hide_caps)
        self.to_tray = QCheckBox("Keep running in the tray when I close the window")
        self.to_tray.setChecked(bool(s["close_to_tray"]))
        self.to_tray.toggled.connect(self._settings_changed)
        root.addWidget(self.to_tray)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)
        self.accept = QCheckBox("I understand")
        self.accept.toggled.connect(self._settings_changed)
        root.addWidget(self.accept)

        self.history = QTextBrowser()
        self.history.setOpenLinks(False)
        self.history.setPlaceholderText("Translated messages appear here.")
        root.addWidget(self.history, 1)
        bottom = QHBoxLayout()
        self.costs = QLabel()
        bottom.addWidget(self.costs, 1)
        self.setup_btn = QPushButton("Setup assistant", clicked=self.open_setup)
        bottom.addWidget(self.setup_btn)
        self.update_btn = QPushButton("Check for updates", clicked=self.update_clicked)
        bottom.addWidget(self.update_btn)
        root.addLayout(bottom)
        self._update = None          # last update.Check
        self.overlay_hidden = False  # hotkey / tray: translations hidden until toggled again
        self.tray = None
        self.hotkey = None
        self._quitting = False
        self.resize(560, 560)
        self._service_ui()

    def _auto_changed(self, _on=None):
        """Neither box changes what is sent, so the look thread keeps running."""
        self.settings["auto_start"] = self.auto_start.isChecked()
        self.settings["hide_without_chat"] = self.only_chat.isChecked()
        self.settings.save()
        if self.running:
            self._refresh_overlay()

    def can_auto_start(self) -> bool:
        """Start by itself only when a click on Start would work: area marked, notice confirmed, key there."""
        s = self.settings
        service = s["service"]
        return bool(s["auto_start"] and not self.running and s["region"] is not None and s.accepted(service)
                    and (not services.is_cloud(service) or s.api_key(service)))

    def auto_start_now(self) -> bool:
        if not self.can_auto_start():
            return False
        log.info("Automatic start")
        self.toggle()
        return self.running

    def _look_changed(self, _value=None):
        self.settings["font_px"] = int(self.font_px.value())
        self.settings["show_s"] = float(self.show_s.value())
        self.settings.save()
        self.overlay.set_font_px(self.settings["font_px"])
        if self.running:
            self._refresh_overlay()

    # ---------------------------------------------------------------- test, tray, hotkey
    def test_service(self):
        """One request with a made-up chat picture: shows whether key, model and service work, and how fast."""
        service = self.settings["service"]
        if not self.settings.accepted(service):
            self.status.setText("Please confirm the notice below first.")
            return
        self.test_btn.setEnabled(False)
        self.status.setText("Testing %s …" % services.SERVICES[service][0])
        settings, put = self.settings, self.results.put

        def work():
            import time
            t0 = time.monotonic()
            try:
                result = services.make(settings).request(translate.sample_picture())
                result.seconds = time.monotonic() - t0
                put(("test", result))
            except translate.TranslateError as e:
                put(("test", e))
            except Exception as e:
                log.exception("Test failed")
                put(("test", translate.TranslateError("other", type(e).__name__)))

        import threading
        threading.Thread(target=work, name="test", daemon=True).start()

    def _tested(self, outcome):
        self.test_btn.setEnabled(True)
        if isinstance(outcome, translate.TranslateError):
            self._test_text = "Test failed: " + ERRORS.get(outcome.kind, outcome.kind)
        else:
            now = datetime.now()
            self.settings.count_request(now.strftime("%Y-%m-%d"), now.strftime("%Y-%m"), outcome.cost_usd)
            self.settings.save()
            self._test_text = ("Test OK – %d of 3 messages read in %.1f s."
                               % (min(3, len(outcome.lines)), outcome.seconds))
        log.info("Test: %s", self._test_text)
        self._test_until = datetime.now().timestamp() + 15

    def toggle_overlay(self):
        self.overlay_hidden = not self.overlay_hidden
        self._refresh_overlay()
        self._tray_texts()

    def setup_tray(self, app):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        from . import icon
        self.tray = QSystemTrayIcon(icon.icon(), self)
        self.tray.setToolTip("Fog Translate")
        menu = QMenu()
        self._act_window = QAction("Show window", menu, triggered=self.show_window)
        self._act_run = QAction("Start", menu, triggered=self.toggle)
        self._act_overlay = QAction("Hide translations", menu, triggered=self.toggle_overlay)
        self._act_quit = QAction("Quit", menu, triggered=self.quit)
        for a in (self._act_window, self._act_run, self._act_overlay):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(self._act_quit)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window()
                                    if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self._tray_texts()
        return True

    def _tray_texts(self):
        if self.tray is None:
            return
        self._act_run.setText("Stop" if self.running else "Start")
        self._act_overlay.setText("Show translations" if self.overlay_hidden else "Hide translations")

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit(self):
        self._quitting = True
        self.close()

    def setup_hotkey(self, app):
        from .hotkey import Hotkey
        self.hotkey = Hotkey(self.settings["hide_hotkey"], self.toggle_overlay)
        return self.hotkey.start(app)

    def open_setup(self):
        """The setup assistant (also shown by itself at the very first start)."""
        from .wizard import SetupWizard
        if self.running:
            self.toggle()
        self.wizard = SetupWizard(self.settings, self._setup_done)
        self.wizard.show()
        self.wizard.raise_()
        self.wizard.activateWindow()

    def _setup_done(self):
        """Take over what the assistant stored."""
        self.wizard = None
        s = self.settings
        self._filling = True
        self.service.setCurrentIndex(self.service.findData(s["service"]))
        self.target.setCurrentIndex(self.target.findData(s["target"]))
        self._filling = False
        self._service_ui()
        self._refresh()
        self.show_window()

    def _cap_changed(self, value: int):
        self.settings["daily_cap"] = int(value)
        self.settings.save()
        if self.settings.requests_today(datetime.now().strftime("%Y-%m-%d")) < value:
            self.engine.cap_raised()
        self._refresh()

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
        self.key.setPlaceholderText("saved" if s.has_stored_key(service) else "Paste API key")
        if cloud:
            url = services.KEY_URL[service]
            self.key_link.setText('Get a key: <a href="%s">%s</a>' % (url, url))
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
        if s["show_all"] != self.show_all.isChecked():
            s["show_all"] = self.show_all.isChecked()
            self._render_history()
        s["read_background"] = self.background.isChecked()
        s["hide_in_captures"] = self.hide_caps.isChecked()
        s["close_to_tray"] = self.to_tray.isChecked()
        self.overlay.hide_in_captures = s["hide_in_captures"]
        if services.is_cloud(service):
            s.set_accepted(service, self.accept.isChecked())
        s.save()
        if self.running:
            self._start_worker()
        self._refresh()

    def _load_local_models(self):
        names = ollama.installed_models(int(self.settings["ollama_port"]))
        if not names:
            self.status.setText(ERRORS["server"] + " Or no model pulled yet.")
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
        self.status.setText("%d local models found." % len(names))

    def _save_key(self):
        text = self.key.text().strip()
        service = self.settings["service"]
        if not text or not services.is_cloud(service):
            return
        stored = self.settings.set_api_key(service, text)
        self.key.clear()
        self.key.setPlaceholderText("saved" if stored else "for this session only")
        if self.running:
            self._start_worker()
        self._refresh()

    def show_last_picture(self):
        """The picture last sent to the service, exactly as cut out (only in memory, never a file)."""
        img = self.engine.last_sent
        if img is None:
            self.status.setText("Nothing sent yet – start first and wait for chat messages.")
            return
        from PySide6.QtGui import QImage, QPixmap
        import numpy as np
        rgb = np.ascontiguousarray(np.asarray(img)[..., 2::-1])
        h, w = rgb.shape[:2]
        pic = QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())
        view = QLabel()
        view.setWindowTitle("Sent capture – %d × %d px" % (w, h))
        view.setPixmap(pic)
        view.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._picture_view = view
        view.show()

    def _render_history(self):
        bar = self.history.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        self.history.setHtml(history_html(self.engine.messages()[-100:]))
        if at_end:
            bar.setValue(bar.maximum())

    # ---------------------------------------------------------------- updates (only on click)
    UPDATE_TEXT = {
        "current": "Fog Translate is up to date.",
        "dirty": "Cannot update: files in the program folder were changed.",
        "branch": "Cannot update: not on the \"main\" branch.",
        "ahead": "Cannot update: the program folder has its own commits.",
        "error": "Update check failed (no connection to GitHub?).",
    }

    def update_clicked(self):
        from . import update
        c = self._update
        if c is not None and c.state == "behind":
            self._update_apply()
            return
        if c is not None and c.state == "newer":
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            QDesktopServices.openUrl(QUrl(update.download_page()))
            return
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking …")
        import threading
        threading.Thread(target=lambda: self.results.put(("update", update.check())), name="update",
                         daemon=True).start()

    def _update_checked(self, c):
        self._update = c
        self.update_btn.setEnabled(True)
        if c.state == "behind":
            self.update_btn.setText("Update and restart")
            self.status.setText("Update available (%d change%s)." % (c.behind, "" if c.behind == 1 else "s"))
        elif c.state == "newer":
            self.update_btn.setText("Open download page")
            self.status.setText("Version %s is available (installed: %s)." % (c.remote_version, __version__))
        else:
            self.update_btn.setText("Check for updates")
            self.status.setText(self.UPDATE_TEXT.get(c.state, c.state))
        log.info("Update-Prüfung: %s", c.state)

    def _update_apply(self):
        from . import update
        if self.running:
            self.toggle()
        if not update.apply():
            self._update = None
            self.update_btn.setText("Check for updates")
            self.status.setText("Update failed (see log).")
            log.warning("Update: Fast-Forward nicht möglich")
            return
        log.info("Update installiert, Neustart")
        if update.restart():
            self.close()
            QApplication.quit()
        else:
            self.status.setText("Update installed – please restart Fog Translate.")

    # ---------------------------------------------------------------- region
    def pick_region(self):
        """Take a still picture of the game (with our own windows out of the way) and mark the chat on it."""
        game = window.find_game()
        if game is None or game.minimized:
            self.status.setText("Open Dead by Daylight first (not minimised), then mark the chat area.")
            return
        self.overlay.hide()
        self.hide()                                    # our window must not be in the picture
        QTimer.singleShot(350, lambda: self._open_picker(game))

    def _open_picker(self, game):
        picture = None
        try:
            from .grab import Grabber
            grabber = Grabber()
            try:
                picture = grabber.grab(game.client)
            finally:
                grabber.close()
        except Exception:
            log.exception("Screenshot for marking failed")
        self.show()
        if picture is None:
            self.status.setText("Could not take a picture of the game (see log).")
            return
        log.info("Marking on a picture of %d x %d", picture.shape[1], picture.shape[0])
        self.picker = RegionPicker(picture, self._picked, self.settings["region"])
        screen = QApplication.primaryScreen().availableGeometry()
        self.picker.start((screen.width(), screen.height()))

    def _picked(self, rel):
        self.picker = None
        if rel is not None:
            self.settings["region"] = list(rel)
            self.settings.save()
            self.engine.new_area()            # also drops waiting pictures of the old size
            self.auto_start_now()
        self._refresh()

    # ---------------------------------------------------------------- loop
    def _start_looper(self):
        """(Re)start the look thread; it builds the translator itself, so the window never waits."""
        self._stop_looper()
        self.engine.starting(NoWorker())
        settings = self.settings
        game = window.find_game()
        log.info("Start: service %s, scale %.2f, game window %s, chat area %s", settings["service"], qtgeom.ratio(),
                 game.client if game else None, self.engine.region_on_screen(game))
        overlay = self.overlay
        self.looper = Looper(self.engine, lambda: services.make(settings), self.results.put, settings["look_s"],
                             own_rects=lambda: [r for r in (overlay.rect_on_screen,) if r])
        self.looper.start()

    def _stop_looper(self, wait: float = 0.0):
        if self.looper is not None:
            self.looper.stop()
            if wait:
                self.looper.join(wait)           # closing: let it end before the program does
            self.looper = None

    def _start_worker(self):            # settings changed while running
        if not self.settings.accepted(self.settings["service"]):
            # another cloud service, or the notice unticked: nothing goes out until it is confirmed
            self.running = False
            self._stop_looper()
            self.engine.status = "unconfirmed"
            self.overlay.hide()
            return
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
                self.status.setText("Please confirm the notice below first.")
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
            if kind == "update":
                self._update_checked(value)
            elif kind == "test":
                self._tested(value)
            elif kind == "tick":
                self.game = value
            elif kind == "started":
                self.engine.started()
            elif kind == "start_failed":
                self.running = False
                self._stop_looper()
                self.engine.failed(value)
            elif kind == "answer":
                if self.engine.answer(value):
                    self._render_history()
                if self.engine.last_counts:
                    log.info("Answer in %(seconds).2f s: %(read)d messages read, %(foreign)d foreign, %(new)d new, "
                             "%(replaced)d replaced", self.engine.last_counts)
                elif hasattr(value, "kind"):
                    log.info("Answer: error %s", value.kind)
                self.settings.save()
        if self.running:
            self._refresh_overlay()
        self._refresh()

    def _refresh_overlay(self):
        box = self.engine.region_on_screen(self.game)
        lines = (self.engine.visible() if self.running and box is not None and not self.overlay_hidden
                 and self.engine.chat_shown() else [])
        if not lines or self.picker is not None:
            self.overlay.hide()
            return
        screen = QApplication.screenAt(self.overlay.geometry().center()) or QApplication.primaryScreen()
        g = screen.geometry()
        area = qtgeom.from_qt((g.x(), g.y(), g.width(), g.height()), qtgeom.ratio())
        self.overlay.show_lines(lines, lambda size: geometry.overlay_spot(box, size, area))

    def _refresh(self):
        e = self.engine
        text = STATUS.get(e.status, e.status) if self.running or e.status not in ("watching", "starting") \
            else STATUS["idle"]
        if not self.running and self.settings["region"] is None:
            text = STATUS["no_region"]
        if e.status == "error":
            text = ERRORS.get(e.error, e.error)
        elif self.running and e.status == "watching":
            from .change import MIN_TEXT_PX
            if e.gate.stats.get("text_px", MIN_TEXT_PX) < MIN_TEXT_PX or not e.gate.stats.get("chat", True):
                text = STATUS["no_chat"]
        now = datetime.now()
        if getattr(self, "_test_until", 0) > now.timestamp():
            text = self._test_text                       # the test's result stays readable for a moment
        self.status.setText(text)
        self.run_btn.setText("Stop" if self.running else "Start")
        self._tray_texts()
        spent = float(self.settings["spent"].get(now.strftime("%Y-%m"), 0.0))
        last = " · last answer %.1f s" % e.last_seconds if e.last_seconds > 0 else ""
        self.costs.setText("Today %d / %d requests · this month about $%.2f (estimated)%s"
                           % (self.settings.requests_today(now.strftime("%Y-%m-%d")), int(self.settings["daily_cap"]),
                              spent, last))

    def closeEvent(self, event):
        if self.settings["close_to_tray"] and self.tray is not None and not self._quitting:
            event.ignore()                               # keep translating; the tray icon brings it back
            self.hide()
            return
        self._stop_looper(wait=2.0)
        self.overlay.close()
        if self.hotkey is not None:
            self.hotkey.stop(QApplication.instance())
        if self.tray is not None:
            self.tray.hide()
        super().closeEvent(event)
        QApplication.instance().quit()


def history_html(lines) -> str:
    """The message list as HTML – every text from the service escaped, so it can only ever be plain text."""
    from html import escape
    parts = []
    for ln in lines:
        head = escape(ln.sender) if ln.sender else "System"
        tag = ('<span style="color:#ffc45c; font-weight:600">%s</span>&nbsp;&nbsp;' % escape(ln.language.upper())
               if ln.translate else "")
        body = escape(ln.translation if ln.translate else ln.text)
        block = ('<div style="margin:0 0 10px 0">%s<span style="color:#8a93a3; font-weight:600">%s</span><br>'
                 '<span style="font-size:15px">%s</span>' % (tag, head, body))
        if ln.translate and ln.translation != ln.text:
            block += '<br><span style="color:#8a8f99; font-size:12px">%s</span>' % escape(ln.text)
        parts.append(block + "</div>")
    return "".join(parts)


def run(argv=None) -> int:
    import os
    # Qt coordinates = physical pixels, like the Win32 window rectangles and mss
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    from . import icon
    icon.set_app_id()
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setWindowIcon(icon.icon())
    settings = Settings()
    app.setQuitOnLastWindowClosed(False)                 # the window may hide to the tray; closeEvent quits
    win = MainWindow(settings)
    win.setup_tray(app)
    if win.setup_hotkey(app):
        log.info("Hotkey %s hides/shows the translations", settings["hide_hotkey"])
    win.show()
    from . import wizard
    if wizard.wanted(settings):
        win.open_setup()
    else:
        win.auto_start_now()
    return app.exec()
