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
    win.toggle()
    assert not win.running and "API-Key" in win.status.text()
    _pick(win, "ollama")
    win.toggle()                                      # Ollama needs neither
    assert win.running
    win.toggle()
    win.close()
