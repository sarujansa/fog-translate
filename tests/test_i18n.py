"""The window's languages (i18n.py, lang_*.py) and its light/dark look (theme.py)."""
import ast
import os
import re

import pytest

from fogtranslate import i18n

ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fogtranslate")
PLACEHOLDER = re.compile(r"%(?:\.\d)?[sdf]|\$")
NAMES = ("Fog Translate", "Dead by Daylight", "Ollama", "Claude", "Gemini", "Ctrl+Alt+T", "GitHub", "DPAPI")


def texts():
    """Every text the program shows: the literal in each tr("…") and N_("…")."""
    found, loose = [], []
    for name in sorted(os.listdir(ROOT)):
        if not name.endswith(".py") or name.startswith("lang_"):
            continue
        with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "N_"):
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.append(arg.value)
                elif node.func.id == "N_":
                    loose.append((name, node.lineno))
    return sorted(set(found)), loose


def test_every_marked_text_is_a_literal():
    assert texts()[1] == []                           # N_(variable) would hide a text from the tables


@pytest.mark.parametrize("code", [c for c in i18n.LANGS if c != "en"])
def test_every_text_is_translated_with_the_same_placeholders(code):
    table = i18n.table(code)
    keys = texts()[0]
    assert len(keys) > 140
    assert [k for k in keys if k not in table] == []
    assert [k for k in table if k not in keys] == []          # nothing left over from a text that is gone
    for key in keys:
        value = table[key]
        assert value.strip(), key
        assert PLACEHOLDER.findall(value) == PLACEHOLDER.findall(key), (key, value)
        assert (key[:1] == " ") == (value[:1] == " ") and (key[-1:] == " ") == (value[-1:] == " "), (key, value)
        assert "<" not in value or "<" in key, (key, value)   # no markup comes in through a translation
        for name in NAMES:
            assert value.count(name) >= min(1, key.count(name)), (key, name)


def test_the_setting_chooses_the_language_and_auto_follows_windows(monkeypatch):
    assert i18n.set_language("ru") == "ru" and i18n.tr("Start") != "Start"
    assert i18n.tr("a text nobody translated") == "a text nobody translated"
    assert i18n.set_language("en") == "en" and i18n.tr("Start") == "Start"
    assert i18n.set_language("xx") == i18n.system_language()
    monkeypatch.setattr(i18n, "system_language", lambda: "ja")
    assert i18n.set_language("auto") == "ja" and i18n.current() == "ja"


def test_windows_languages_map_to_ours(monkeypatch):
    from PySide6.QtCore import QLocale

    class Fake:
        def __init__(self, names):
            self.names = names

        def uiLanguages(self):
            return self.names

        def name(self):
            return "en_US"
    for names, want in ((["zh-Hans-CN"], "zh"), (["ko-KR", "en-US"], "ko"), (["de-DE", "ru-RU"], "en"),
                        (["it"], "it"), ([], "en")):
        monkeypatch.setattr(QLocale, "system", staticmethod(lambda names=names: Fake(names)))
        assert i18n.system_language() == want, names


# ---------------------------------------------------------------- the windows
pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtWidgets import QApplication  # noqa: E402

from fogtranslate import theme  # noqa: E402
from fogtranslate.app import MainWindow, history_html  # noqa: E402
from fogtranslate.config import Settings  # noqa: E402
from fogtranslate.lines import ChatLine  # noqa: E402
from fogtranslate.translate import Result  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_choosing_a_language_rebuilds_the_window_and_is_saved(app):
    win = MainWindow(Settings())
    win.engine.answer(Result([ChatLine("Meg", "привет", "ru", "hello", True)], 0.0))
    assert win.run_btn.text() == "Start" and win.language.currentData() == "auto"
    win.language.setCurrentIndex(win.language.findData("it"))
    win._language_changed()
    assert Settings()["ui_language"] == "it" and i18n.current() == "it"
    it = i18n.table("it")
    assert win.run_btn.text() == it["Start"] and win.pick_btn.text() == it["Mark chat area"]
    assert win.update_btn.text() == it["Check for updates"] and win.language.currentData() == "it"
    assert "hello" in win.history.toPlainText()                # what was translated so far is still listed
    win._pump()                                                # the status line comes in the new language
    assert win.status.text() == it["Stopped."] and win.hint.text() == it["Next: confirm the notice for this service."]
    win.language.setCurrentIndex(win.language.findData("en"))
    win._language_changed()
    assert win.run_btn.text() == "Start"
    win.close()


@pytest.mark.parametrize("code", [c for c in i18n.LANGS if c != "en"])
def test_the_windows_build_in_every_language(app, code):
    from fogtranslate.wizard import SetupWizard
    s = Settings()
    s["ui_language"] = code
    i18n.set_language(code)
    win = MainWindow(s)
    win.running = True
    win.engine.error = "net"
    for status in ("watching", "asking", "cap", "error", "no_game"):
        win.engine.status = status
        win._refresh()
        assert win.status.text()
    win.running = False
    wiz = SetupWizard(s)
    for page in range(3):
        wiz._show_page(page)
    assert wiz.next_btn.text() == i18n.tr("Finish") != "Finish"
    wiz.close()
    win.close()


def test_the_assistant_can_switch_the_language_and_keeps_the_choice(app):
    from fogtranslate.wizard import SetupWizard
    s = Settings()
    told = []
    wiz = SetupWizard(s, relang=lambda: told.append(1))
    wiz.radios["ollama"].setChecked(True)
    wiz.language.setCurrentIndex(wiz.language.findData("ko"))
    wiz._language_changed()
    assert told == [1] and Settings()["ui_language"] == "ko"
    assert wiz.radios["ollama"].isChecked() and wiz.next_btn.text() == i18n.table("ko")["Next"]
    wiz.close()


def test_light_and_dark_are_set_and_saved(app):
    win = MainWindow(Settings())
    try:
        for name, dark in (("dark", True), ("light", False)):
            win.theme.setCurrentIndex(win.theme.findData(name))
            win._theme_changed()
            assert Settings()["theme"] == name and theme.is_dark(app) is dark
            assert app.style().objectName().lower() == "fusion"
        win.theme.setCurrentIndex(win.theme.findData("auto"))
        win._theme_changed()
        assert Settings()["theme"] == "auto" and app.style().objectName().lower() == theme._native[0].lower()
        assert theme.apply(app, "pink") == "auto"
    finally:
        theme.apply(app, "auto")
        win.close()


def test_the_message_list_is_readable_in_both_looks():
    def contrast(a, b):
        def lum(c):
            v = [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
            return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
        hi, lo = sorted((lum(a), lum(b)), reverse=True)
        return (hi + 0.05) / (lo + 0.05)
    for dark, colours in ((True, theme.DARK), (False, theme.LIGHT)):
        for colour in theme.HISTORY[dark]:
            assert contrast(colour, colours["Base"]) >= 4.5, (dark, colour)
        assert contrast(colours["Text"], colours["Base"]) >= 7 and contrast(colours["ButtonText"], colours["Button"]) >= 7
        assert contrast(colours["PlaceholderText"], colours["Base"]) >= 3
    line = ChatLine("Meg", "привет", "ru", "hello", True)
    assert theme.HISTORY[False][0] in history_html([line], theme.HISTORY[False])
    assert theme.HISTORY[True][0] in history_html([line])
