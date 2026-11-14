"""The setup assistant of the first start."""
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from fogtranslate import secret, wizard  # noqa: E402
from fogtranslate.app import MainWindow  # noqa: E402
from fogtranslate.config import Settings  # noqa: E402
from fogtranslate.lines import ChatLine  # noqa: E402
from fogtranslate.translate import Result, TranslateError  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _a_cipher(monkeypatch):
    """Keys can be stored in the tests (DPAPI exists only on Windows)."""
    monkeypatch.setattr(secret, "CIPHER", lambda data, enc: bytes(b ^ 0x5A for b in data))


def _wait(wiz, done, seconds=10.0):
    end = time.monotonic() + seconds
    while not done() and time.monotonic() < end:
        wiz._pump()
        time.sleep(0.02)
    assert done()


def test_it_is_offered_only_before_anything_is_set_up():
    s = Settings()
    assert wizard.wanted(s)
    s["region"] = [0.1, 0.1, 0.3, 0.3]
    assert not wizard.wanted(s)                       # an existing user (area marked)
    s["region"] = None
    s.set_api_key("gemini", "AIza-x")
    assert not wizard.wanted(s)                       # … or a key stored
    s2 = Settings()
    s2["claude_key"] = s2["gemini_key"] = ""
    s2["setup_done"] = True
    assert not wizard.wanted(s2)                      # finished or skipped once


def test_going_through_with_a_cloud_service_stores_key_notice_and_choice(app, tmp_path):
    s = Settings()
    done = []
    wiz = wizard.SetupWizard(s, lambda: done.append(1))
    wiz.radios["gemini"].setChecked(True)
    wiz.target.setCurrentIndex(wiz.target.findData("en"))
    wiz.next()
    assert wiz.pages.currentIndex() == 1 and "aistudio.google.com" in wiz.key_help.text()
    assert not wiz.next_btn.isEnabled()               # the notice is not confirmed yet
    wiz.accept.setChecked(True)
    wiz.next()
    assert wiz.pages.currentIndex() == 1 and "paste an API key" in wiz.result.text()
    wiz.key.setText("AIza-secret-key")
    wiz.next()
    assert wiz.pages.currentIndex() == 2
    wiz.next()                                        # Finish
    assert done == [1] and not wiz.isVisible()
    saved = Settings()
    assert saved["service"] == "gemini" and saved["target"] == "en" and saved["setup_done"]
    assert saved.accepted("gemini") and saved.api_key("gemini") == "AIza-secret-key"
    with open(saved.path, encoding="utf-8") as fh:
        assert "AIza-secret-key" not in fh.read()     # never in clear text


def test_ollama_needs_no_key_and_no_notice(app):
    s = Settings()
    wiz = wizard.SetupWizard(s)
    wiz.radios["ollama"].setChecked(True)
    wiz.next()
    assert wiz.key.isHidden() and wiz.accept.isHidden() and wiz.next_btn.isEnabled()
    wiz.next()
    assert wiz.pages.currentIndex() == 2
    wiz.back()
    assert wiz.pages.currentIndex() == 1
    wiz.close()


def test_the_test_button_reports_success_and_failure(app):
    class Fake:
        def request(self, img):
            return Result([ChatLine("Meg", "hola", "es", "hi", True)] * 3, 0.0)

    s = Settings()
    wiz = wizard.SetupWizard(s, make=lambda settings: Fake())
    wiz.radios["claude"].setChecked(True)
    wiz.next()
    wiz.accept.setChecked(True)
    wiz.test()
    assert "paste an API key" in wiz.result.text()    # nothing is sent without a key
    wiz.key.setText("sk-ant-test")
    wiz.test()
    _wait(wiz, lambda: "works" in wiz.result.text() or "failed" in wiz.result.text())
    assert "It works" in wiz.result.text() and "3 of 3" in wiz.result.text()
    from datetime import datetime
    assert Settings().requests_today(datetime.now().strftime("%Y-%m-%d")) == 1      # a test counts as a request

    def broken(settings):
        raise TranslateError("key")

    wiz._make = broken
    wiz.test()
    _wait(wiz, lambda: "failed" in wiz.result.text())
    assert "invalid" in wiz.result.text()
    wiz.close()


def test_skipping_or_closing_never_shows_it_again(app):
    for how in ("skip", "close"):
        s = Settings()
        s["setup_done"] = False
        s.save()
        done = []
        wiz = wizard.SetupWizard(s, lambda: done.append(1))
        wiz.show()
        wiz.skip() if how == "skip" else wiz.close()
        assert done == [1] and Settings()["setup_done"], how


def test_the_main_window_takes_over_what_the_assistant_stored(app):
    win = MainWindow(Settings())
    win.open_setup()
    wiz = win.wizard
    wiz.radios["ollama"].setChecked(True)
    wiz.target.setCurrentIndex(wiz.target.findData("fr"))
    wiz.next()
    wiz.next()
    wiz.next()
    assert win.wizard is None
    assert win.service.currentData() == "ollama" and win.target.currentData() == "fr"
    assert win.key.isHidden()
    win.close()
