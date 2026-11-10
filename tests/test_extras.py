"""Test button, answer time, overlay settings, tray and hotkey."""
import ctypes
import sys
import time

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from fogtranslate import hotkey, services, translate  # noqa: E402
from fogtranslate.app import MainWindow  # noqa: E402
from fogtranslate.config import Settings  # noqa: E402
from fogtranslate.lines import ChatLine  # noqa: E402
from fogtranslate.translate import Result, TranslateError  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _wait(win, done, seconds=10.0):
    end = time.monotonic() + seconds
    while not done() and time.monotonic() < end:
        win._pump()
        time.sleep(0.02)
    assert done()


# ---------------------------------------------------------------- hotkey (pure parts)
def test_hotkey_combinations():
    assert hotkey.parse("Ctrl+Alt+T") == (0x0002 | 0x0001, ord("T"))
    assert hotkey.parse("ctrl + shift + f9") == (0x0002 | 0x0004, 0x78)
    assert hotkey.parse("F13") == (0, 0x7C)
    assert hotkey.parse("T") is None                  # a plain letter would be taken from every program
    assert hotkey.parse("Shift+T") is None
    assert hotkey.parse("") is None and hotkey.parse("Ctrl+Banana") is None and hotkey.parse("Hyper+T") is None


def test_only_the_hotkey_message_is_recognised():
    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MSG(ctypes.Structure):                      # the layout of the Windows MSG
        _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint), ("wParam", ctypes.c_size_t),
                    ("lParam", ctypes.c_ssize_t), ("time", ctypes.c_ulong), ("pt", POINT)]

    if sys.platform != "win32":                       # ctypes.wintypes.MSG exists everywhere; check our reading of it
        from ctypes import wintypes
        assert wintypes.MSG.message.offset == MSG.message.offset
        assert wintypes.MSG.wParam.offset == MSG.wParam.offset
    msg = MSG(None, hotkey.WM_HOTKEY, hotkey.HOTKEY_ID, 0, 0, POINT(0, 0))
    assert hotkey.message_id(ctypes.addressof(msg)) == hotkey.HOTKEY_ID
    other = MSG(None, 0x0100, hotkey.HOTKEY_ID, 0, 0, POINT(0, 0))        # WM_KEYDOWN
    assert hotkey.message_id(ctypes.addressof(other)) is None


def test_without_windows_no_hotkey_is_registered(app):
    hk = hotkey.Hotkey("Ctrl+Alt+T", lambda: None)
    if sys.platform != "win32":
        assert hk.start(app) is False and not hk.registered
    hk.stop(app)


# ---------------------------------------------------------------- window
def test_the_translations_can_be_hidden_and_shown_again(app):
    win = MainWindow(Settings())
    assert not win.overlay_hidden
    win.toggle_overlay()
    assert win.overlay_hidden and not win.overlay.isVisible()
    win.toggle_overlay()
    assert not win.overlay_hidden
    win.close()


def test_text_size_and_duration_are_set_in_the_window(app):
    win = MainWindow(Settings())
    win.font_px.setValue(26)
    win.show_s.setValue(60)
    s = Settings()
    assert s["font_px"] == 26 and s["show_s"] == 60.0
    assert win.overlay.font_main.pixelSize() == 26
    win.close()


def test_the_answer_time_is_shown(app):
    win = MainWindow(Settings())
    res = Result([ChatLine("Meg", "hola", "es", "hallo", True)], 0.001)
    res.seconds = 1.84
    win.results.put(("answer", res))
    win._pump()
    assert "last answer 1.8 s" in win.costs.text()
    assert win.engine.last_counts["seconds"] == 1.84
    win.close()


def test_the_test_button_reports_success_and_failure(app, monkeypatch):
    class Fake:
        def request(self, img):
            assert img.shape[1] == 520                # the made-up sample, never the screen
            return Result([ChatLine("Meg", "hola", "es", "hallo", True)] * 3, 0.002)

    win = MainWindow(Settings())
    win.service.setCurrentIndex(win.service.findData("ollama"))      # needs no notice
    monkeypatch.setattr(services, "make", lambda settings: Fake())
    win.test_service()
    _wait(win, lambda: win.test_btn.isEnabled())
    assert "Test OK – 3 of 3 messages" in win.status.text()

    def broken(settings):
        raise TranslateError("key")

    monkeypatch.setattr(services, "make", broken)
    win.test_service()
    _wait(win, lambda: win.test_btn.isEnabled())
    assert "Test failed: API key missing or invalid." in win.status.text()
    win.close()


def test_the_test_needs_the_notice_for_cloud_services(app):
    win = MainWindow(Settings())
    win.service.setCurrentIndex(win.service.findData("gemini"))
    win.test_service()
    assert "notice" in win.status.text() and win.test_btn.isEnabled()
    win.close()


def test_closing_goes_to_the_tray_only_when_asked_and_possible(app):
    win = MainWindow(Settings())
    win.show()
    win.to_tray.setChecked(True)
    assert Settings()["close_to_tray"] is True
    win.close()                                       # no tray here (offscreen): closing really closes
    assert win.tray is None and not win.isVisible()


def test_the_sample_picture_shows_text_the_gate_would_send():
    from fogtranslate.change import MIN_TEXT_PX, text_mask
    assert text_mask(translate.sample_picture()).sum() > MIN_TEXT_PX
