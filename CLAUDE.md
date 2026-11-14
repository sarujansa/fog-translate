# Fog Translate – Projektkontext für Claude Code

Live-Übersetzung des Dead-by-Daylight-Chats (Windows). Der Nutzer markiert den Chat-Bereich; bei neuen, ruhigen
Zeilen schickt das Programm das Bild des Bereichs an den gewählten Dienst – Claude, Gemini oder lokal Ollama (liest +
erkennt Sprache + übersetzt in einem Schritt)
und zeigt neue fremdsprachige Zeilen in einem klickdurchlässigen Fenster über dem Chat. Eigenständig, unabhängig
von Fog Scout (`senisinx/fog-scout`); Code daraus darf kopiert werden (gleicher Autor). Oberfläche **Englisch, Italienisch, Russisch, Chinesisch (vereinfacht), Japanisch, Koreanisch** (0.6 nur Englisch; 0.10 Wunsch des Nutzers; kein Deutsch), Doku Deutsch,
Code und Kommentare Englisch.

**Lizenz** (Wunsch des Nutzers, 0.7.4): eigene Bedingungen in `LICENSE` – nutzen und unverändert kostenlos
weitergeben erlaubt, Bearbeiten/veränderte Fassungen nur mit schriftlicher Erlaubnis, kein Verkauf. Neue
Abhängigkeiten in `THIRD_PARTY.md` eintragen (Wächter `test_every_package_is_listed_in_third_party`).

## Harte Regeln (nicht verhandelbar)

- **Keine Eingaben ans Spiel** (kein SendInput/PostMessage, keine Tastatur-/Maus-Simulation), nichts in den Chat
  schreiben.
- **Kein Zugriff auf den Spielprozess** (kein OpenProcess, kein Speicherlesen, keine PID-Abfragen) und keine
  Spieldateien. Erlaubt: Bildschirmpixel (mss), Fensterinfos (Klasse `UnrealWindow`, Titel, Position,
  Vordergrund, Z-Reihenfolge/Stil/Lage der Fenster darüber), `SetWindowDisplayAffinity` nur auf eigenen Fenstern. Nie `PrintWindow`.
- Gelesen wird nur der markierte Bereich. Mit DBD im Vordergrund immer; mit DBD im Hintergrund nur bei
  `read_background` (Standard an, Wunsch des Nutzers) **und** wenn kein anderes Fenster über dem Bereich liegt
  (`window.region_free` → `windows_above`/`overlaps`, nur Fensterinfos) – sonst würde das Bild eines anderen
  Programms verschickt. Ohne Prüfung gilt der Bereich als verdeckt (`engine.look`), ebenso wenn `windows_above` nicht bis oben kommt (`None`).
- Das Übersetzungsfenster ist in Screenshots/Aufnahmen sichtbar (Wunsch des Nutzers); das Programm liest es nie
  mit: der Blick-Thread schwärzt `overlay.rect_on_screen` im Ausschnitt (`grab.blank`). Ausblenden nur mit
  `hide_in_captures` (`SetWindowDisplayAffinity` nur auf dem eigenen Fenster).
- **Netz nur zum gewählten Übersetzungsdienst** (`claude.py` → `claude.URL` auf api.anthropic.com, Key nur im Header `Authorization`, `gemini.py` →
  `gemini.HOST`, Key nur im Header `x-goog-api-key`, nie in der URL; `ollama.py` → nur `127.0.0.1`, `HOST` fest,
  nur der Port einstellbar, nie über einen Proxy: `http._opener` mit leerem `ProxyHandler` für `LOCAL_HOSTS`); HTTP nur über `http.py` (keine Weiterleitungen, Antwort ≤ `MAX_BYTES`). Gesendet nur
  das Bild des Bereichs (PNG im Speicher, nie als Datei) und die Zielsprache. Vor dem ersten Start eines
  Cloud-Dienstes (auch beim Wechsel während des Laufens: `_start_worker` stoppt sonst, Status `unconfirmed`) bestätigt der Nutzer, dass das Bild Spielernamen/Nachrichten anderer zeigen kann (`accepted` je
  Dienst; bei Gemini mit Hinweis auf die Datennutzung der kostenlosen Stufe). Grenzen: `min_gap_s`, `daily_cap` (im Fenster einstellbar, 10–5000, `NoWheelSpinBox`; Anhebung nach erreichtem Limit liest weiter; Anzeige „Today n / cap“), nur bei geändertem + ruhigem Bild
  (`change.ChangeGate`), Gemini ≥ `engine.SERVICE_GAP_S`; das Tageslimit zählt laufende Anfragen (`_open`) und berechnete Fehlantworten (`BILLED_ERRORS`) mit; nach „Limit erreicht“ `QUOTA_WAIT_S` Pause; nach einer Antwort ohne jede Nachricht `EMPTY_WAIT_S`, je Wiederholung verdoppelt bis `EMPTY_MAX_S`.
- **Updates nur auf Klick** („Nach Updates suchen“, `update.py`): Git-Installation `git fetch origin main` (davor nur ein `origin` unter dem alten Kontonamen auf `REPO_URL` umstellen; ohne
  Hooks, ohne Passwortabfrage), dann nur Fast-Forward – nie bei geänderten Dateien, anderem Zweig oder eigenen
  Commits; Neustart über `start.bat`. ZIP-Installation: nur die Versionszeile von `update.VERSION_URL` lesen und die
  Seite öffnen, nichts herunterladen. Nichts über den Nutzer senden. `start.bat` → `deps.py` installiert Pakete neu,
  wenn sich `requirements.txt` geändert hat (SHA-256 in `.venv\requirements.sha256`).
- **.exe/Setup** (0.8): `installer/fogtranslate.spec` (PyInstaller 6.22.3 fest, `requirements-build.txt` mit
  SHA-256), `installer/fogtranslate.iss` (Inno Setup 7.1.1 fest + Prüfsumme, nur für den Benutzer, keine
  Admin-Rechte, `{localappdata}\Programs\Fog Translate`). `.github/workflows/build.yml`: Bau, `--selftest` der .exe,
  Setup still installieren/prüfen/deinstallieren; Job `release` (einziger mit `contents: write`/`id-token`/`attestations`, Herkunftsnachweis per
  `attest-build-provenance`) nur bei Push auf `main` und nur wenn es `v<Version>` noch nicht gibt. **Die .exe aktualisiert sich auf Klick selbst** (0.10, vom Nutzer
  freigegeben; bis 0.9.8 nur Download-Seite), `relupdate.py`, drei Klicks auf denselben Knopf, nie von selbst: „Check for updates“ liest nur `relupdate.API`
  (neuestes Release dieses Repos), „Download update“ lädt das Setup nur von `DOWNLOAD_PREFIX`, ≤ `MAX_BYTES`, nach `data_dir/update` und behält es nur bei passender SHA-256
  (`.sha256`-Datei und, falls gelistet, GitHubs Digest – beide müssen stimmen), „Install and restart“ prüft Name/Ordner/SHA-256 erneut (`setup_still_ours`), startet
  das Setup mit `install_args` (`/update=1`) und beendet das Programm. Weiterleitungen nur auf HTTPS (`_HttpsOnly`), keine Konten/Tokens. Das Setup wartet bei `/update=1` auf den Mutex
  `relupdate.MUTEX_NAME` (`[Code] InitializeSetup`, ≤ 60 s), startet die neue Version (`[Run] Check: IsUpdate`) und nach einem Abbruch die alte (`DeinitializeSetup`). Setup und
  Programmordner gehören demselben Benutzer (keine Admin-Rechte) – daher keine Kopie in einen geschützten Ordner wie bei Fog Scout.
- **Hotkey** (0.9, `hotkey.py`): nur `RegisterHotKey` für die eine eingestellte Kombination (`hide_hotkey`, Standard
  Strg+Alt+T; braucht Strg/Alt/Win oder eine F-Taste) – Windows meldet sie dem eigenen Programm über Qts nativen
  Ereignisfilter. Kein Tastatur-Hook, kein Lesen anderer Tasten, nichts ans Spiel.
- **„Test service“** schickt nur das erfundene Beispielbild `translate.sample_picture` (nie den Bildschirm), bei
  Cloud-Diensten erst nach bestätigtem Hinweis; zählt als Anfrage.
- API-Key nur DPAPI-verschlüsselt (`secret.py`), nie Klartext, nie ins Log; ohne DPAPI nur für die Sitzung.
- Antworten des Dienstes nur als Klartext anzeigen, Steuerzeichen/Bidi entfernt (`translate.parse`).
- Wächter: `tests/test_guards.py`. Neue Features, die gegen diese Regeln verstoßen: nachfragen.

## Setup des Nutzers

Samsung G5 3440×1440, DBD (Steam/Epic/MS Store) im Fenster-Vollbild. Im Match rendert DBD 16:9 = 2560×1440
zentriert (Balken je 440 px), **Lobby, Menüs und Ergebnisbildschirm nutzen aber die volle Breite** – der Chat sitzt
dort rechts vom 16:9-Bild (x ≈ 2800–3280). Bereiche daher relativ zum **ganzen Spielfenster**
(`geometry.window_space`, `region_space` = "window"), nie auf 16:9 beschneiden (bis 0.7 endete jeder Rahmen bei
x = 3000; ältere Bereiche werden verworfen). Win32 und mss rechnen in
physischen Pixeln, Qt bei Windows-Skalierung > 100 % in logischen (physisch / Faktor): **jede** Stelle, an der ein
Bildschirm-Rechteck ein Qt-Fenster trifft, rechnet über `qtgeom` (`ratio`, `to_qt`, `from_qt`) – Overlay, Bildschirmfläche
(Sarus Test 09.11.2026: abgeschnittene Zeilen). Markiert wird seit 0.7 auf einem **Standbild** des Spielfensters in
einem normalen Fenster (`picker.RegionPicker`): Bildpixel = Bildschirmpixel, kein Fenster über dem Spiel (über DBD
kamen die Klicks beim Nutzer nicht an). `QT_ENABLE_HIGHDPI_SCALING=0` bleibt zusätzlich.

## Architektur (fogtranslate/)

| Datei | Aufgabe |
|---|---|
| `geometry.py` | (rein) `window_space` (Raum der Bereiche = ganzes Spielfenster), `viewport` (16:9, nur noch Hilfsfunktion), `to_relative`/`from_relative`, `valid_region`, `overlay_spot` |
| `change.py` | (rein) `ChangeGate` vergleicht nur **Schrift** (`text_mask`: hell, scharfe Kante, dunkles Chat-Feld daneben, ohne lange gerade Linien), nie rohe Pixel – die Lobby bewegt sich ständig (Sarus Test 09.11.2026: nie gesendet). Anfrage bei geänderter Schrift (`MIN_CHANGED_PX`/`CHANGED_SHARE`), wenn `SETTLE_LOOKS` ruhig oder nach `MAX_WAIT_LOOKS`; nicht unter `MIN_TEXT_PX`; `stats` für den Status. **Kein Chat = nichts senden** (0.9.8, Sarus Test 10.11.2026: Lobby-Szene hinter geschlossenem Chat lief als Dauer-Anfrage): `chat_like` – Schrift liegt in niedrigen Zeilenbändern mit Lücken; mehr als `SCENE_SHARE` in Blöcken über `MAX_LINE_ROWS` = Spielbild, wird nie gesendet (`stats["chat"]`). **Nur neue Zeilen** (0.8.2): `new_rows` findet die Scroll-Verschiebung gegen die zuletzt gesendete Schrift (beste Übereinstimmung, ≤ `MAX_LOST`) → `crop_top`, die Engine schickt nur `img[crop_top:]`; ohne sichere Ausrichtung den ganzen Bereich |
| `lines.py` | (rein) `ChatLine`, `same_message` (gleich, Teil des anderen ab `MIN_PART` oder Ähnlichkeit ≥ `SIMILAR`, gleicher oder leerer Absender), `Transcript.add` → (neu, ersetzt): bessere Lesung (länger) ersetzt frühere Bruchstücke an Ort und Stelle, nie doppelt (Sarus Test 09.11.2026: umgebrochene russische Nachricht); eine Lesung, die die alte doppelt enthält (`_repeats`), ersetzt nie |
| `translate.py` | Gemeinsames aller Dienste: `SYSTEM`, `SCHEMA`, `LANGUAGES`, `png_bytes`, `parse`/`answer_lines`, `TranslateError.kind`, `Worker`-Thread |
| `claude.py`, `gemini.py`, `ollama.py`, `services.py`, `http.py` | Dienste (je `Translator.request(img) → Result`): Claude per REST ohne SDK (0.12; Anfrage wie das SDK 2.7.0: `API_VERSION`, `body`/`headers`, Fallbacks, eine Wiederholung `_should_retry`/`_retry_wait`; `MODELS`, `cost_usd`), Gemini per REST (`responseJsonSchema`, einmal Rückfall auf `responseSchema`), Ollama lokal (`format` = Schema, `installed_models`); `services.make(settings)`, `SERVICES`, `KEY_SETTING`/`MODEL_SETTING`; `http.request`/`exchange` (Standardbibliothek; `exchange` mit Antwort-Headern) |
| `engine.py`, `looper.py` | Schleife ohne Qt: `look` (nur DBD vorn), `_try_send` (Abstand, Tageslimit), `answer` (→ geändert ja/nein), `messages` (Liste), `visible` (Overlay: die letzten `KEEP_SHOWN` Übersetzungen, solange innerhalb `show_s` etwas Neues kam – laufender Verlauf, nicht nur die letzte Änderung), `last_counts` (nur Zahlen fürs Log), `last_sent` (nur Speicher, „Letzten Ausschnitt zeigen“); **nur mit Chat** (0.9.7, Wunsch des Nutzers): `chat_seen` = der Bereich zeigt Chat-Zeilen (`change.chat_like`; weg nach `GONE_LOOKS` Blicken ohne, sofort bei kein Spiel/verdeckt/Hintergrund ohne Lesen), `chat_shown()` mit `hide_without_chat` → das Overlay steht nur dann; ein `RLock`, weil zwei Threads. **Schneller Chat** (0.9.1): `_ref` = Schrift des ältesten noch nicht sicheren Bilds; ist der Chat seitdem um `KEEP_AT` gescrollt (`_moved_far` über `change.scroll_shift`), wandert das ungesendete Bild in `_backlog` (≤ `BACKLOG_MAX`) und `_stacked` schickt alle gestapelt (älteste oben, `SEAM`) in einer Anfrage – Simulation `tests/test_burst.py`; neu markiert (`new_area`) oder andere Bildgröße → wartende Bilder verworfen (`_forget`), Zustandswechsel aus dem Fenster nur über Engine-Methoden unter dem Lock. `Looper` = Blick-Thread: baut den Übersetzer und macht Fenster suchen/Aufnahme/Vergleich – **nie im Fenster-Thread**; meldet `started`/`start_failed`/`tick`/`answer` über die Queue |
| `window.py`, `grab.py` | DBD-Fenster (nur Fensterinfos; Titel mit festem Puffer, keine Längenabfrage, die eine Nachricht schicken könnte), mss-Ausschnitt |
| `secret.py`, `config.py` | DPAPI, `Settings` in `%LOCALAPPDATA%\FogTranslate` (`FOGTRANSLATE_DATA_DIR` in Tests; Keys je Dienst `api_key(service)`, `accepted(service)`, übernimmt 0.1-Schlüssel) |
| `update.py`, `deps.py` | Update auf Klick (`check` → `Check.state` current/behind/ahead/dirty/branch/newer/error, vor dem Fetch `move_origin` (nur `origin` unter `OLD_OWNER` → `REPO_URL`), `apply` = `merge --ff-only`, `restart`), Pakete nach Update (`needed`, `main`, nur Standardbibliothek) |
| `qtgeom.py` | Physische ↔ Qt-Pixel (`ratio` = devicePixelRatio des Hauptbildschirms) |
| `wizard.py` | Einrichtungs-Assistent beim ersten Start (`wanted`: nie beendet/übersprungen **und** kein Key **und** kein Bereich; `SetupWizard`: Dienst + Zielsprache → Key/Hinweis/„Test“ → Abschluss; Keys nur über `Settings.set_api_key`, Test nur mit `sample_picture`; Überspringen/× setzt `setup_done`); Hauptfenster: `open_setup`/`_setup_done`, Knopf „Setup assistant“ |
| `i18n.py`, `lang_*.py` | Sprache des Fensters: englischer Text = Schlüssel, `tr("…")`, `N_("…")` für Tabellen (übersetzt beim Anzeigen), Platzhalter `%s`/`%d` in gleicher Reihenfolge; `LANGS`, `ui_language` („auto“ = `system_language`, sonst Englisch), `set_language`. **Jeder neue Text braucht einen Eintrag in allen fünf `lang_<code>.py`** (`tests/test_i18n.py`: vollständig, gleiche Platzhalter, kein Markup, Namen unverändert). Wechsel im Fenster/Assistenten baut den Inhalt neu (`MainWindow.rebuild`, `SetupWizard._language_changed`); Log bleibt wie es ist. Setup: `[Languages]` in der .iss, je Sprache die Nutzungsbedingungen `installer/terms/terms_<code>.txt` (UTF-8 mit BOM; en/de = die beiden Hälften von `LICENSE`, bei Änderung an `LICENSE` mitziehen und die fünf Übersetzungen anpassen – sie nennen den englischen Text als maßgeblich; Wächter `test_the_setup_shows_the_terms_in_the_chosen_language`) |
| `theme.py` | Hell/Dunkel (`theme` = auto/light/dark): „auto“ = wie Qt es für Windows zeigt; sonst Fusion + eigene Palette (`DARK`/`LIGHT`) und `setColorScheme` für die Titelleiste; `HISTORY` = Farben der Nachrichtenliste je Aussehen (Kontrast im Test); das Overlay behält sein eigenes dunkles Design |
| `relupdate.py` | Update der installierten .exe aus den GitHub-Releases (harte Regel oben): `parse_release`, `check`, `download`, `setup_still_ours`, `start_setup` (ohne PyInstaller-Variablen, Windows-DLL-Suche), `clean_update_folder` beim Start, `claim_mutex`; im Fenster `_update_button`, `_release_checked`/`_release_download`/`_release_install`; Tests mit `FakeGitHub` |
| `hotkey.py` | `parse` („Ctrl+Alt+T“ → Modifikatoren, Taste), `message_id` (WM_HOTKEY aus der nativen Nachricht), `Hotkey.start/stop` (RegisterHotKey + Filter, Fehler nie in die Ereignisschleife) |
| `selftest.py` | `--selftest RESULT.json`: Module, Bibliotheken, Fenster offscreen, Logo; JSON, Exit 0 = ok (CI prüft die .exe damit) |
| `icon.py` | Logo aus `fogtranslate/assets/icon-<n>.png` (je Grösse in `SIZES` ein eigenes Bild, bis 32 px die vereinfachte Fassung; `pixmap`/`icon`, Zwischengrössen aus dem nächstgrösseren Bild), `set_app_id` (eigenes Taskleisten-Symbol), `ico_bytes`/`save_ico` (für .exe und Setup, jede Grösse aus ihrem eigenen Bild). Quelle der Bilder: Repo fog-forge `tools/icons/` (gemeinsame Familie mit Fog Forge, Fog Scout, Fog Launch) – dort ändern, herkopieren, dann `tools/export_logo.py` für `assets/logo.png` |
| `overlay.py`, `picker.py`, `app.py`, `__main__.py` | Übersetzungsfenster (klickdurchlässig; je Nachricht Kopfzeile Sprache + Name, Übersetzung, Original klein; Messen und Zeichnen über dieselben `rows`/`_height`), Verlauf `history_html` (alles escaped), Bereich markieren (`app.pick_region`: eigene Fenster weg, nach 350 ms ein mss-Bild des Spielfensters → `RegionPicker(picture, done, current)` mit `Canvas` in Bildpixeln, Save/Cancel/Esc/Enter/×), Steuerfenster (Thread → Fenster nur über `queue` + QTimer, nie Qt-Signal aus Threads; „Test service“ `test_service`/`_tested`, Antwortzeit `last_seconds` in der Kostenzeile und im Log, Schriftgröße/Anzeigedauer `_look_changed`, Tray `setup_tray` + `close_to_tray`, `toggle_overlay`/`overlay_hidden`; Autostart `auto_start` → `can_auto_start`/`auto_start_now` beim Öffnen und nach dem Markieren – nur wenn ein Klick auf Start ginge: Bereich, bestätigter Hinweis, Key; `setQuitOnLastWindowClosed(False)`, `closeEvent` beendet), **Bedienung** (0.11, Wunsch des Nutzers „benutzerfreundlich“): oben Status mit Punkt (`DOT`) und der nächste Schritt (`HINTS`, `next_step` → notice/key/region, `hint_btn` „Show me“ → `_go`), der Knopf für den nächsten Schritt blau (`NEXT_STYLE`, `_look`); Reiter `tabs`: Translations / Service (`service_tab`) / Options; `toggle` startet nie ins Leere – `_guide` führt zum fehlenden Schritt, ohne Bereich `pick_region` und Start danach (`_start_after_pick`), getippter Key wird übernommen (`_take_typed_key`); Meldungen nur über `_say` (die Statuszeile wird 5× je Sekunde neu geschrieben); „Preview“ `preview_overlay` zeigt `preview_lines` (erfunden, nichts gelesen/gesendet; echte Übersetzungen gehen vor); **Ort der Übersetzungen** (0.11.1, Frage des Nutzers „wieso kann ich das Overlay nicht bewegen“): `overlay_spot` wie `region` relativ zum Spielfenster, gewählt auf dem Standbild (`pick_spot` → `RegionPicker` mit eigenem Titel/Hinweis → `_spot_picked`; nie ziehbar machen – klickdurchlässig, und über DBD kommen Klicks nicht an), nicht über dem Chat-Bereich (`geometry.touches`, sonst gingen geschwärzte Zeilen verloren), `geometry.placed_spot`, `reset_spot`; Aussehen-Wechsel baut das Fenster neu (`rebuild`, sonst behalten Links die alte Farbe), Start/`--test`; `__main__._log_setup`: Log, unbehandelte Fehler aller Threads ins Log, `faulthandler` → `crash.txt` |

## Starten, Testen

```bat
start.bat
.venv\Scripts\python -m fogtranslate --test chat.png
.venv\Scripts\python -m pytest -q tests
```

Pakete: alle Versionen fest **mit SHA-256** (`tools/hash_requirements.py`), Installation mit `--require-hashes
--only-binary=:all:`; Python 3.12–3.14. CI (`.github/workflows/tests.yml`): pyflakes + pytest unter Linux und Windows.

## Arbeitsweise

Nutzer: Saru, Deutsch, direkt und kritisch. Commits als `senisinx <80452583+senisinx@users.noreply.github.com>`,
ohne Co-Authored-By-/Session-Zeilen, PR-Beschreibungen ohne „Generated by/with Claude Code“ und ohne Sitzungslink. Nach dem Push PR öffnen,
bei grüner CI selbst mergen. Version in `fogtranslate/__init__.py` erhöhen, README anpassen.
