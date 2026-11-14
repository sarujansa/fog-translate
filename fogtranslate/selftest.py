"""``FogTranslate.exe --selftest RESULT.json``: checks the packaged program in CI (and on request) – every module
imports, the libraries load, the window builds offscreen, the logo draws. Writes the result as JSON; exit 0 = ok.
Sends nothing anywhere; uses a temporary settings folder."""
from __future__ import annotations

import importlib
import json
import os
import pkgutil
import sys
import tempfile
import time


def run(out_path: str) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    checks = {}
    t0 = time.monotonic()

    def check(name, fn):
        try:
            value = fn()
            checks[name] = {"ok": True, "info": value}
        except Exception as e:                  # report, never crash
            checks[name] = {"ok": False, "info": "%s: %s" % (type(e).__name__, e)}

    import fogtranslate
    check("version", lambda: fogtranslate.__version__)
    check("frozen", lambda: bool(getattr(sys, "frozen", False)))
    modules = [m.name for m in pkgutil.iter_modules(fogtranslate.__path__)]
    check("modules", lambda: [importlib.import_module("fogtranslate." + m) and m for m in modules])
    for lib in ("mss", "numpy", "PIL", "PySide6.QtWidgets"):
        check("import " + lib, lambda lib=lib: getattr(importlib.import_module(lib), "__version__", "ok"))

    with tempfile.TemporaryDirectory() as data:
        os.environ["FOGTRANSLATE_DATA_DIR"] = data

        def window():
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance() or QApplication([])
            from .app import MainWindow
            from .config import Settings
            w = MainWindow(Settings())
            w.show()
            app.processEvents()
            size = (w.width(), w.height())
            w.close()
            return size
        check("window", window)
        check("logo", lambda: len(__import__("fogtranslate.icon", fromlist=["ico_bytes"]).ico_bytes()))
    result = {"ok": all(c["ok"] for c in checks.values()), "seconds": round(time.monotonic() - t0, 2),
              "checks": checks}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, default=str)
    return 0 if result["ok"] else 1
