"""The control window offscreen: switching services shows the right fields and keeps the choices."""
import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication  # noqa: E402

from fogtranslate.app import MainWindow  # noqa: E402
from fogtranslate.config import Settings  # noqa: E402


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
    win.accept.setChecked(True)
    win.toggle()                                      # starts at once; the missing key comes from the thread
    assert win.running and "Starting" in win.status.text()
    _wait(win, lambda: not win.running)
    assert "API key" in win.status.text()
    _pick(win, "ollama")
    win.toggle()                                      # Ollama needs neither
    assert win.running
    win.toggle()
    assert win.looper is None
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


def test_the_history_is_plain_text_even_if_the_service_sends_markup(app):
    from fogtranslate.app import history_html
    from fogtranslate.lines import ChatLine
    html = history_html([ChatLine("<b>Meg</b>", "<img src=x>", "ru", "<a href='x'>hi</a>", True)])
    assert "<b>Meg" not in html and "<img" not in html and "<a href" not in html
    assert "&lt;a href" in html and "RU" in html
