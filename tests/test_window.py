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
    assert not win.running and "Hinweis" in win.status.text()
    win.accept.setChecked(True)
    win.toggle()                                      # starts at once; the missing key comes from the thread
    assert win.running and "Startet" in win.status.text()
    _wait(win, lambda: not win.running)
    assert "API-Key" in win.status.text()
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
    assert "Noch nichts" in win.status.text()
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
