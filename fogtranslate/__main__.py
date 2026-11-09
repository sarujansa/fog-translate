"""``python -m fogtranslate`` – start the program. ``--test PICTURE.png`` translates one screenshot crop once."""
from __future__ import annotations

import argparse
import logging
import os
import sys


_CRASH = None          # kept open for faulthandler as long as the program runs


def _log_setup():
    """Log file + every uncaught error (window thread and other threads) + a hard crash/hang dump."""
    global _CRASH
    import faulthandler
    import threading
    from . import __version__
    from .config import data_dir
    folder = data_dir()
    os.makedirs(folder, exist_ok=True)
    logging.basicConfig(filename=os.path.join(folder, "fogtranslate.log"), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s")
    log = logging.getLogger("fogtranslate")
    log.info("Fog Translate %s, Python %s", __version__, sys.version.split()[0])

    def on_error(kind, value, tb):
        log.error("Unerwarteter Fehler", exc_info=(kind, value, tb))

    sys.excepthook = on_error
    threading.excepthook = lambda a: on_error(a.exc_type, a.exc_value, a.exc_traceback)
    try:
        _CRASH = open(os.path.join(folder, "crash.txt"), "w", encoding="utf-8")
        faulthandler.enable(_CRASH, all_threads=True)
    except OSError:
        pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fogtranslate")
    ap.add_argument("--test", metavar="PICTURE", help="translate one picture (chat crop) once")
    ap.add_argument("--service", choices=("claude", "gemini", "ollama"), help="service for --test")
    ap.add_argument("--selftest", metavar="RESULT.json", help="check the program, write the result, exit")
    args = ap.parse_args(argv)
    if args.selftest:
        from .selftest import run as selftest
        return selftest(args.selftest)
    _log_setup()
    if args.test:
        import numpy as np
        from PIL import Image
        from .config import Settings
        from . import services
        from .translate import TranslateError
        s = Settings()
        if args.service:
            s["service"] = args.service
        img = np.asarray(Image.open(args.test).convert("RGB"))[..., ::-1]
        try:
            res = services.make(s).request(img)
        except TranslateError as e:
            print("Error:", e.kind)
            return 1
        for ln in res.lines:
            print(("✓ " if not ln.translate else "→ ") + "[%s] %s: %s  |  %s"
                  % (ln.language, ln.sender, ln.text, ln.translation))
        print("Cost about $%.4f" % res.cost_usd)
        return 0
    from .app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
