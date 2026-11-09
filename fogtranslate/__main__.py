"""``python -m fogtranslate`` – start the program. ``--test BILD.png`` translates one screenshot crop once."""
from __future__ import annotations

import argparse
import logging
import os
import sys


def _log_setup():
    from .config import data_dir
    folder = data_dir()
    os.makedirs(folder, exist_ok=True)
    logging.basicConfig(filename=os.path.join(folder, "fogtranslate.log"), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="fogtranslate")
    ap.add_argument("--test", metavar="BILD", help="ein Bild (Chat-Ausschnitt) einmal übersetzen")
    args = ap.parse_args(argv)
    _log_setup()
    if args.test:
        import numpy as np
        from PIL import Image
        from .config import Settings
        from .translate import TranslateError, Translator
        s = Settings()
        key = s.api_key()
        if not key:
            print("Kein API-Key (Einstellungen oder ANTHROPIC_API_KEY).")
            return 2
        img = np.asarray(Image.open(args.test).convert("RGB"))[..., ::-1]
        try:
            res = Translator(key, s["model"], s["target"]).request(img)
        except TranslateError as e:
            print("Fehler:", e.kind)
            return 1
        for ln in res.lines:
            print(("✓ " if not ln.translate else "→ ") + "[%s] %s: %s  |  %s"
                  % (ln.language, ln.sender, ln.text, ln.translation))
        print("Kosten ca. %.4f $" % res.cost_usd)
        return 0
    from .app import run
    return run()


if __name__ == "__main__":
    sys.exit(main())
