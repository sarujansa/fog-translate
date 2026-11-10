"""One global key combination to hide/show the translations (default Ctrl+Alt+T).

Uses ``RegisterHotKey`` only – Windows tells our own program when the registered combination is pressed. No
keyboard hook, no reading of other keys, nothing is sent to the game. The combination is taken system-wide while
the program runs (the game does not get it), so the default is one DBD does not use.
"""
from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger(__name__)
IS_WIN = sys.platform == "win32"
WM_HOTKEY = 0x0312
HOTKEY_ID = 0x4654                    # "FT"
MODS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "win": 0x0008}
MOD_NOREPEAT = 0x4000
DEFAULT = "Ctrl+Alt+T"


def parse(combo: str) -> tuple[int, int] | None:
    """"Ctrl+Alt+T" → (modifiers, virtual key); None when it is not a usable combination. Needs at least one of
    Ctrl/Alt/Win (a plain letter would be taken away from every program), or an F-key F1–F24 alone."""
    parts = [p.strip().lower() for p in str(combo or "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for p in parts[:-1]:
        if p not in MODS:
            return None
        mods |= MODS[p]
    key = parts[-1]
    if len(key) == 1 and (key.isascii() and (key.isalpha() or key.isdigit())):
        vk = ord(key.upper())
        if not mods & (MODS["ctrl"] | MODS["alt"] | MODS["win"]):
            return None
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        return None
    return mods, vk


def message_id(message_address: int) -> int | None:
    """The hotkey id of a native Windows message (a pointer to MSG), None if it is not WM_HOTKEY."""
    from ctypes import wintypes
    msg = wintypes.MSG.from_address(message_address)
    return int(msg.wParam) if msg.message == WM_HOTKEY else None


class Hotkey:
    """Register in the GUI thread; ``pressed()`` is called there (through Qt's native event filter)."""

    def __init__(self, combo: str, pressed):
        self.combo = combo
        self.pressed = pressed
        self.registered = False
        self._filter = None

    def start(self, app) -> bool:
        parsed = parse(self.combo)
        if not IS_WIN or parsed is None:
            return False
        mods, vk = parsed
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            if not user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
                log.info("Hotkey %s not available (taken by another program?)", self.combo)
                return False
        except OSError:
            return False
        from PySide6.QtCore import QAbstractNativeEventFilter
        owner = self

        class Filter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, event_type, message):
                try:
                    if bytes(event_type) == b"windows_generic_MSG" and message_id(int(message)) == HOTKEY_ID:
                        owner.pressed()
                        return True, 0
                except Exception:                     # never break the event loop
                    log.exception("Hotkey filter")
                return False, 0

        self._filter = Filter()
        app.installNativeEventFilter(self._filter)
        self.registered = True
        return True

    def stop(self, app=None):
        if not self.registered:
            return
        try:
            ctypes.WinDLL("user32").UnregisterHotKey(None, HOTKEY_ID)
        except OSError:
            pass
        if app is not None and self._filter is not None:
            app.removeNativeEventFilter(self._filter)
        self.registered = False
