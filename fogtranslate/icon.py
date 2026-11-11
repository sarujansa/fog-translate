"""The program's logo: two speech bubbles – a grey one with foreign "text" and an amber one with the translation –
over a wisp of fog. Amber is the colour of the language tag in the overlay.

0.11.3 (Saru: "die Icons sollten in einer höheren Qualität sein, ich bin mit allen 4 nicht zufrieden"): one family
with Fog Forge, Fog Scout and Fog Launch – the same dark tile with depth, glow, soft fog and amber. The pictures come
from the shared source in the fog-forge repository (tools/icons/, rendered by Chromium from SVG), one file per size
in assets/; 16–32 px are a simpler variant (no fog, larger bubbles) that stays sharp in the taskbar. Until 0.11.2 the
logo was drawn here with QPainter."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

SIZES = (16, 24, 32, 48, 64, 128, 256)          # assets/icon-<n>.png; up to 32 the small variant
ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
APP_ID = "FogTranslate.App"


def path(size: int) -> str:
    return os.path.join(ASSETS, f"icon-{size}.png")


def pixmap(size: int) -> QPixmap:
    """The logo at ``size`` px: its own picture when there is one, else the next larger one scaled down."""
    if size in SIZES:
        return QPixmap(path(size))
    larger = [n for n in SIZES if n >= size and (n > 32 or size <= 32)] or [SIZES[-1]]
    return QPixmap(path(larger[0])).scaled(size, size, Qt.AspectRatioMode.IgnoreAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)


def icon() -> QIcon:
    ic = QIcon()
    for n in SIZES:
        ic.addPixmap(pixmap(n))
    return ic


def set_app_id():
    """Windows: own taskbar group and icon instead of Python's (affects only this process)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def ico_bytes() -> bytes:
    """The logo as a Windows .ico (16–256 px) – for the .exe and the installer. Every size from its own picture
    (saving one big picture with ``sizes`` would scale it down instead)."""
    import io
    from PIL import Image
    pictures = []
    for n in SIZES:
        with Image.open(path(n)) as picture:
            pictures.append(picture.convert("RGBA"))
    out = io.BytesIO()
    pictures[-1].save(out, "ICO", sizes=[(n, n) for n in SIZES], append_images=pictures[:-1])
    return out.getvalue()


def save_ico(target: str) -> None:
    with open(target, "wb") as fh:
        fh.write(ico_bytes())
