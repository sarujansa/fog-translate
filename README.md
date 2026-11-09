# Fog Translate

Live-Übersetzung des **Dead by Daylight**-Chats. Du markierst einmal den Chat-Bereich; sobald dort neue Zeilen
stehen, liest ein KI-Modell sie (jede Schrift: Kyrillisch, Koreanisch, Japanisch, Chinesisch, Latein mit
Akzenten …), erkennt die Sprache und übersetzt sie. Die Übersetzung erscheint in einem kleinen, klickdurchlässigen Fenster
direkt über dem Chat.

Eigenständiges Programm, unabhängig von [Fog Scout](https://github.com/sarujansa/fog-scout) – beide laufen
nebeneinander.

## Was das Programm tut – und was nicht

- Liest **nur Bildschirmpixel** des markierten Bereichs (wie OBS oder Discord-Bildschirmfreigabe), und nur,
  solange DBD das aktive Fenster ist.
- **Keine Eingaben ans Spiel**, kein Zugriff auf den Spielprozess, keine Spieldateien. Es schreibt nichts in den
  Chat.
- Das Übersetzungsfenster ist von Bildschirmaufnahmen ausgenommen – es taucht nicht in OBS-Aufnahmen, Screenshots
  oder in der Erkennung von Fog Scout auf.
- **Internet:** nur zum gewählten Dienst (siehe unten). Gesendet wird das Bild des markierten Bereichs – **es kann
  Spielernamen und Nachrichten anderer Spieler zeigen** – und die Zielsprache. Nur wenn sich dort etwas geändert
  hat, höchstens alle 3 s (Gemini: 6,5 s), höchstens 300 Anfragen am Tag (einstellbar in `settings.json`).
- API-Keys werden mit Windows-DPAPI verschlüsselt gespeichert, nie im Klartext und nie im Log.

## Dienste

| Dienst | Was du brauchst | Kosten | Daten |
|---|---|---|---|
| **Claude** (Anthropic) | API-Key von https://console.anthropic.com | je Anfrage grob 0,5–1 Cent (Opus), Haiku ein Bruchteil | gehen an Anthropic |
| **Gemini** (Google) | kostenloser API-Key von https://aistudio.google.com/apikey | kostenlose Stufe (ca. 10 Anfragen/min, Tageskontingent) | gehen an Google; in der kostenlosen Stufe darf Google sie zur Produktverbesserung nutzen |
| **Ollama** (lokal) | [Ollama](https://ollama.com) + Bildmodell, z. B. `ollama pull qwen2.5vl:7b` (≈ 6 GB, Grafikkarte ≥ 8 GB) oder `gemma3:4b` | gratis | bleiben auf dem PC |

Bei Ollama spricht das Programm nur mit `127.0.0.1` (Port einstellbar, Standard 11434). „Lokale Modelle laden“
füllt die Liste mit den installierten Modellen.

## Starten

1. Python 3.12–3.14 von python.org installieren.
2. `start.bat` doppelklicken (beim ersten Mal werden die Pakete installiert, alle Versionen fest und per SHA-256
   geprüft).
3. Dienst wählen, API-Key eintragen (nicht bei Ollama), Hinweis bestätigen.
4. DBD öffnen, **Chat-Bereich markieren** (Rahmen um den Chat aufziehen, Esc bricht ab), **Starten**.

Test ohne Spiel: `.venv\Scripts\python -m fogtranslate --test chat.png [--service gemini]` übersetzt einen
Bildausschnitt einmal. Keys gehen auch über `ANTHROPIC_API_KEY` bzw. `GEMINI_API_KEY`.

## Wenn etwas nicht stimmt

- **„Letzten Ausschnitt zeigen“** zeigt genau das Bild, das zuletzt verschickt wurde. Sind Zeilen rechts
  abgeschnitten, den Bereich neu markieren – etwas breiter als der Chat.
- Log: `%LOCALAPPDATA%\FogTranslate\fogtranslate.log`, bei einem Absturz zusätzlich `crash.txt`.

## Einstellungen

`%LOCALAPPDATA%\FogTranslate\settings.json` (Log: `fogtranslate.log` daneben).
