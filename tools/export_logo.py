"""Write assets/logo.png (256 px) from fogtranslate/icon.py – run after changing the drawing.

    python tools/export_logo.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from fogtranslate import icon  # noqa: E402

if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    path = os.path.join(ROOT, "assets", "logo.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not icon.pixmap(256).save(path, "PNG"):
        raise SystemExit("could not write " + path)
    print(path)
