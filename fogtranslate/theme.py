"""Light and dark look of the windows (the translation overlay keeps its own dark design).

"auto" leaves everything as Qt shows it for Windows. "light"/"dark" switch to Qt's Fusion style with a palette of
our own, so the result is the same on Windows 10 and 11, and ask Qt for the matching title bar where it can.
"""
from __future__ import annotations

THEMES = ("auto", "light", "dark")
_native = None           # (style name, palette) as the program started

DARK = {"Window": "#1e1f22", "WindowText": "#e6e6e6", "Base": "#17181a", "AlternateBase": "#232428",
        "Text": "#e6e6e6", "Button": "#2b2d31", "ButtonText": "#e6e6e6", "BrightText": "#ffffff",
        "Highlight": "#3d6fd9", "HighlightedText": "#ffffff", "ToolTipBase": "#2b2d31", "ToolTipText": "#e6e6e6",
        "PlaceholderText": "#8a8f99", "Link": "#6ea8ff", "LinkVisited": "#b39dff",
        "Light": "#3a3d42", "Midlight": "#303237", "Mid": "#202225", "Dark": "#141517", "Shadow": "#000000"}
LIGHT = {"Window": "#f3f3f3", "WindowText": "#1b1b1b", "Base": "#ffffff", "AlternateBase": "#f7f7f7",
         "Text": "#1b1b1b", "Button": "#e9e9e9", "ButtonText": "#1b1b1b", "BrightText": "#000000",
         "Highlight": "#2f6fdb", "HighlightedText": "#ffffff", "ToolTipBase": "#ffffff", "ToolTipText": "#1b1b1b",
         "PlaceholderText": "#8a8a8a", "Link": "#0b57d0", "LinkVisited": "#6a3fb8",
         "Light": "#ffffff", "Midlight": "#f0f0f0", "Mid": "#c4c4c4", "Dark": "#a0a0a0", "Shadow": "#5a5a5a"}
DISABLED = {"dark": "#7a7d85", "light": "#9a9a9a"}
# the message list: (language tag, sender, original text)
HISTORY = {True: ("#ffc45c", "#8a93a3", "#8a8f99"), False: ("#a35f00", "#5a6472", "#6b7078")}


def palette(name: str):
    from PySide6.QtGui import QColor, QPalette
    p = QPalette()
    for role, colour in (DARK if name == "dark" else LIGHT).items():
        p.setColor(getattr(QPalette.ColorRole, role), QColor(colour))
    grey = QColor(DISABLED[name])
    for role in ("WindowText", "Text", "ButtonText"):
        p.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), grey)
    return p


def apply(app, name: str) -> str:
    """Set the look; returns the name used ("auto" for anything unknown)."""
    global _native
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPalette
    name = name if name in THEMES else "auto"
    if _native is None:
        _native = (app.style().objectName(), QPalette(app.palette()))
    scheme = {"dark": Qt.ColorScheme.Dark, "light": Qt.ColorScheme.Light}.get(name, Qt.ColorScheme.Unknown)
    try:
        app.styleHints().setColorScheme(scheme)      # the title bar, where the platform can
    except Exception:
        pass
    if name == "auto":
        if app.style().objectName().lower() != _native[0].lower():
            app.setStyle(_native[0])
        app.setPalette(QPalette())                   # back to what Windows gives
    else:
        if app.style().objectName().lower() != "fusion":
            app.setStyle("Fusion")
        app.setPalette(palette(name))
    return name


def is_dark(app) -> bool:
    from PySide6.QtGui import QPalette
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def history_colours(app) -> tuple:
    return HISTORY[is_dark(app)]
