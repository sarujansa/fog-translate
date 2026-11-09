# Fog Translate – Projektkontext für Claude Code

Live-Übersetzung des Dead-by-Daylight-Chats (Windows). Der Nutzer markiert den Chat-Bereich; bei neuen, ruhigen
Zeilen schickt das Programm das Bild des Bereichs an den gewählten Dienst – Claude, Gemini oder lokal Ollama (liest +
erkennt Sprache + übersetzt in einem Schritt)
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
- **Netz nur zum gewählten Übersetzungsdienst** (`claude.py` → api.anthropic.com über das SDK, `gemini.py` →
  `gemini.HOST`, Key nur im Header `x-goog-api-key`, nie in der URL; `ollama.py` → nur `127.0.0.1`, `HOST` fest,
  nur der Port einstellbar); HTTP nur über `http.py` (keine Weiterleitungen, Antwort ≤ `MAX_BYTES`). Gesendet nur
  das Bild des Bereichs (PNG im Speicher, nie als Datei) und die Zielsprache. Vor dem ersten Start eines
  Cloud-Dienstes bestätigt der Nutzer, dass das Bild Spielernamen/Nachrichten anderer zeigen kann (`accepted` je
  Dienst; bei Gemini mit Hinweis auf die Datennutzung der kostenlosen Stufe). Grenzen: `min_gap_s`, `daily_cap`, nur bei geändertem + ruhigem Bild
  (`change.ChangeGate`), Gemini ≥ `engine.SERVICE_GAP_S`, nach „Limit erreicht“ `QUOTA_WAIT_S` Pause.
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
| `translate.py` | Gemeinsames aller Dienste: `SYSTEM`, `SCHEMA`, `LANGUAGES`, `png_bytes`, `parse`/`answer_lines`, `TranslateError.kind`, `Worker`-Thread |
| `claude.py`, `gemini.py`, `ollama.py`, `services.py`, `http.py` | Dienste (je `Translator.request(img) → Result`): Claude per SDK (`MODELS`, `cost_usd`, Fallbacks), Gemini per REST (`responseJsonSchema`, einmal Rückfall auf `responseSchema`), Ollama lokal (`format` = Schema, `installed_models`); `services.make(settings)`, `SERVICES`, `KEY_SETTING`/`MODEL_SETTING`; `http.request` (Standardbibliothek) |
| `engine.py`, `looper.py` | Schleife ohne Qt: `look` (nur DBD vorn), `_try_send` (Abstand, Tageslimit), `answer`, `visible`, `last_sent` (nur Speicher, „Letzten Ausschnitt zeigen“); ein `RLock`, weil zwei Threads. `Looper` = Blick-Thread: baut den Übersetzer (SDK-Import dauert unter Windows Sekunden) und macht Fenster suchen/Aufnahme/Vergleich – **nie im Fenster-Thread**; meldet `started`/`start_failed`/`tick`/`answer` über die Queue |
| `window.py`, `grab.py` | DBD-Fenster (nur Fensterinfos; Titel mit festem Puffer, keine Längenabfrage, die eine Nachricht schicken könnte), mss-Ausschnitt |
| `secret.py`, `config.py` | DPAPI, `Settings` in `%LOCALAPPDATA%\FogTranslate` (`FOGTRANSLATE_DATA_DIR` in Tests; Keys je Dienst `api_key(service)`, `accepted(service)`, übernimmt 0.1-Schlüssel) |
| `overlay.py`, `picker.py`, `app.py`, `__main__.py` | Übersetzungsfenster (klickdurchlässig, von Aufnahmen ausgenommen), Bereich markieren, Steuerfenster (Thread → Fenster nur über `queue` + QTimer, nie Qt-Signal aus Threads), Start/`--test`; `__main__._log_setup`: Log, unbehandelte Fehler aller Threads ins Log, `faulthandler` → `crash.txt` |

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
