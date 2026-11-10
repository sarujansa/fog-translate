<img src="assets/logo.png" alt="" width="96" align="right">

# Fog Translate

*English: [README.en.md](README.en.md)*

Live-Übersetzung des **Dead by Daylight**-Chats. Du markierst einmal den Chat-Bereich; sobald dort neue Zeilen
stehen, liest ein KI-Modell sie (jede Schrift: Kyrillisch, Koreanisch, Japanisch, Chinesisch, Latein mit
Akzenten …), erkennt die Sprache und übersetzt sie. Die Übersetzung erscheint in einem kleinen, klickdurchlässigen Fenster
direkt über dem Chat.

Eigenständiges Programm, unabhängig von [Fog Scout](https://github.com/senisinx/fog-scout) – beide laufen
nebeneinander.

## So funktioniert es

1. **Mark chat area** macht ein Standbild des DBD-Fensters; du ziehst einen Rahmen um den Chat und klickst **Save**.
   Der Bereich wird relativ zum Spielfenster gespeichert und passt auch bei anderer Fenstergröße.
2. Nach **Start** schaut das Programm zweimal pro Sekunde auf diesen Bereich (nur Bildschirmpixel).
3. Verglichen wird nur die **Schrift** im Bereich (helle, scharfe Striche auf dem dunklen Chat-Feld) – die bewegte
   Lobby dahinter zählt nicht. Hat sich die Schrift geändert, geht das Bild des Bereichs an den gewählten Dienst –
   höchstens alle 2 s (Gemini: 6,5 s), höchstens 300-mal am Tag (einstellbar: „Daily limit“). Geschickt wird nur der
   Streifen mit den neuen Zeilen – das Programm erkennt, wie weit der Chat gescrollt ist.
4. Der Dienst liest jede Nachricht, fügt umgebrochene Zeilen zusammen, erkennt die Sprache und übersetzt in deine
   Zielsprache; zurück kommen Name, Original, Sprache und Übersetzung.
   Läuft der Chat schnell, hebt das Programm Zwischenbilder auf und schickt sie gestapelt mit der nächsten Anfrage,
   damit keine Nachricht verloren geht, die schon aus dem Feld gescrollt ist.
5. Schon gezeigte Nachrichten werden erkannt und nicht doppelt gezeigt; eine bessere Lesung ersetzt die alte.
6. Fremdsprachige Nachrichten erscheinen im Overlay über dem Chat (Sprache, Name, Übersetzung, Original klein) und
   in der Liste im Hauptfenster. Das Overlay blendet nach 25 s ohne Neues aus.

## Was das Programm tut – und was nicht

- Liest **nur Bildschirmpixel** des markierten Bereichs (wie OBS oder Discord-Bildschirmfreigabe). Ist DBD im
  Hintergrund, nur solange kein anderes Fenster über dem Chat liegt (abschaltbar; im Zweifel gilt der Chat als verdeckt).
- **Keine Eingaben ans Spiel**, kein Zugriff auf den Spielprozess, keine Spieldateien. Es schreibt nichts in den
  Chat.
- Das Übersetzungsfenster ist in Screenshots und Aufnahmen sichtbar; wer das nicht will, setzt das Häkchen
  „Hide the translation in screenshots and recordings“. Das Programm liest seine eigene Übersetzung nie mit.
- Die Oberfläche ist Englisch.
- **Internet:** nur zum gewählten Dienst (siehe unten). Gesendet wird das Bild des markierten Bereichs – **es kann
  Spielernamen und Nachrichten anderer Spieler zeigen** – und die Zielsprache. Nur wenn sich dort etwas geändert
  hat, höchstens alle 2 s (Gemini: 6,5 s), höchstens 300 Anfragen am Tag (einstellbar im Fenster: „Daily limit“, 10–5000; danach Pause bis Mitternacht).
- Ein Cloud-Dienst sendet erst, wenn sein Hinweis bestätigt ist – auch beim Wechsel des Dienstes während des
  Laufens (sonst stoppt das Programm). Antworten, die der Dienst berechnet, aber nicht lesbar sind, zählen
  zum Tageslimit.
- API-Keys werden mit Windows-DPAPI verschlüsselt gespeichert, nie im Klartext und nie im Log.

## Dienste

Am schnellsten übersetzen **Claude Haiku 5.5** und **Gemini Flash-Lite**; Claude Opus 5.5 liest schwierige
Schriften am zuverlässigsten, braucht aber länger.

| Dienst | Was du brauchst | Kosten | Daten |
|---|---|---|---|
| **Claude** (Anthropic) | API-Key von https://console.anthropic.com | je Anfrage grob 0,5–1 Cent (Opus), Haiku ein Bruchteil | gehen an Anthropic |
| **Gemini** (Google) | kostenloser API-Key von https://aistudio.google.com/apikey | kostenlose Stufe (ca. 10 Anfragen/min, Tageskontingent; Verfügbarkeit je nach Region) | gehen an Google; in der kostenlosen Stufe darf Google sie zur Produktverbesserung nutzen |
| **Ollama** (lokal) | [Ollama](https://ollama.com) + Bildmodell, z. B. `ollama pull qwen2.5vl:7b` (≈ 6 GB, Grafikkarte ≥ 8 GB) oder `gemma3:4b` | gratis | bleiben auf dem PC |

Bei Ollama spricht das Programm nur mit `127.0.0.1` (Port einstellbar, Standard 11434), auch an einem
eingestellten Proxy vorbei – das Bild verlässt den PC nicht. „Load local models“
füllt die Liste mit den installierten Modellen.

## Installieren

**Einfach:** Unter [Releases](https://github.com/senisinx/fog-translate/releases/latest) die Datei
`FogTranslate-Setup-<Version>.exe` laden und starten – keine Admin-Rechte, kein Python nötig. Das Setup ist nicht
signiert: Windows SmartScreen fragt beim ersten Start (Weitere Informationen → Trotzdem ausführen). Updates:
**Check for updates** zeigt eine neue Version und öffnet die Release-Seite; das neue Setup installiert über die
alte Fassung, Einstellungen und Keys bleiben.

**Aus dem Quelltext:**

1. Python 3.12–3.14 von python.org installieren.
2. `start.bat` doppelklicken (beim ersten Mal werden die Pakete installiert, alle Versionen fest und per SHA-256
   geprüft).
3. Beim ersten Start führt der **Einrichtungs-Assistent** durch Dienst, API-Key (mit Test) und Hinweis – später
   jederzeit über „Setup assistant“. Der Key wird nie im Installer abgefragt, sondern im Programm und dort sofort
   verschlüsselt gespeichert.
4. DBD öffnen (Lobby mit sichtbarem Chat), **Mark chat area**: das Programm zeigt ein Standbild des Spiels – Rahmen um
   den ganzen Chat ziehen (etwas breiter als die längste Zeile), **Save**. Dann **Start**.

Test ohne Spiel: `.venv\Scripts\python -m fogtranslate --test chat.png [--service gemini]` übersetzt einen
Bildausschnitt einmal. Keys gehen auch über `ANTHROPIC_API_KEY` bzw. `GEMINI_API_KEY`.

## Bedienung

- **Test service** prüft Key, Modell und Dienst mit einem erfundenen Beispiel-Chat und zeigt die Antwortzeit.
- **Overlay:** Schriftgröße und Anzeigedauer im Fenster. **Strg+Alt+T** blendet die Übersetzungen aus und wieder ein
  (auch über das Symbol im Infobereich).
- **Infobereich (Tray):** Fenster zeigen, Start/Stop, Übersetzungen aus/ein, Beenden. Mit „Keep running in the tray
  when I close the window“ läuft das Programm weiter, wenn du das Fenster schließt.
- Unten steht, wie lange die letzte Antwort gebraucht hat.

## Updates

Knopf **Check for updates** unten rechts – das Programm fragt GitHub nur auf diesen Klick.

- Mit `git clone` installiert: zeigt, ob es Neues gibt; **Update and restart** holt es (nur wenn im
  Ordner nichts geändert wurde) und startet neu. `start.bat` installiert geänderte Pakete dabei automatisch. Ein Klon
  unter dem alten GitHub-Kontonamen wird dabei auf `github.com/senisinx/fog-translate` umgestellt.
- Als ZIP installiert: zeigt die neue Versionsnummer und öffnet die Download-Seite.

## Wenn etwas nicht stimmt

- **Show last capture** zeigt genau das Bild, das zuletzt verschickt wurde. Sind Zeilen rechts
  abgeschnitten, den Bereich neu markieren – etwas breiter als der Chat.
- Log: `%LOCALAPPDATA%\FogTranslate\fogtranslate.log`, bei einem Absturz zusätzlich `crash.txt`.

## Einstellungen

`%LOCALAPPDATA%\FogTranslate\settings.json` (Log: `fogtranslate.log` daneben).

## Lizenz / License

Nutzen und **unverändert** weitergeben ist erlaubt (am besten den Link zu diesem Repository teilen).
**Bearbeiten, Verändern und das Veröffentlichen veränderter Fassungen nur mit meiner schriftlichen Erlaubnis** –
frag einfach per GitHub-Issue. Inoffizielles Fan-Tool, Nutzung auf eigene Gefahr. Details: [LICENSE](LICENSE),
Bibliotheken: [THIRD_PARTY.md](THIRD_PARTY.md).

Use and sharing the **unmodified** program is allowed (best: share the link to this repository). **Modifying it or
publishing modified versions requires my written permission** – just ask in a GitHub issue. Unofficial fan tool,
use at your own risk. Details: [LICENSE](LICENSE), libraries: [THIRD_PARTY.md](THIRD_PARTY.md).

