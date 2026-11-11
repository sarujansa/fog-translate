"""Write assets/logo.png (256 px, shown in the README) from fogtranslate/assets/icon-256.png.

    python tools/export_logo.py

The icon pictures themselves come from the fog-forge repository (tools/icons/); copy them into fogtranslate/assets/
and run this.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    path = os.path.join(ROOT, "assets", "logo.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    shutil.copyfile(os.path.join(ROOT, "fogtranslate", "assets", "icon-256.png"), path)
    print(path)
