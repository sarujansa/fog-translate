"""The API key at rest: encrypted with Windows DPAPI (current user), never written as clear text.

Without DPAPI (Linux, or DPAPI failing) ``protect`` raises ``CannotProtect`` and the key is kept for the session
only. The key never goes to the log.
"""
from __future__ import annotations

import base64
import ctypes
import sys

IS_WIN = sys.platform == "win32"


class CannotProtect(Exception):
    pass


def _dpapi(data: bytes, encrypt: bool) -> bytes:
    from ctypes import wintypes

    class BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    fn.argtypes = [ctypes.POINTER(BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                   wintypes.DWORD, ctypes.POINTER(BLOB)]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buf = ctypes.create_string_buffer(data, len(data))
    src = BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    dst = BLOB()
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(dst)):    # 0x1 = UI forbidden
        raise OSError(ctypes.get_last_error(), "DPAPI")
    try:
        return ctypes.string_at(dst.pbData, dst.cbData)
    finally:
        kernel.LocalFree(dst.pbData)


CIPHER = _dpapi if IS_WIN else None


def protect(secret: str, cipher=None) -> str:
    cipher = cipher or CIPHER
    if not secret:
        return ""
    if cipher is None:
        raise CannotProtect("no DPAPI")
    try:
        return "dpapi:" + base64.b64encode(cipher(secret.encode("utf-8"), True)).decode("ascii")
    except (OSError, ValueError) as e:
        raise CannotProtect(type(e).__name__) from None


def unprotect(stored, cipher=None) -> str:
    cipher = cipher or CIPHER
    s = str(stored or "")
    if not s.startswith("dpapi:") or cipher is None:
        return ""
    try:
        return cipher(base64.b64decode(s[6:]), False).decode("utf-8")
    except (OSError, ValueError):
        return ""
