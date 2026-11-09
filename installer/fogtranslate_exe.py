"""Entry of the packaged program (PyInstaller, installer/fogtranslate.spec): the same as ``python -m fogtranslate``."""
import sys

from fogtranslate.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
