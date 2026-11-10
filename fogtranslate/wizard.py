"""The setup assistant shown at the first start: choose a service, enter and test its API key, confirm the notice.

Three short pages in an ordinary window. Keys are stored the same way as from the main window (encrypted with
DPAPI, ``Settings.set_api_key``); "Test" sends only the made-up sample chat (``translate.sample_picture``).
Skipping is always possible – everything can be set later in the main window.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QRadioButton, QStackedWidget, QVBoxLayout, QWidget)

from . import services, translate

log = logging.getLogger(__name__)

ABOUT = {
    "claude": "Best at slang and difficult scripts. Needs a paid API key; with the "
              "recommended model a request costs a fraction of a cent.",
    "gemini": "Has a free tier: a free API key from Google AI Studio is enough. On the free tier "
              "Google may use the pictures to improve its products.",
    "ollama": "Free, nothing leaves your PC. Needs Ollama installed, a vision model pulled and a "
              "graphics card with about 8 GB.",
}
NOTICE = {
    "claude": "The picture of the marked chat area (it can show player names and other players' messages) is sent "
              "to Anthropic – with your own API key, at your own cost.",
    "gemini": "The picture of the marked chat area (it can show player names and other players' messages) is sent "
              "to Google. On the free tier Google may use it to improve its products, and humans may read it.",
}
ERRORS = {
    "key": "The API key is missing or not valid.",
    "quota": "The service reports a limit or no credit.",
    "net": "No connection to the service.",
    "model": "Model not found.",
    "server": "Ollama is not running.",
    "refused": "The service declined the test.",
    "answer": "The service's answer could not be read.",
    "other": "Unexpected error (see log).",
}


def wanted(settings) -> bool:
    """Show the assistant at start: never finished or skipped, and nothing is set up yet."""
    if settings["setup_done"]:
        return False
    has_key = any(settings.has_stored_key(s) for s in services.KEY_SETTING)
    return not has_key and settings["region"] is None


class SetupWizard(QWidget):
    def __init__(self, settings, done=None, make=None):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Fog Translate – setup")
        self.settings = settings
        self._done = done or (lambda: None)
        self._make = make or services.make            # injectable for tests
        self._finished = False
        self._results: queue.Queue = queue.Queue()
        self._timer = QTimer(self, interval=150, timeout=self._pump)
        self.pages = QStackedWidget()
        self.pages.addWidget(self._page_service())
        self.pages.addWidget(self._page_key())
        self.pages.addWidget(self._page_finish())

        self.back_btn = QPushButton("Back", clicked=self.back)
        self.next_btn = QPushButton("Next", clicked=self.next)
        self.next_btn.setDefault(True)
        self.skip_btn = QPushButton("Skip setup", clicked=self.skip)
        buttons = QHBoxLayout()
        buttons.addWidget(self.skip_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.back_btn)
        buttons.addWidget(self.next_btn)
        root = QVBoxLayout(self)
        root.addWidget(self.pages, 1)
        root.addLayout(buttons)
        self.resize(560, 420)
        self._show_page(0)

    # ---------------------------------------------------------------- pages
    def _title(self, text):
        label = QLabel("<b style='font-size:16px'>%s</b>" % text)
        label.setTextFormat(Qt.TextFormat.RichText)
        return label

    def _page_service(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(self._title("1 of 3 · Which translation service?"))
        intro = QLabel("Fog Translate sends a picture of the chat to a service that reads and translates it. "
                       "Choose one – you can change it any time.")
        intro.setWordWrap(True)
        box.addWidget(intro)
        self.group = QButtonGroup(self)
        self.radios = {}
        for sid, (label, _cloud) in services.SERVICES.items():
            radio = QRadioButton(label)
            radio.setChecked(sid == self.settings["service"])
            self.group.addButton(radio)
            self.radios[sid] = radio
            box.addWidget(radio)
            about = QLabel(ABOUT[sid])
            about.setWordWrap(True)
            about.setContentsMargins(22, 0, 0, 8)
            box.addWidget(about)
        lang = QHBoxLayout()
        lang.addWidget(QLabel("Translate to:"))
        self.target = QComboBox()
        self.target.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for code, name in translate.LANGUAGES.items():
            self.target.addItem("%s (%s)" % (name, code.upper()), code)
        self.target.setCurrentIndex(list(translate.LANGUAGES).index(self.settings["target"]))
        lang.addWidget(self.target)
        lang.addStretch(1)
        box.addLayout(lang)
        box.addStretch(1)
        return page

    def _page_key(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.key_title = self._title("")
        box.addWidget(self.key_title)
        self.key_help = QLabel()
        self.key_help.setWordWrap(True)
        self.key_help.setOpenExternalLinks(True)
        self.key_help.setTextFormat(Qt.TextFormat.RichText)
        box.addWidget(self.key_help)
        row = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("Paste your API key")
        self.test_btn = QPushButton("Test", clicked=self.test)
        row.addWidget(self.key, 1)
        row.addWidget(self.test_btn)
        box.addLayout(row)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        box.addWidget(self.notice)
        self.accept = QCheckBox("I understand")
        self.accept.toggled.connect(lambda _on: self._buttons())
        box.addWidget(self.accept)
        self.result = QLabel()
        self.result.setWordWrap(True)
        box.addWidget(self.result)
        box.addStretch(1)
        return page

    def _page_finish(self):
        page = QWidget()
        box = QVBoxLayout(page)
        box.addWidget(self._title("3 of 3 · Almost done"))
        text = QLabel("Three steps are left, in the main window:<br><br>"
                      "<b>1.</b> Open Dead by Daylight and go to a lobby where the chat is visible.<br>"
                      "<b>2.</b> Click <b>Mark chat area</b>, drag a box around the whole chat and click <b>Save</b>.<br>"
                      "<b>3.</b> Click <b>Start</b>.<br><br>"
                      "Translations appear above the chat. Ctrl+Alt+T hides and shows them.")
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setWordWrap(True)
        box.addWidget(text)
        box.addStretch(1)
        return page

    # ---------------------------------------------------------------- flow
    def service(self) -> str:
        return next(sid for sid, radio in self.radios.items() if radio.isChecked())

    def _show_page(self, index: int):
        self.pages.setCurrentIndex(index)
        if index == 1:
            self._fill_key_page()
        self._buttons()

    def _fill_key_page(self):
        service = self.service()
        cloud = services.is_cloud(service)
        name = services.SERVICES[service][0]
        self.key_title.setText("<b style='font-size:16px'>2 of 3 · %s</b>" % ("API key for " + name if cloud else name))
        if cloud:
            url = services.KEY_URL[service]
            stored = self.settings.has_stored_key(service)
            self.key_help.setText('Get a key here: <a href="%s">%s</a><br>It is stored encrypted on this PC '
                                  '(Windows DPAPI) and only ever sent to this service.%s'
                                  % (url, url, "<br><b>A key is already saved</b> – leave the field empty to keep it."
                                     if stored else ""))
            self.notice.setText(NOTICE[service])
        else:
            self.key_help.setText('Install Ollama from <a href="https://ollama.com">ollama.com</a>, then run '
                                  '<code>ollama pull %s</code> in a command prompt. No key is needed.'
                                  % self.settings["ollama_model"])
            self.notice.setText("Nothing leaves your PC with Ollama.")
        self.key.setVisible(cloud)
        self.accept.setVisible(cloud)
        self.accept.setChecked(self.settings.accepted(service) if cloud else True)
        self.result.setText("")

    def _buttons(self):
        index = self.pages.currentIndex()
        self.back_btn.setEnabled(index > 0)
        self.next_btn.setText("Finish" if index == 2 else "Next")
        ok = True
        if index == 1 and services.is_cloud(self.service()):
            ok = self.accept.isChecked()
        self.next_btn.setEnabled(ok)
        self.test_btn.setEnabled(ok)

    def _store(self) -> bool:
        """Take what the pages show into the settings. True unless a cloud service still has no key."""
        s = self.settings
        service = self.service()
        s["service"] = service
        s["target"] = self.target.currentData()
        if services.is_cloud(service):
            s.set_accepted(service, self.accept.isChecked())
            text = self.key.text().strip()
            if text:
                s.set_api_key(service, text)
                self.key.clear()
                self.key.setPlaceholderText("saved")
        s.save()
        return not services.is_cloud(service) or bool(s.api_key(service))

    def next(self):
        index = self.pages.currentIndex()
        if index == 0:
            self.settings["service"] = self.service()
            self._show_page(1)
        elif index == 1:
            if not self._store():
                self.result.setText("Please paste an API key first – or use “Skip setup” and add it later.")
                return
            self._show_page(2)
        else:
            self._end()

    def back(self):
        self._show_page(max(0, self.pages.currentIndex() - 1))

    def skip(self):
        self._end()

    def _end(self):
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        self.settings["setup_done"] = True
        self.settings.save()
        self.close()
        self._done()

    def closeEvent(self, event):
        if not self._finished:                         # closed with ×: like "Skip setup"
            self._finished = True
            self._timer.stop()
            self.settings["setup_done"] = True
            self.settings.save()
            self._done()
        super().closeEvent(event)

    # ---------------------------------------------------------------- test
    def test(self):
        if not self._store():
            self.result.setText("Please paste an API key first.")
            return
        self.test_btn.setEnabled(False)
        self.result.setText("Testing …")
        settings, make, put = self.settings, self._make, self._results.put

        def work():
            t0 = time.monotonic()
            try:
                result = make(settings).request(translate.sample_picture())
                put((len(result.lines), time.monotonic() - t0, result.cost_usd))
            except translate.TranslateError as e:
                put(e)
            except Exception as e:
                log.exception("Setup test failed")
                put(translate.TranslateError("other", type(e).__name__))

        threading.Thread(target=work, name="setup-test", daemon=True).start()
        self._timer.start()

    def _pump(self):
        try:
            outcome = self._results.get_nowait()
        except queue.Empty:
            return
        self._timer.stop()
        if isinstance(outcome, translate.TranslateError):
            self.result.setText("<b>Test failed:</b> " + ERRORS.get(outcome.kind, outcome.kind))
        else:
            read, seconds, _cost = outcome
            self.result.setText("<b>It works.</b> %d of 3 sample messages read in %.1f s." % (min(3, read), seconds))
        self._buttons()
