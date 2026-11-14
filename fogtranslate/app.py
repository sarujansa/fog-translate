"""Control window and the Qt side of the loop."""
from __future__ import annotations

import logging
import queue
import sys
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from . import __version__, geometry, i18n, ollama, qtgeom, services, theme, translate, window
from .config import Settings
from .engine import Engine
from .lines import ChatLine
from .i18n import N_, tr
from .looper import Looper
from .overlay import TranslationOverlay
from .picker import RegionPicker
from .statusview import HINTS, STATUS, View, view
from .updateflow import UpdateFlow

log = logging.getLogger(__name__)

ERRORS, NOTICES = services.ERRORS, services.NOTICES


DOT = {"off": "#8a8f99", "on": "#3fb950", "wait": "#d29922", "bad": "#e5534b"}     # stopped, working, waiting, error
# the button for the next step stands out (white on this blue: contrast 4.6)
NEXT_STYLE = ("QPushButton { background: #2f6fdb; color: #ffffff; border: 2px solid #2f6fdb; border-radius: 4px; "
              "padding: 4px 16px; font-weight: 600; } "
              "QPushButton:hover { background: #3d7cea; border-color: #3d7cea; } "
              "QPushButton:pressed { background: #2559b3; border-color: #2559b3; } "
              "QPushButton:focus { border-color: #b9d2ff; }")


THEME_LABELS = {"auto": N_("Automatic (Windows)"), "light": N_("Light"), "dark": N_("Dark")}
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


class MainWindow(UpdateFlow, QWidget):
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
        self._init_update_state()
        self.overlay_hidden = False  # hotkey / tray: translations hidden until toggled again
        self.tray = None
        self.hotkey = None
        self._quitting = False
        self._preview_until = 0.0    # a made-up translation is on screen until then ("Preview")
        self._preview_box = None
        self._preview_place = None   # the place the user chose, on screen, when the preview began
        self._start_after_pick = False   # Start was clicked without a chat area: start once it is marked
        self._build()
        self.resize(560, 560)
        self.pump_timer = QTimer(self, interval=200, timeout=self._pump)
        self.pump_timer.start()
        self._refresh()

    # ---------------------------------------------------------------- UI
    def _build(self):
        """The window's contents, all made from the settings (built again on a language or theme change)."""
        root = QVBoxLayout(self)
        self._build_head(root)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.tabs.addTab(self._translations_tab(), tr("Translations"))
        self.service_tab = self._service_tab()
        self.tabs.addTab(self.service_tab, tr("Service"))
        self.tabs.addTab(self._options_tab(), tr("Options"))
        self._build_bottom(root)
        self._update_button()
        self._service_ui()

    def _build_head(self, root):
        """Status with its dot, the hint with "Show me", Start and "Mark chat area"."""
        head = QHBoxLayout()
        self.dot = QLabel()
        self.dot.setFixedSize(12, 12)
        head.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status = QLabel()
        self.status.setWordWrap(True)
        font = self.status.font()
        font.setPointSizeF(font.pointSizeF() * 1.2)
        font.setBold(True)
        self.status.setFont(font)
        head.addWidget(self.status, 1)
        root.addLayout(head)
        hint_row = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        hint_row.addWidget(self.hint, 1)
        self.hint_btn = QPushButton(tr("Show me"), clicked=self._hint_clicked)
        self.hint.setMinimumHeight(self.hint_btn.sizeHint().height())
        hint_row.addWidget(self.hint_btn)
        root.addLayout(hint_row)
        self._hint_step = ""
        self._looks = {}             # widget → style last set (set only when it changes)

        row = QHBoxLayout()
        self.run_btn = QPushButton(tr("Start"), clicked=self.toggle)
        self.run_btn.setMinimumHeight(36)
        self.pick_btn = QPushButton(tr("Mark chat area"), clicked=self.pick_region)
        self.pick_btn.setMinimumHeight(36)
        row.addWidget(self.run_btn, 2)
        row.addWidget(self.pick_btn, 1)
        root.addLayout(row)

    def _translations_tab(self):
        """Tab 1: what was translated."""
        page = QWidget()
        box = QVBoxLayout(page)
        self.history = QTextBrowser()
        self.history.setOpenLinks(False)
        self.history.setPlaceholderText(tr("Translated messages appear here."))
        box.addWidget(self.history, 1)
        under = QHBoxLayout()
        under.addStretch(1)
        self.shot_btn = QPushButton(tr("Show last capture"), clicked=self.show_last_picture)
        under.addWidget(self.shot_btn)
        box.addLayout(under)
        return page

    def _service_tab(self):
        """Tab 2: the service and what it needs."""
        s = self.settings
        page = QWidget()
        box = QVBoxLayout(page)
        grid = QGridLayout()
        grid.addWidget(QLabel(tr("Translate to:")), 0, 0)
        self.target = QComboBox()
        for code in translate.LANGUAGES:
            self.target.addItem("%s (%s)" % (tr(translate.LANGUAGES[code]), code.upper()), code)
        self.target.setCurrentIndex(list(translate.LANGUAGES).index(s["target"]))
        self.target.currentIndexChanged.connect(self._settings_changed)
        grid.addWidget(self.target, 0, 1)
        grid.addWidget(QLabel(tr("Service:")), 1, 0)
        self.service = QComboBox()
        for sid, (label, _cloud) in services.SERVICES.items():
            self.service.addItem(tr(label), sid)
        self.service.setCurrentIndex(list(services.SERVICES).index(s["service"]))
        self.service.currentIndexChanged.connect(self._service_changed)
        grid.addWidget(self.service, 1, 1)
        grid.addWidget(QLabel(tr("Model:")), 2, 0)
        model_row = QHBoxLayout()
        self.model = QComboBox()
        self.model.activated.connect(self._settings_changed)
        self._edit_hooked = None
        model_row.addWidget(self.model, 1)
        self.local_btn = QPushButton(tr("Load local models"), clicked=self._load_local_models)
        model_row.addWidget(self.local_btn)
        grid.addLayout(model_row, 2, 1)
        self.key_label = QLabel(tr("API key:"))
        grid.addWidget(self.key_label, 3, 0)
        key_row = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.returnPressed.connect(self._save_key)
        key_row.addWidget(self.key)
        self.key_btn = QPushButton(tr("Save"), clicked=self._save_key)
        key_row.addWidget(self.key_btn)
        grid.addLayout(key_row, 3, 1)
        self.key_link = QLabel()
        self.key_link.setOpenExternalLinks(True)
        self.key_link.setTextFormat(Qt.TextFormat.RichText)
        grid.addWidget(self.key_link, 4, 1)
        grid.addWidget(QLabel(tr("Daily limit:")), 5, 0)
        limit_row = QHBoxLayout()
        self.daily_cap = NoWheelSpinBox()
        self.daily_cap.setRange(MIN_CAP, MAX_CAP)
        self.daily_cap.setSingleStep(50)
        self.daily_cap.setSuffix(tr(" requests per day"))
        self.daily_cap.setValue(int(s["daily_cap"]))
        self.daily_cap.valueChanged.connect(self._cap_changed)
        limit_row.addWidget(self.daily_cap)
        limit_row.addStretch(1)
        grid.addLayout(limit_row, 5, 1)
        grid.setColumnStretch(1, 1)
        box.addLayout(grid)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        box.addWidget(self.notice)
        self.accept = QCheckBox(tr("I understand"))
        self.accept.toggled.connect(self._settings_changed)
        box.addWidget(self.accept)
        test_row = QHBoxLayout()
        self.test_btn = QPushButton(tr("Test service"), clicked=self.test_service)
        test_row.addWidget(self.test_btn)
        test_row.addStretch(1)
        box.addLayout(test_row)
        box.addStretch(1)
        return page

    def _options_tab(self):
        """Tab 3: everything that is set once."""
        s = self.settings
        page = QWidget()
        box = QVBoxLayout(page)
        group = QGroupBox(tr("Translation window"))
        inner = QVBoxLayout(group)
        look_row = QHBoxLayout()
        self.font_px = NoWheelSpinBox()
        self.font_px.setRange(10, 48)
        self.font_px.setPrefix(tr("text size "))
        self.font_px.setSuffix(tr(" px"))
        self.font_px.setValue(int(s["font_px"]))
        self.font_px.valueChanged.connect(self._look_changed)
        self.show_s = NoWheelSpinBox()
        self.show_s.setRange(3, 600)
        self.show_s.setSingleStep(5)
        self.show_s.setPrefix(tr("show for "))
        self.show_s.setSuffix(tr(" s"))
        self.show_s.setValue(int(float(s["show_s"])))
        self.show_s.valueChanged.connect(self._look_changed)
        self.preview_btn = QPushButton(tr("Preview"), clicked=self.preview_overlay)
        look_row.addWidget(self.font_px)
        look_row.addWidget(self.show_s)
        look_row.addWidget(self.preview_btn)
        look_row.addStretch(1)
        inner.addLayout(look_row)
        place_row = QHBoxLayout()
        self.place_btn = QPushButton(tr("Choose position"), clicked=self.pick_spot)
        self.unplace_btn = QPushButton(tr("Reset position"), clicked=self.reset_spot)
        self.unplace_btn.setEnabled(s["overlay_spot"] is not None)
        place_row.addWidget(self.place_btn)
        place_row.addWidget(self.unplace_btn)
        place_row.addStretch(1)
        inner.addLayout(place_row)
        self.only_chat = QCheckBox(tr("Show translations only while the chat is visible"))
        self.only_chat.setChecked(bool(s["hide_without_chat"]))
        self.only_chat.toggled.connect(self._auto_changed)
        inner.addWidget(self.only_chat)
        self.show_all = QCheckBox(tr("Also show messages already in my language"))
        self.show_all.setChecked(bool(s["show_all"]))
        self.show_all.toggled.connect(self._settings_changed)
        inner.addWidget(self.show_all)
        self.hide_caps = QCheckBox(tr("Hide the translation in screenshots and recordings"))
        self.hide_caps.setChecked(bool(s["hide_in_captures"]))
        self.hide_caps.toggled.connect(self._settings_changed)
        inner.addWidget(self.hide_caps)
        if s["hide_hotkey"]:
            inner.addWidget(QLabel(tr("%s hides and shows the translations.") % s["hide_hotkey"]))
        box.addWidget(group)
        group = QGroupBox(tr("Program"))
        inner = QVBoxLayout(group)
        self.auto_start = QCheckBox(tr("Start automatically when Fog Translate opens"))
        self.auto_start.setChecked(bool(s["auto_start"]))
        self.auto_start.toggled.connect(self._auto_changed)
        inner.addWidget(self.auto_start)
        self.background = QCheckBox(tr("Also read while DBD is in the background (only while no window covers the chat)"))
        self.background.setChecked(bool(s["read_background"]))
        self.background.toggled.connect(self._settings_changed)
        inner.addWidget(self.background)
        self.to_tray = QCheckBox(tr("Keep running in the tray when I close the window"))
        self.to_tray.setChecked(bool(s["close_to_tray"]))
        self.to_tray.toggled.connect(self._settings_changed)
        inner.addWidget(self.to_tray)
        ui_row = QHBoxLayout()
        self.language = QComboBox()
        self.language.addItem(tr("Automatic (Windows)"), "auto")
        for code, name in i18n.LANGS.items():
            self.language.addItem(name, code)
        self.language.setCurrentIndex(max(0, self.language.findData(s["ui_language"])))
        self.language.activated.connect(self._language_changed)
        self.theme = QComboBox()
        for name, label in THEME_LABELS.items():
            self.theme.addItem(tr(label), name)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s["theme"])))
        self.theme.activated.connect(self._theme_changed)
        ui_row.addWidget(QLabel(tr("Language:")))
        ui_row.addWidget(self.language)
        ui_row.addWidget(QLabel(tr("Appearance:")))
        ui_row.addWidget(self.theme)
        ui_row.addStretch(1)
        inner.addLayout(ui_row)
        box.addWidget(group)
        last = QHBoxLayout()
        self.setup_btn = QPushButton(tr("Setup assistant"), clicked=self.open_setup)
        last.addWidget(self.setup_btn)
        last.addStretch(1)
        box.addLayout(last)
        box.addStretch(1)
        return page

    def _build_bottom(self, root):
        """Costs and the update button."""
        bottom = QHBoxLayout()
        self.costs = QLabel()
        bottom.addWidget(self.costs, 1)
        self.update_btn = QPushButton("", clicked=self.update_clicked)
        bottom.addWidget(self.update_btn)
        root.addLayout(bottom)

    def _language_changed(self, _index=None):
        """Another language: build the window's contents again (they are all made from the settings)."""
        code = self.language.currentData()
        if code == self.settings["ui_language"]:
            return
        self.settings["ui_language"] = code
        self.settings.save()
        i18n.set_language(code)
        self.rebuild()

    def rebuild(self):
        tab = self.tabs.currentIndex()
        QWidget().setLayout(self.layout())             # the old layout and its widgets go with this temporary parent
        self._build()
        self.tabs.setCurrentIndex(tab)                 # the language is chosen on a tab: stay there
        self.setWindowTitle("Fog Translate " + __version__)
        if self.tray is not None:
            self._act_window.setText(tr("Show window"))
            self._act_quit.setText(tr("Quit"))
        self._render_history()
        self._refresh()

    def _theme_changed(self, _index=None):
        self.settings["theme"] = self.theme.currentData()
        self.settings.save()
        theme.apply(QApplication.instance(), self.settings["theme"])
        # texts with a link keep the link colour they were made with (a pale link on white after dark → light,
        # Saru 11.11.2026): build the contents again, as for another language; the list's colours follow too
        self.rebuild()

    def _auto_changed(self, _on=None):
        """Neither box changes what is sent, so the look thread keeps running."""
        self.settings["auto_start"] = self.auto_start.isChecked()
        self.settings["hide_without_chat"] = self.only_chat.isChecked()
        self.settings.save()
        if self.running:
            self._refresh_overlay()

    def can_auto_start(self) -> bool:
        """Start by itself only when a click on Start would work: area marked, notice confirmed, key there."""
        return bool(self.settings["auto_start"] and not self.running and not self.next_step())

    def next_step(self) -> str:
        """What Start still needs: "notice" (not confirmed), "key" (none there), "region" (not marked) or ""."""
        s = self.settings
        service = s["service"]
        if not s.accepted(service):
            return "notice"
        if services.is_cloud(service) and not s.has_key(service):
            return "key"
        if s["region"] is None:
            return "region"
        return ""

    def _go(self, step: str):
        """Bring the place where ``step`` is done to the front."""
        if step == "region":
            self.pick_region()
            return
        self.tabs.setCurrentWidget(self.service_tab)
        {"notice": self.accept, "key": self.key, "cap": self.daily_cap}[step].setFocus()

    def _guide(self, step: str):
        """Start or the test cannot work yet: show where the missing step is done, and say what it is."""
        self._go(step)
        if step == "notice":
            self._say(tr("Please confirm the notice for this service first."))
        elif step == "key":
            self._say(tr("Please paste an API key first."))

    def _hint_clicked(self):
        if self._hint_step:
            self._go(self._hint_step)

    def _take_typed_key(self):
        """A key typed but not saved yet is saved before it is needed (Start, test)."""
        if self.key.text().strip():
            self._save_key()

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
        changed = self.overlay.font_main.pixelSize() != self.settings["font_px"]
        self.overlay.set_font_px(self.settings["font_px"])
        if changed and self.isVisible():
            self.preview_overlay(3.0)                  # the new size is seen at once, with or without the game
        elif self.running:
            self._refresh_overlay()

    def preview_overlay(self, seconds: float = 6.0):
        """Show a made-up translation where the real ones appear – in the middle of the screen without the game or
        a marked area. Nothing is read or sent for it."""
        game = window.find_game()
        box = self.engine.region_on_screen(game) if game is not None and not game.minimized else None
        if box is None:
            g = QApplication.primaryScreen().geometry()
            x, y, w, h = qtgeom.from_qt((g.x(), g.y(), g.width(), g.height()), qtgeom.ratio())
            box = (x + w // 3, y + h // 2, w // 3, 1)
        self._preview_box = box
        self._preview_place = self._spot_on_screen(game) if game is not None and not game.minimized else None
        self._preview_until = time.monotonic() + seconds
        self._refresh_overlay()

    # ---------------------------------------------------------------- test, tray, hotkey
    def test_service(self):
        """One request with a made-up chat picture: shows whether key, model and service work, and how fast."""
        self._take_typed_key()
        service = self.settings["service"]
        step = self.next_step()
        if step in ("notice", "key"):                  # the test needs no chat area
            self._guide(step)
            return
        self.test_btn.setEnabled(False)
        self._say(tr("Testing %s …") % tr(services.SERVICES[service][0]), 120)
        settings, put = self.settings, self.results.put
        import threading
        threading.Thread(target=lambda: put(("test", services.test_request(settings))), name="test",
                         daemon=True).start()

    def _tested(self, outcome):
        self.test_btn.setEnabled(True)
        services.count_test(self.settings, outcome)
        if isinstance(outcome, translate.TranslateError):
            self._test_text = tr("Test failed: %s") % tr(ERRORS.get(outcome.kind, outcome.kind))
        else:
            self._test_text = (tr("Test OK – %d of 3 messages read in %.1f s.")
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
        self._act_window = QAction(tr("Show window"), menu, triggered=self.show_window)
        self._act_run = QAction(tr("Start"), menu, triggered=self.toggle)
        self._act_overlay = QAction(tr("Hide translations"), menu, triggered=self.toggle_overlay)
        self._act_quit = QAction(tr("Quit"), menu, triggered=self.quit)
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
        self._act_run.setText(tr("Stop") if self.running else tr("Start"))
        self._act_overlay.setText(tr("Show translations") if self.overlay_hidden else tr("Hide translations"))

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
        self.wizard = SetupWizard(self.settings, self._setup_done, relang=self.rebuild)
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
        self.tabs.setCurrentIndex(0)
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
            self.model.addItem(tr(label), mid)
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
        self.key.setPlaceholderText(tr("saved") if s.has_stored_key(service) else tr("Paste API key"))
        if cloud:
            url = services.KEY_URL[service]
            self.key_link.setText('%s <a href="%s">%s</a>' % (tr("Get a key:"), url, url))
        self.notice.setText(tr(NOTICES[service]))
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
        """Ask the local Ollama for its models – in a thread (up to 5 s without a server; 0.12: the window froze)."""
        port, put = int(self.settings["ollama_port"]), self.results.put
        self.local_btn.setEnabled(False)
        import threading
        threading.Thread(target=lambda: put(("models", ollama.installed_models(port))), name="models",
                         daemon=True).start()

    def _local_models_loaded(self, names):
        self.local_btn.setEnabled(True)
        if not names:
            self._say(tr(ERRORS["server"]) + " " + tr("Or no model pulled yet."))
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
        self._say(tr("%d local models found.") % len(names))

    def _save_key(self):
        text = self.key.text().strip()
        service = self.settings["service"]
        if not text or not services.is_cloud(service):
            return
        stored = self.settings.set_api_key(service, text)
        self.key.clear()
        self.key.setPlaceholderText(tr("saved") if stored else tr("for this session only"))
        if self.running:
            self._start_worker()
        self._refresh()

    def show_last_picture(self):
        """The picture last sent to the service, exactly as cut out (only in memory, never a file)."""
        img = self.engine.last_sent
        if img is None:
            self._say(tr("Nothing sent yet – start first and wait for chat messages."))
            return
        from PySide6.QtGui import QImage, QPixmap
        import numpy as np
        rgb = np.ascontiguousarray(np.asarray(img)[..., 2::-1])
        h, w = rgb.shape[:2]
        pic = QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())
        view = QLabel()
        view.setWindowTitle(tr("Sent capture – %d × %d px") % (w, h))
        view.setPixmap(pic)
        view.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._picture_view = view
        view.show()

    def _render_history(self):
        bar = self.history.verticalScrollBar()
        at_end = bar.value() >= bar.maximum() - 4
        self.history.setHtml(history_html(self.engine.messages()[-100:],
                                          theme.history_colours(QApplication.instance())))
        if at_end:
            bar.setValue(bar.maximum())

    def _say(self, text: str, seconds: float = 15.0):
        """A message in the status line that stays readable for a moment (the line is rewritten 5× a second)."""
        self._test_text = text
        self._test_until = datetime.now().timestamp() + seconds
        self.status.setText(text)

    # ---------------------------------------------------------------- region
    def pick_region(self):
        """Take a still picture of the game (with our own windows out of the way) and mark the chat on it."""
        game = window.find_game()
        if game is None or game.minimized:
            self._start_after_pick = False
            self._say(tr("Open Dead by Daylight first (not minimised), then mark the chat area."))
            return
        self.overlay.hide()
        self.hide()                                    # our window must not be in the picture
        QTimer.singleShot(350, lambda: self._open_picker(game))

    def pick_spot(self):
        """Choose where the translations appear – on a still picture like the chat area: the translation window
        lets every click through, and over the game a window of ours gets no clicks, so it cannot be dragged."""
        game = window.find_game()
        if game is None or game.minimized:
            self._say(tr("Open Dead by Daylight first (not minimised), then choose the position."))
            return
        self._preview_until = 0.0
        self.overlay.hide()
        self.hide()
        QTimer.singleShot(350, lambda: self._open_picker(game, spot=True))

    def _spot_picked(self, rel):
        self.picker = None
        region = self.settings["region"]
        if rel is not None and region is not None and geometry.touches(rel, region):
            # the program never reads its own window: chat lines under it would be lost
            self._say(tr("That place covers the chat area – choose one next to it."))
        elif rel is not None:
            self.settings["overlay_spot"] = list(rel)
            self.settings.save()
            self.unplace_btn.setEnabled(True)
            self.preview_overlay()                     # show where they will be
        self._refresh()

    def reset_spot(self):
        """Back to the place right above the chat."""
        self.settings["overlay_spot"] = None
        self.settings.save()
        self.unplace_btn.setEnabled(False)
        self.preview_overlay()

    def _spot_on_screen(self, game):
        """The chosen place as a screen box, or None (none chosen, no game)."""
        rel = self.settings["overlay_spot"]
        if rel is None or game is None:
            return None
        cx, cy, cw, ch = game.client
        x, y, w, h = geometry.from_relative(rel, geometry.window_space(cw, ch))
        return cx + x, cy + y, w, h

    def _open_picker(self, game, spot=False):
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
            self._start_after_pick = False
            self._say(tr("Could not take a picture of the game (see log)."))
            return
        log.info("Marking on a picture of %d x %d", picture.shape[1], picture.shape[0])
        if spot:
            self.picker = RegionPicker(
                picture, self._spot_picked, self.settings["overlay_spot"], tr("Position of the translations"),
                tr("Drag a box where the translations should appear – they start at its top left corner. "
                   "Not on the chat itself. Then click Save."))
        else:
            self.picker = RegionPicker(picture, self._picked, self.settings["region"])
        screen = QApplication.primaryScreen().availableGeometry()
        self.picker.start((screen.width(), screen.height()))

    def _picked(self, rel):
        self.picker = None
        asked, self._start_after_pick = self._start_after_pick, False
        if rel is not None:
            self.settings["region"] = list(rel)
            self.settings.save()
            self.engine.new_area()            # also drops waiting pictures of the old size
            if asked and not self.running:
                self.toggle()                 # Start was what the user clicked
            else:
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
            self._take_typed_key()
            step = self.next_step()
            if step:                              # not ready: lead to the missing step instead of a start that fails
                self._start_after_pick = step == "region"
                self._guide(step)
                return
            self._test_until = 0                  # an earlier message makes way for the status
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
            elif kind == "release":
                self._release_checked(value)
            elif kind == "downloaded":
                self._release_downloaded(value)
            elif kind == "test":
                self._tested(value)
            elif kind == "models":
                self._local_models_loaded(value)
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
        if self._update_note[0] and self._update_note[1] <= time.monotonic():
            self._update_note = ("", 0.0)
            self._update_button()                      # back to "Check for updates"
        preview_over = bool(self._preview_until) and self._preview_until <= time.monotonic()
        if preview_over:
            self._preview_until = 0.0
        if self.running or self._preview_until or preview_over:
            self._refresh_overlay()
        self._refresh()

    def _refresh_overlay(self):
        box = self.engine.region_on_screen(self.game)
        lines = (self.engine.visible() if self.running and box is not None and not self.overlay_hidden
                 and self.engine.chat_shown() else [])
        place = self._spot_on_screen(self.game)
        if not lines and self._preview_until > time.monotonic():      # real translations come first
            lines, box, place = preview_lines(), self._preview_box, self._preview_place
        if not lines or self.picker is not None:
            self.overlay.hide()
            return
        screen = QApplication.screenAt(self.overlay.geometry().center()) or QApplication.primaryScreen()
        g = screen.geometry()
        area = qtgeom.from_qt((g.x(), g.y(), g.width(), g.height()), qtgeom.ratio())
        if place is not None:
            self.overlay.show_lines(lines, lambda size: geometry.placed_spot(place, size, area))
        else:
            self.overlay.show_lines(lines, lambda size: geometry.overlay_spot(box, size, area))

    def _refresh(self):
        e = self.engine
        from .change import MIN_TEXT_PX
        no_text = (e.gate.stats.get("text_px", MIN_TEXT_PX) < MIN_TEXT_PX or not e.gate.stats.get("chat", True))
        v: View = view(e.status, e.error, self.running, "" if self.running else self.next_step(), no_text)
        text = tr(ERRORS.get(e.error, e.error)) if v.error else tr(STATUS.get(v.status, v.status))
        now = datetime.now()
        if getattr(self, "_test_until", 0) > now.timestamp():
            text = self._test_text                       # the test's result stays readable for a moment
        self.status.setText(text)
        self.run_btn.setText(tr("Stop") if self.running else tr("Start"))
        step, look, goal = v.step, v.look, v.goal
        hint = tr(HINTS[v.hint]) if v.hint else ""
        if look == "on" and self.settings["hide_hotkey"]:
            hint += " " + tr("%s hides and shows the translations.") % self.settings["hide_hotkey"]
        self.hint.setText(hint)
        self._hint_step = goal
        self.hint_btn.setVisible(bool(goal))
        self._look(self.dot, "background: %s; border-radius: 6px;" % DOT[look])
        self._look(self.pick_btn, NEXT_STYLE if step == "region" else "")
        self._look(self.run_btn, NEXT_STYLE if not self.running and not step else "")
        self._tray_texts()
        spent = float(self.settings["spent"].get(now.strftime("%Y-%m"), 0.0))
        last = " · " + tr("last answer %.1f s") % e.last_seconds if e.last_seconds > 0 else ""
        self.costs.setText((tr("Today %d / %d requests · this month about $%.2f (estimated)") + "%s")
                           % (self.settings.requests_today(now.strftime("%Y-%m-%d")), int(self.settings["daily_cap"]),
                              spent, last))

    def _look(self, widget, style: str):
        if self._looks.get(widget) != style:
            self._looks[widget] = style
            widget.setStyleSheet(style)

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


def preview_lines() -> list:
    """What "Preview" shows: one made-up message, laid out like a real one."""
    return [ChatLine("Fog Translate", "Так выглядит перевод.", "ru", tr("This is how a translation looks."), True)]


def history_html(lines, colours=theme.HISTORY[True]) -> str:
    """The message list as HTML – every text from the service escaped, so it can only ever be plain text.
    ``colours`` = (language tag, sender, original) for the window's look."""
    from html import escape
    c_tag, c_sender, c_original = colours
    parts = []
    for ln in lines:
        head = escape(ln.sender) if ln.sender else tr("System")
        tag = ('<span style="color:%s; font-weight:600">%s</span>&nbsp;&nbsp;' % (c_tag, escape(ln.language.upper()))
               if ln.translate else "")
        body = escape(ln.translation if ln.translate else ln.text)
        block = ('<div style="margin:0 0 10px 0">%s<span style="color:%s; font-weight:600">%s</span><br>'
                 '<span style="font-size:15px">%s</span>' % (tag, c_sender, head, body))
        if ln.translate and ln.translation != ln.text:
            block += '<br><span style="color:%s; font-size:12px">%s</span>' % (c_original, escape(ln.text))
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
    i18n.set_language(settings["ui_language"])
    theme.apply(app, settings["theme"])
    from . import relupdate, update
    relupdate.claim_mutex()                              # the setup waits for it when it updates the program
    if update.frozen():
        from .config import data_dir
        relupdate.clean_update_folder(data_dir())        # a setup still there was installed or not wanted
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
