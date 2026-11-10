"""The window's language. English text is the key: ``tr("Start")``; ``N_("…")`` only marks a text in a table that
is translated where it is shown (``tr(STATUS[key])``). Placeholders stay ``%s``/``%d`` in the same order.

Translations live in ``lang_<code>.py`` (a dict ``T``); a text without an entry is shown in English. The setting
``ui_language`` is a code or "auto" = the language of Windows, English when that is none of ours.
(Until 0.9.8 the window was English only; the log stays as it is.)
"""
from __future__ import annotations

import importlib

LANGS = {"en": "English", "it": "Italiano", "ru": "Русский", "zh": "简体中文", "ja": "日本語", "ko": "한국어"}
_table: dict[str, str] = {}
_current = "en"


def N_(text: str) -> str:
    return text


def tr(text: str) -> str:
    return _table.get(text, text)


def current() -> str:
    return _current


def system_language() -> str:
    """The Windows language as one of ``LANGS`` ("en" when it is another one)."""
    try:
        from PySide6.QtCore import QLocale
        names = list(QLocale.system().uiLanguages()) + [QLocale.system().name()]
    except Exception:
        return "en"
    for name in names:
        code = str(name).replace("_", "-").split("-")[0].lower()
        if code in LANGS:
            return code
        if code:
            return "en"                      # the first language Windows lists decides
    return "en"


def resolve(setting: str) -> str:
    return setting if setting in LANGS else system_language()


def table(code: str) -> dict:
    if code == "en" or code not in LANGS:
        return {}
    return dict(importlib.import_module("%s.lang_%s" % (__package__, code)).T)


def set_language(setting: str) -> str:
    """Switch to ``setting`` (a code or "auto"); returns the code now in use."""
    global _table, _current
    _current = resolve(setting)
    _table = table(_current)
    return _current
