# Fog Translate – Projektkontext für Claude Code

Live-Übersetzung des Dead-by-Daylight-Chats (Windows). Der Nutzer markiert den Chat-Bereich; bei neuen, ruhigen
Zeilen schickt das Programm das Bild des Bereichs an Claude (liest + erkennt Sprache + übersetzt in einem Schritt)
und zeigt neue fremdsprachige Zeilen in einem klickdurchlässigen Fenster über dem Chat. Eigenständig, unabhängig
von Fog Scout (`sarujansa/fog-scout`); Code daraus darf kopiert werden (gleicher Autor). Oberfläche/Doku Deutsch,
Code und Kommentare Englisch.

## Harte Regeln (nicht verhandelbar)

- **Keine Eingaben ans Spiel** (kein SendInput/PostMessage, keine Tastatur-/Maus-Simulation), nichts in den Chat
  schreiben.
- **Kein Zugriff auf den Spielprozess** (kein OpenProcess, kein Speicherlesen, keine PID-Abfragen) und keine
  Spieldateien. Erlaubt: Bildschirmpixel (mss), Fensterinfos (Klasse `UnrealWindow`, Titel, Position,
  Vordergrund), `SetWindowDisplayAffinity` nur auf eigenen Fenstern. Nie `PrintWindow`.
- Gelesen wird nur der markierte Bereich und nur, solange DBD das aktive Fenster ist.
- **Internet nur zum gewählten Übersetzungsdienst** (`translate.py`); gesendet nur das Bild des Bereichs (PNG im
  Speicher, nie als Datei) und die Zielsprache. Vor dem ersten Start bestätigt der Nutzer, dass das Bild
  Spielernamen zeigen kann (`accepted`). Grenzen: `min_gap_s`, `daily_cap`, nur bei geändertem + ruhigem Bild
  (`change.ChangeGate`).
- API-Key nur DPAPI-verschlüsselt (`secret.py`), nie Klartext, nie ins Log; ohne DPAPI nur für die Sitzung.
- Antworten des Dienstes nur als Klartext anzeigen, Steuerzeichen/Bidi entfernt (`translate.parse`).
- Wächter: `tests/test_guards.py`. Neue Features, die gegen diese Regeln verstoßen: nachfragen.

## Setup des Nutzers

Samsung G5 3440×1440, DBD (Steam/Epic/MS Store) im Fenster-Vollbild, rendert 16:9 = 2560×1440 zentriert (Balken je
440 px). Bereiche daher relativ zum 16:9-Viewport (`geometry.viewport`). Qt läuft mit
`QT_ENABLE_HIGHDPI_SCALING=0`, damit Qt-, Win32- und mss-Koordinaten gleich (physische Pixel) sind.

## Architektur (fogtranslate/)

| Datei | Aufgabe |
|---|---|
| `geometry.py` | (rein) `viewport`, `to_relative`/`from_relative`, `valid_region`, `overlay_spot` |
| `change.py` | (rein) `ChangeGate`: Anfrage nur bei geändertem Bild, `SETTLE_LOOKS` ruhig, nicht bei leerem Bereich |
| `lines.py` | (rein) `ChatLine`, `SeenLines` (schon gezeigte Zeilen über `normal()` erkennen) |
| `translate.py` | Claude (SDK `anthropic`, Bild + strukturierte Ausgabe `SCHEMA`, `MODELS`, Kosten `cost_usd`, `parse`, `TranslateError.kind`, `Worker`-Thread) |
| `engine.py` | Schleife ohne Qt: `look` (nur DBD vorn), `_try_send` (Abstand, Tageslimit), `answer`, `visible` |
| `window.py`, `grab.py` | DBD-Fenster (nur Fensterinfos), mss-Ausschnitt |
| `secret.py`, `config.py` | DPAPI, `Settings` in `%LOCALAPPDATA%\FogTranslate` (`FOGTRANSLATE_DATA_DIR` in Tests) |
| `overlay.py`, `picker.py`, `app.py`, `__main__.py` | Übersetzungsfenster (klickdurchlässig, von Aufnahmen ausgenommen), Bereich markieren, Steuerfenster (Thread → Fenster nur über `queue` + QTimer, nie Qt-Signal aus Threads), Start/`--test` |

## Starten, Testen

```bat
start.bat
.venv\Scripts\python -m fogtranslate --test chat.png
.venv\Scripts\python -m pytest -q tests
```

Pakete: alle Versionen fest **mit SHA-256** (`tools/hash_requirements.py`), Installation mit `--require-hashes
--only-binary=:all:`; Python 3.12–3.14. CI (`.github/workflows/tests.yml`): pyflakes + pytest unter Linux und Windows.

## Arbeitsweise

Nutzer: Saru, Deutsch, direkt und kritisch. Commits als `sarujansa <80452583+sarujansa@users.noreply.github.com>`,
ohne Co-Authored-By-/Session-Zeilen, PR-Beschreibungen ohne „Generated with Claude Code“. Nach dem Push PR öffnen,
bei grüner CI selbst mergen. Version in `fogtranslate/__init__.py` erhöhen, README anpassen.
