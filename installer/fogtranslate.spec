# -*- mode: python -*-
# PyInstaller build of Fog Translate as a folder app (onedir: nothing is unpacked at each start; the installer
# copies the folder). Built in GitHub Actions on Windows (.github/workflows/build.yml); by hand, from the repository
# root, with requirements.txt and requirements-build.txt installed:
#     python -m PyInstaller --noconfirm --clean installer/fogtranslate.spec
# Result: dist/FogTranslate/FogTranslate.exe. Check: FogTranslate.exe --selftest <result.json> (fogtranslate/selftest.py).
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PACKAGE = os.path.join(ROOT, "fogtranslate")
datas = [(os.path.join(ROOT, name), ".") for name in ("LICENSE", "THIRD_PARTY.md", "README.md", "README.en.md")]
hiddenimports = sorted(f"fogtranslate.{name[:-3]}" for name in os.listdir(PACKAGE)
                       if name.endswith(".py") and name != "__init__.py")

os.makedirs(workpath, exist_ok=True)
ICON = os.path.join(workpath, "fogtranslate.ico")
from fogtranslate import icon  # noqa: E402  (the logo is drawn, not a file)
icon.save_ico(ICON)

a = Analysis(
    [os.path.join(SPECPATH, "fogtranslate_exe.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
    noarchive=False,
)
# never used: Qt's software OpenGL (20 MB) and Qt's own translations (the program is English)
a.binaries = [b for b in a.binaries if not b[0].replace("\\", "/").endswith("opengl32sw.dll")]
a.datas = [d for d in a.datas if "/translations/" not in d[0].replace("\\", "/")]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="FogTranslate", icon=ICON, console=False,
          upx=False, version=None)
coll = COLLECT(exe, a.binaries, a.datas, name="FogTranslate", upx=False)
