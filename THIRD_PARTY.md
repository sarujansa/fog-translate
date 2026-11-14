# Fremde Bestandteile / Third-party components

Fog Translate enthält keinen fremden Quelltext. Die folgenden Bibliotheken werden beim Einrichten von PyPI
installiert (`requirements.txt`, Versionen fest) und stehen unter ihren eigenen Lizenzen – die Nutzungsbedingungen
in `LICENSE` gelten für sie nicht.

Fog Translate contains no third-party source code. The libraries below are installed from PyPI during setup
(`requirements.txt`, pinned versions) and are subject to their own licenses – the terms in `LICENSE` do not apply
to them.

| Paket / Package | Version | Lizenz / License |
|---|---|---|
| PySide6-Essentials, shiboken6 (Qt for Python) | 6.11.2 | LGPL-3.0-only (or GPL-2.0/3.0) |
| numpy | 2.5.4 | BSD-3-Clause (and others, see package) |
| Pillow | 13.0.0 | MIT-CMU |
| mss | 10.2.0 | MIT |

Qt / PySide6 wird unter der LGPL-3.0 genutzt (dynamisch geladen, unverändert). / Qt / PySide6 is used under the
LGPL-3.0 (dynamically loaded, unmodified).

Die installierte .exe wird mit **PyInstaller** gebaut (GPL-2.0 mit Ausnahme für damit gebaute Programme) und das
Setup mit **Inno Setup** (eigene, freie Lizenz). / The installed .exe is built with **PyInstaller** (GPL-2.0 with an
exception for programs built with it), the setup with **Inno Setup** (its own free license).

