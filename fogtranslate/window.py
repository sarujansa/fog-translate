"""The Dead by Daylight window – window-manager information only (class, title, position).

Never opens the game process, never sends it a message or input.
"""
from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

IS_WIN = sys.platform == "win32"
GAME_CLASS = "UnrealWindow"

if IS_WIN:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND
    GA_ROOT = 2


@dataclass(frozen=True)
class GameWindow:
    hwnd: int
    client: tuple[int, int, int, int]       # client area (the game picture) in screen coordinates
    minimized: bool = False


def _text(hwnd) -> str:
    """The title with a fixed buffer and no length query first (that query may send the window a message, and a
    busy window could then block us). GetWindowText reads another process's caption without a message."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def _class(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def is_game(hwnd) -> bool:
    if not IS_WIN or not hwnd:
        return False
    try:
        return (bool(user32.IsWindowVisible(hwnd)) and _class(hwnd) == GAME_CLASS
                and "deadbydaylight" in _text(hwnd).lower().replace(" ", ""))
    except OSError:
        return False


def _client(hwnd):
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        return None
    return pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top


def find_game() -> GameWindow | None:
    if not IS_WIN:
        return None
    found = []

    def cb(hwnd, _):
        if is_game(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    if not found:
        return None
    hwnd = found[0]
    client = _client(hwnd)
    if client is None:
        return None
    return GameWindow(int(hwnd), client, bool(user32.IsIconic(hwnd)))


def game_in_front(game: GameWindow | None) -> bool:
    """The DBD window is the active window (then the chat region is not covered by another program)."""
    if not IS_WIN or game is None:
        return False
    fg = user32.GetForegroundWindow()
    root = user32.GetAncestor(fg, GA_ROOT) if fg else None
    return bool(root) and int(root) == game.hwnd
