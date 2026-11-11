"""The control window offscreen: switching services shows the right fields and keeps the choices."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from fogtranslate.app import MainWindow  # noqa: E402
from fogtranslate.config import Settings  # noqa: E402
from fogtranslate.lines import ChatLine  # noqa: E402
from fogtranslate.translate import Result  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pick(win, service):
    win.service.setCurrentIndex(win.service.findData(service))


def test_switching_services(app):
    win = MainWindow(Settings())
    _pick(win, "ollama")
    assert win.key.isHidden() and not win.local_btn.isHidden() and win.accept.isHidden()
    assert win.model.isEditable()
    _pick(win, "gemini")
    assert not win.key.isHidden() and win.local_btn.isHidden()
    assert "aistudio.google.com" in win.key_link.text()
    win.model.setCurrentIndex(win.model.findData("gemini-flash-lite-latest"))
    win.model.activated.emit(win.model.currentIndex())
    assert win.settings["gemini_model"] == "gemini-flash-lite-latest"
    _pick(win, "claude")
    assert not win.model.isEditable()
    assert Settings()["service"] == "claude"          # saved
    win.close()


def test_starting_without_key_or_notice_is_refused(app):
    win = MainWindow(Settings())
    _pick(win, "gemini")
    win.toggle()
    assert not win.running and "notice" in win.status.text()
    assert win.tabs.currentWidget() is win.service_tab        # … and the window shows where to confirm it
    win._pump()
    assert "notice" in win.status.text()              # the message stays readable (it was gone after 200 ms)
    win.accept.setChecked(True)
    win.toggle()                                      # no key: refused at once, not by a start that fails
    assert not win.running and "API key" in win.status.text()
    win.key.setText("AIza-typed")
    win.settings["region"] = [0.8, 0.5, 0.15, 0.2]
    win.toggle()                                      # a key typed but not saved is taken
    assert win.running and "Starting" in win.status.text()
    assert win.settings.api_key("gemini") == "AIza-typed" and win.key.text() == ""
    win.toggle()
    _pick(win, "ollama")
    win.toggle()                                      # Ollama needs neither
    assert win.running
    win.toggle()
    assert win.looper is None
    win.close()


def test_start_without_a_chat_area_leads_to_marking_it_and_starts_then(app, monkeypatch):
    s = Settings()
    s["service"] = "ollama"
    s["auto_start"] = False
    win = MainWindow(s)
    started, asked = [], []
    monkeypatch.setattr(win, "_start_looper", lambda: started.append(1))
    monkeypatch.setattr(win, "pick_region", lambda: asked.append(1))
    win.toggle()
    assert asked == [1] and not win.running           # nothing to watch yet: mark first
    win._picked((0.1, 0.5, 0.3, 0.3))
    assert win.running and started == [1]             # Start was what was clicked, whatever "auto_start" says
    win.toggle()
    win._picked((0.1, 0.5, 0.3, 0.3))                 # marked again later, without Start: stays stopped
    assert not win.running
    win.close()


def test_without_the_game_marking_says_so_and_forgets_the_start(app):
    s = Settings()
    s["service"] = "ollama"
    win = MainWindow(s)
    win.toggle()                                      # no game here
    assert not win.running and "Dead by Daylight" in win.status.text() and not win._start_after_pick
    win.close()


def test_the_hint_names_the_next_step_and_leads_there(app):
    s = Settings()
    win = MainWindow(s)
    assert win.next_step() == "notice" and "notice" in win.hint.text() and not win.hint_btn.isHidden()
    win.hint_btn.click()
    assert win.tabs.currentWidget() is win.service_tab
    win.accept.setChecked(True)
    assert win.next_step() == "key" and "API key" in win.hint.text()
    s.session_keys["claude"] = "k"
    win._refresh()
    assert win.next_step() == "region" and "mark the chat area" in win.hint.text() and win.hint_btn.isHidden()
    assert win._looks[win.pick_btn] and not win._looks[win.run_btn]       # the button to press stands out
    s["region"] = [0.1, 0.5, 0.3, 0.3]
    win._refresh()
    assert win.next_step() == "" and "press Start" in win.hint.text()
    assert win._looks[win.run_btn] and not win._looks[win.pick_btn]
    win.running = True
    for status, error, word in (("watching", "", "above the chat"), ("no_game", "", "Open Dead by Daylight"),
                                ("cap", "", "daily limit"), ("error", "key", "Check the API key"), ("error", "net", "")):
        win.engine.status, win.engine.error = status, error
        win.engine.gate.stats = {"text_px": 5000, "chat": True}
        win._refresh()
        assert word in win.hint.text() and (win.hint.text() != "" or not word), status
        assert win.hint_btn.isHidden() == (status not in ("cap", "error") or error == "net"), status
    win.engine.status = "cap"
    win._refresh()
    win.tabs.setCurrentIndex(0)
    win.hint_btn.click()
    assert win.tabs.currentWidget() is win.service_tab
    win.running = False
    win.close()


def test_the_preview_shows_a_made_up_translation_for_a_moment(app):
    win = MainWindow(Settings())
    win.preview_overlay(0.05)
    assert win.overlay.isVisible() and win.overlay.lines[0].sender == "Fog Translate"
    assert win.overlay.rect_on_screen is not None     # blacked out of any picture like a real translation
    import time
    time.sleep(0.08)
    win._pump()
    assert not win.overlay.isVisible() and win.engine.last_sent is None
    win.close()


def test_the_place_of_the_translations_can_be_chosen_and_reset(app):
    import types
    s = Settings()
    s["region"] = [0.8, 0.5, 0.15, 0.2]
    win = MainWindow(s)
    win.pick_spot()                                   # no game here: says so, nothing opens
    assert "choose the position" in win.status.text() and win.picker is None
    assert not win.unplace_btn.isEnabled()
    win._spot_picked((0.75, 0.45, 0.1, 0.1))          # over the chat: its lines could not be read under it
    assert Settings()["overlay_spot"] is None and "covers the chat" in win.status.text()
    win._spot_picked(None)                            # cancelled
    assert Settings()["overlay_spot"] is None
    win._spot_picked((0.1, 0.2, 0.2, 0.1))
    assert Settings()["overlay_spot"] == [0.1, 0.2, 0.2, 0.1] and win.unplace_btn.isEnabled()
    win._preview_until = 0.0
    win.running = True
    win.game = types.SimpleNamespace(client=(0, 0, 800, 600), minimized=False)
    win.engine.chat_seen = True
    win.engine.answer(Result([ChatLine("Meg", "привет", "ru", "hallo", True)], 0.0))
    win._refresh_overlay()
    assert win.overlay.rect_on_screen[:2] == (80, 120)             # the box's top left corner in the game window
    win.reset_spot()
    assert Settings()["overlay_spot"] is None and not win.unplace_btn.isEnabled()
    win._refresh_overlay()
    x, y, _w, h = win.overlay.rect_on_screen
    assert (x, y + h + 6) == (640, 300)                            # back right above the chat area
    win.running = False
    win.close()


def test_a_broken_place_in_the_file_is_dropped(tmp_path):
    import json
    s = Settings()
    s.save()
    with open(s.path, encoding="utf-8") as fh:
        data = json.load(fh)
    data["overlay_spot"] = [2, "x"]
    with open(s.path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    assert Settings()["overlay_spot"] is None


def test_another_look_builds_the_window_again_so_links_take_its_colour(app):
    from fogtranslate import theme
    win = MainWindow(Settings())
    try:
        win.tabs.setCurrentIndex(2)
        old = win.key_link
        win.theme.setCurrentIndex(win.theme.findData("light"))
        win._theme_changed()
        assert win.key_link is not old and win.tabs.currentIndex() == 2 and win.theme.currentData() == "light"
    finally:
        theme.apply(app, "auto")
        win.close()


def test_the_language_change_stays_on_its_tab(app):
    win = MainWindow(Settings())
    win.tabs.setCurrentIndex(2)
    win.language.setCurrentIndex(win.language.findData("ja"))
    win._language_changed()
    assert win.tabs.currentIndex() == 2 and win.tabs.tabText(1) != "Service"
    win.close()


def _wait(win, done, seconds=10.0):
    import time
    end = time.monotonic() + seconds
    while not done() and time.monotonic() < end:
        win._pump()
        time.sleep(0.02)
    assert done()


def test_the_last_sent_picture_can_be_shown(app):
    import numpy as np
    win = MainWindow(Settings())
    win.show_last_picture()
    assert "Nothing sent" in win.status.text()
    win.engine.last_sent = np.zeros((40, 120, 3), np.uint8)
    win.show_last_picture()
    assert win._picture_view.pixmap().width() == 120
    win._picture_view.close()
    win.close()


def test_the_logo_is_drawn_at_every_size(app):
    from fogtranslate import icon
    ic = icon.icon()
    for n in icon.SIZES:
        pm = icon.pixmap(n)
        assert pm.width() == n and not pm.toImage().isNull()
        corner, middle = pm.toImage().pixelColor(0, 0), pm.toImage().pixelColor(n // 2, n // 2)
        assert corner.alpha() == 0 and middle.alpha() == 255      # rounded tile, opaque inside
    assert len(ic.availableSizes()) == len(icon.SIZES)


def test_the_update_button_follows_the_check(app):
    from fogtranslate.update import Check
    win = MainWindow(Settings())
    win._update_checked(Check("behind", 2))
    assert win.update_btn.text() == "Update and restart" and "2 changes" in win.status.text()
    win._update_checked(Check("newer", remote_version="9.9"))
    assert win.update_btn.text() == "Open download page"
    win._update_checked(Check("dirty"))
    assert win.update_btn.text() == "Check for updates" and "changed" in win.status.text()
    win.close()


def test_a_check_that_finds_nothing_says_so_on_the_button_for_a_moment(app):
    from fogtranslate.update import Check
    win = MainWindow(Settings())
    win._update_checked(Check("current"))
    assert win.update_btn.text() == "Up to date" and win.update_btn.isEnabled()
    assert "up to date" in win.status.text()
    win._release_checked(("error", None, "offline"))
    assert win.update_btn.text() == "Check failed"
    win._update_note = (win._update_note[0], 0.0)     # the moment is over
    win._pump()
    assert win.update_btn.text() == "Check for updates"
    win.close()


def test_the_history_is_plain_text_even_if_the_service_sends_markup(app):
    from fogtranslate.app import history_html
    from fogtranslate.lines import ChatLine
    html = history_html([ChatLine("<b>Meg</b>", "<img src=x>", "ru", "<a href='x'>hi</a>", True)])
    assert "<b>Meg" not in html and "<img" not in html and "<a href" not in html
    assert "&lt;a href" in html and "RU" in html


def test_the_status_says_when_the_marked_area_shows_no_text(app):
    win = MainWindow(Settings())
    win.running = True
    win.engine.status = "watching"
    win.engine.gate.stats = {"text_px": 3}
    win._refresh()
    assert "no text found" in win.status.text()
    win.engine.gate.stats = {"text_px": 5000}
    win._refresh()
    assert win.status.text() == "Watching the chat …"
    win.running = False
    win.close()


def test_the_selftest_passes(tmp_path):
    """Run like the .exe runs it: a fresh process. Inside the test process the windows, timers and threads of
    earlier tests got in the way (an import race, then a crash in processEvents – CI, 10.11.2026)."""
    import json
    import os
    import subprocess
    import sys
    out = tmp_path / "selftest.json"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", FOGTRANSLATE_DATA_DIR=str(tmp_path / "data"))
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, "-m", "fogtranslate", "--selftest", str(out)], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)
    result = json.loads(out.read_text(encoding="utf-8"))
    failed = {k: v for k, v in result["checks"].items() if not v["ok"]}
    assert proc.returncode == 0, (failed, proc.stderr[-2000:])
    assert result["ok"] and result["checks"]["logo"]["info"] > 1000

def test_the_daily_limit_can_be_set_in_the_window_and_shows_today(app):
    win = MainWindow(Settings())
    assert "Today 0 / 300 requests" in win.costs.text()
    win.daily_cap.setValue(120)
    assert Settings()["daily_cap"] == 120                 # saved
    assert "Today 0 / 120 requests" in win.costs.text()
    win.close()


def test_raising_the_limit_after_it_was_reached_goes_on_reading(app):
    from datetime import datetime
    win = MainWindow(Settings())
    win.daily_cap.setValue(10)
    day = datetime.now().strftime("%Y-%m-%d")
    for _ in range(10):
        win.settings.count_request(day, day[:7], 0.0)
    win.engine.status = "cap"
    win.daily_cap.setValue(20)
    assert win.engine.status == "watching"
    win.close()


def test_the_wheel_does_not_change_the_limit_without_focus(app):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    win = MainWindow(Settings())
    before = win.daily_cap.value()
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    win.daily_cap.wheelEvent(ev)
    assert win.daily_cap.value() == before
    win.close()


def test_switching_to_an_unconfirmed_service_while_running_stops(app, monkeypatch):
    """Review 10.11.2026: a running session sent pictures to Gemini without its notice being confirmed."""
    from fogtranslate import services

    class Quiet:
        def request(self, img):
            raise AssertionError("nothing may be sent")
    monkeypatch.setattr(services, "make", lambda settings: Quiet())
    settings = Settings()
    settings["region"] = [0.8, 0.5, 0.15, 0.2]
    settings.session_keys["gemini"] = "k"
    win = MainWindow(settings)
    _pick(win, "ollama")
    win.toggle()
    assert win.running
    _pick(win, "gemini")                              # notice never confirmed for Gemini
    assert not win.running and win.looper is None
    assert "confirm the notice" in win.status.text()
    win.accept.setChecked(True)
    win.toggle()
    assert win.running
    win.accept.setChecked(False)                      # unticked while running: stops as well
    assert not win.running and win.looper is None
    win.close()
