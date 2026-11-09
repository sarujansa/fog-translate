# Fremde Bestandteile / Third-party components

Fog Translate enthält keinen fremden Quelltext. Die folgenden Bibliotheken werden beim Einrichten von PyPI
installiert (`requirements.txt`, Versionen fest) und stehen unter ihren eigenen Lizenzen – die Nutzungsbedingungen
in `LICENSE` gelten für sie nicht.

Fog Translate contains no third-party source code. The libraries below are installed from PyPI during setup
(`requirements.txt`, pinned versions) and are subject to their own licenses – the terms in `LICENSE` do not apply
to them.

| Paket / Package | Version | Lizenz / License |
|---|---|---|
| anthropic | 2.7.0 | Apache-2.0 |
| PySide6-Essentials, shiboken6 (Qt for Python) | 6.11.2 | LGPL-3.0-only (or GPL-2.0/3.0) |
| numpy | 2.5.4 | BSD-3-Clause (and others, see package) |
| Pillow | 13.0.0 | MIT-CMU |
| mss | 10.2.0 | MIT |
| pydantic, pydantic-core | 2.14.3, 2.50.4 | MIT |
| httpx2, httpcore2 | 2.16.0 | BSD-3-Clause |
| anyio | 4.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| jiter | 0.19.0 | MIT |
| sniffio | 1.3.1 | MIT or Apache-2.0 |
| h11 | 0.16.0 | MIT |
| truststore | 0.10.5 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| docstring_parser | 0.18.0 | MIT |
| opentelemetry-api | 1.45.2 | Apache-2.0 |

Qt / PySide6 wird unter der LGPL-3.0 genutzt (dynamisch geladen, unverändert). / Qt / PySide6 is used under the
LGPL-3.0 (dynamically loaded, unmodified).

Die installierte .exe wird mit **PyInstaller** gebaut (GPL-2.0 mit Ausnahme für damit gebaute Programme) und das
Setup mit **Inno Setup** (eigene, freie Lizenz). / The installed .exe is built with **PyInstaller** (GPL-2.0 with an
exception for programs built with it), the setup with **Inno Setup** (its own free license).

