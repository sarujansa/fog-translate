# Fog Translate

Live-Übersetzung des **Dead by Daylight**-Chats. Du markierst einmal den Chat-Bereich; sobald dort neue Zeilen
stehen, liest Claude sie (jede Schrift: Kyrillisch, Koreanisch, Japanisch, Chinesisch, Latein mit Akzenten …),
erkennt die Sprache und übersetzt sie. Die Übersetzung erscheint in einem kleinen, klickdurchlässigen Fenster
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
- **Internet:** nur zu Anthropic (`api.anthropic.com`), mit deinem eigenen API-Key. Gesendet wird das Bild des
  markierten Bereichs – **es kann Spielernamen zeigen** – und die Zielsprache. Nur wenn sich dort etwas geändert
  hat, höchstens alle 3 s, höchstens 300 Anfragen am Tag (einstellbar in `settings.json`).
- Der API-Key wird mit Windows-DPAPI verschlüsselt gespeichert, nie im Klartext und nie im Log.

## Starten

1. Python 3.12–3.14 von python.org installieren.
2. `start.bat` doppelklicken (beim ersten Mal werden die Pakete installiert, alle Versionen fest und per SHA-256
   geprüft).
3. API-Key von https://console.anthropic.com eintragen, Hinweis bestätigen.
4. DBD öffnen, **Chat-Bereich markieren** (Rahmen um den Chat aufziehen, Esc bricht ab), **Starten**.

Test ohne Spiel: `.venv\Scripts\python -m fogtranslate --test chat.png` übersetzt einen Bildausschnitt einmal.

## Kosten

Je Anfrage ein Bild des Chat-Bereichs + kurze Antwort. Mit Claude Opus 5.5 grob 0,5–1 Cent, mit Claude Haiku 5.5
ein Bruchteil davon. Das Fenster zeigt die geschätzte Summe des Monats.

## Einstellungen

`%LOCALAPPDATA%\FogTranslate\settings.json` (Log: `fogtranslate.log` daneben).
