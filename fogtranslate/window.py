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
    user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindow.restype = wintypes.HWND
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    dwmapi = ctypes.WinDLL("dwmapi")
    dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    GA_ROOT = 2
    GW_HWNDPREV = 3
    GWL_EXSTYLE = -20
    WS_EX_TRANSPARENT, WS_EX_LAYERED = 0x20, 0x80000
    DWMWA_EXTENDED_FRAME_BOUNDS = 9
    DWMWA_CLOAKED = 14

# the taskbar is a strip at the screen edge, shown even over a full-screen game – it never hides the chat
NOT_COVERING = ("Shell_TrayWnd", "Shell_SecondaryTrayWnd")


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


# ------------------------------------------------------------------ is the chat region hidden?
def _cloaked(hwnd) -> bool:
    """"Visible" but not drawn (other virtual desktop, suspended store app)."""
    v = ctypes.c_int(0)
    return dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(v), ctypes.sizeof(v)) == 0 and v.value != 0


def _rect(hwnd):
    rc = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rc), ctypes.sizeof(rc)) != 0:
        if not user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return None
    return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top


def windows_above(hwnd, limit: int = 500) -> list | None:
    """Screen rects of the windows above ``hwnd`` in the Z order that can hide part of it: visible, not
    minimised, not cloaked, not click-through (overlays like ours), not the taskbar. Window-manager
    information only (Z order, style, position); no process is touched. ``None`` when more than ``limit``
    windows lie above: the walk goes upwards, so the window in front would be the one never looked at."""
    if not IS_WIN or not hwnd:
        return []
    out = []
    click_through = WS_EX_LAYERED | WS_EX_TRANSPARENT
    h = user32.GetWindow(hwnd, GW_HWNDPREV)
    steps = 0
    while h and steps < limit:
        steps += 1
        try:
            if (user32.IsWindowVisible(h) and not user32.IsIconic(h) and not _cloaked(h)
                    and (user32.GetWindowLongW(h, GWL_EXSTYLE) & click_through) != click_through
                    and _class(h) not in NOT_COVERING):
                r = _rect(h)
                if r and r[2] > 0 and r[3] > 0:
                    out.append(r)
        except OSError:
            pass
        h = user32.GetWindow(h, GW_HWNDPREV)
    return None if h else out


def overlaps(box, rects) -> bool:
    """True if ``box`` (x, y, w, h) shares pixels with one of ``rects``."""
    x, y, w, h = box
    return any(rx < x + w and x < rx + rw and ry < y + h and y < ry + rh for rx, ry, rw, rh in rects)


def region_free(game: GameWindow | None, box) -> bool:
    """Nothing lies over ``box`` of the game window – then the screen shows the chat even with DBD behind."""
    if game is None or box is None:
        return False
    above = windows_above(game.hwnd)
    return above is not None and not overlaps(box, above)       # not walked to the end → counts as covered
