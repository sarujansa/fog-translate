<img src="assets/logo.png" alt="" width="96" align="right">

# Fog Translate

*Deutsch: [README.md](README.md)*

Live translation of the **Dead by Daylight** chat. You mark the chat area once; whenever new lines appear there,
an AI model reads them (any script: Cyrillic, Korean, Japanese, Chinese, Latin with accents …), detects the
language and translates them. The translation appears in a small click-through window right above the chat.

A standalone program, independent of [Fog Scout](https://github.com/sarujansa/fog-scout) – both can run side by
side. Unofficial fan tool, not affiliated with Behaviour Interactive.

## How it works

1. **Mark chat area** takes a still picture of the DBD window; you drag a box around the chat and click **Save**.
   The area is stored relative to the game window, so it survives another window size.
2. After **Start**, the program looks at that area about once a second (screen pixels only).
3. It compares only the **text** in the area (bright, sharp strokes on the dark chat panel), so the moving lobby
   behind the chat does not count. When the text has changed, the picture of the area is sent to the chosen
   service – at most every 3 s (Gemini: 6.5 s) and at most 300 times a day.
4. The service reads every message, joins wrapped lines, detects the language and translates it into your target
   language, returning name, original, language and translation.
5. Messages already shown are recognised and not shown again; a better reading of a message replaces the old one.
6. Foreign messages appear in the overlay above the chat (language, name, translation, original in small print)
   and in the list in the main window. The overlay fades after 25 s without anything new.

## What it does – and what it doesn't

- Reads **only screen pixels** of the marked area (like OBS or Discord screen sharing). With DBD in the background
  only while no other window covers the chat (can be turned off).
- **No input to the game**, no access to the game process, no game files. It never writes into the chat.
- The translation window is visible in screenshots and recordings; tick "Hide the translation in screenshots and
  recordings" if you don't want that. The program never reads its own translations.
- **Internet:** only the chosen service (see below). Sent are the picture of the marked area – **it can show other
  players' names and messages** – and the target language.
- API keys are stored encrypted with Windows DPAPI, never in plain text and never in the log.

## Services

| Service | What you need | Cost | Data |
|---|---|---|---|
| **Claude** (Anthropic) | API key from https://console.anthropic.com | roughly 0.5–1 cent per request (Opus), Haiku a fraction of that | sent to Anthropic |
| **Gemini** (Google) | free API key from https://aistudio.google.com/apikey | free tier (about 10 requests/min, daily quota; availability depends on your region) | sent to Google; on the free tier Google may use it to improve its products |
| **Ollama** (local) | [Ollama](https://ollama.com) + a vision model, e.g. `ollama pull qwen2.5vl:7b` (≈ 6 GB, GPU with 8 GB+) or `gemma3:4b` | free | stays on your PC |

With Ollama the program only talks to `127.0.0.1` (port configurable, default 11434). "Load local models" fills
the list with your installed models.

## Getting started

1. Install Python 3.12–3.14 from python.org.
2. Download this repository (green **Code** button → **Download ZIP**, or `git clone`) and double-click
   `start.bat` (the first start installs the packages; every version is pinned and checked by SHA-256).
3. Choose a service, paste your API key (not needed for Ollama), confirm the notice.
4. Open DBD (lobby with the chat visible), **Mark chat area**: drag a box around the whole chat (a little wider
   than the longest line), **Save**. Then **Start**.

Test without the game: `.venv\Scripts\python -m fogtranslate --test chat.png [--service gemini]` translates one
picture once. Keys can also come from `ANTHROPIC_API_KEY` or `GEMINI_API_KEY`.

## Updates

**Check for updates** (bottom right) – the program asks GitHub only when you click it.

- Installed with `git clone`: shows whether there is something new; **Update and restart** fetches it (only if
  nothing in the folder was changed) and restarts. `start.bat` installs changed packages automatically.
- Installed from a ZIP: shows the new version number and opens the download page.

## If something is wrong

- **Show last capture** shows exactly the picture that was sent last. If lines are cut off, mark the area again –
  a little wider than the chat.
- The status line says when the marked area shows no text.
- Log: `%LOCALAPPDATA%\FogTranslate\fogtranslate.log`, after a crash also `crash.txt`. Settings:
  `settings.json` in the same folder.

## License

Using the program and sharing it **unmodified** is allowed (best: share the link to this repository). **Modifying
it or publishing modified versions requires my written permission** – just ask in a GitHub issue. Unofficial fan
tool, use at your own risk. Details: [LICENSE](LICENSE), libraries: [THIRD_PARTY.md](THIRD_PARTY.md).
