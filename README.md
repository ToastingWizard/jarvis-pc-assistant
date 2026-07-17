 HEAD
# Tests

Run with:

```
pip install -r requirements-dev.txt
pytest
```

These tests exercise `JarvisEngine` directly rather than the Tkinter
`JarvisUI`, since that's where the actual decision-making logic lives
(wake-word/conversation gating, git push, code review rules) and it can
be tested headlessly without a display. `JarvisUI` stays a thin layer
that wires that logic up to the mic, the window, and the tray icon.

- `test_conversation_window.py` — the wake-word / "singing gets picked
  up as commands" fix.
- `test_push_confirmation.py` — the git push confirmation flow.
- `test_review_safety.py` — tracked-secret-file detection and the
  fix-first-issue safety whitelist.

# JARVIS PC Assistant

A local PC voice assistant for launching apps, opening websites and folders, playing music, running custom modes, reviewing code, and having lightweight butler-style conversation. Windows is the main release target, and source mode also supports Linux.

## AI Setup (Required For Smart Responses)

JARVIS can launch apps and automate tasks without AI.

For smart AI conversations, install Ollama and the Phi-3 Mini model:

1. Install Ollama:
https://ollama.com/download/windows

2. Open PowerShell and run:

```powershell
ollama pull phi3:mini
```

## Features

- Purple desktop control panel with a voice orb and mode shortcuts
- Voice commands like `hey jarvis open chrome`, then natural follow-up commands
- Custom apps, websites, Spotify playlists, folders, and multi-step modes
- Text command box for testing without a microphone
- Optional local AI conversation through Ollama
- Optional Gemini fallback with your own API key
- Minimize-to-tray support
- One-file Windows `.exe` build with PyInstaller
- Linux source-mode support for launching apps, opening links/folders, voice, and code review

## Installation Guide

The easiest way to share JARVIS is through GitHub Releases:

1. Push this project to GitHub.
2. Go to the repository's **Actions** tab.
3. Run **Build Windows EXE** manually, or push a version tag like `v1.0.0`.
4. Download `JARVIS.exe` from the workflow artifact or the GitHub Release.
5. Send friends the release link.

When they launch the exe, JARVIS creates a fresh local `config.json` next to the exe. They can customize everything from the app.

## Run From Source

Install Python 3.10.x -3.13.x dont install 3.14.x cause speach recognition wont work from [python.org](https://www.python.org/downloads/windows/) and enable **Add python.exe to PATH**.

```powershell
py -m pip install -r requirements.txt
py JARVIS_app.py
```

Or double-click:

```text
run_jarvis.bat
```

### Linux Notes

Install Python 3.10-3.13, PortAudio, Tk, and an MP3 player for Edge TTS playback:

```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk portaudio19-dev ffmpeg
python3 -m pip install -r requirements.txt
python3 JARVIS_app.py
```

On Linux, JARVIS uses `xdg-open` for links/folders and normal shell commands for apps. For custom apps, set the target to the Linux command, for example `google-chrome`, `spotify`, `pycharm`, or `/home/you/AppImageName.AppImage`.

## Build The EXE Locally

```powershell
.\build_windows.ps1
```

The finished app will be:

```text
dist\JARVIS.exe
```

## Voice Setup Notes

Voice input uses `SpeechRecognition` and `PyAudio`. If PyAudio refuses to install on Windows, try:

```powershell
python -m pip install pipwin
pipwin install pyaudio
python -m pip install -r requirements.txt
```

For best recognition, use headphones or keep speaker volume low so JARVIS does not hear its own voice.

## Personal Config

Do not commit your real `config.json`. It can contain personal Windows paths, microphone indexes, and API keys. The repo includes `config.example.json` as a safe starter.

If you want to reset your local setup:

```powershell
copy config.example.json config.json
```

## Commands

```text
hey jarvis open chrome
open spotify
play music
play discover weekly playlist
play song blinding lights
play bohemian rhapsody on spotify
chill mode
study mode
search best sci fi movies
what time is it
review code
review my changes
open first issue
fix first issue
push to github
start ollama
stop ollama
```

## AI Code Review

JARVIS can review local Git changes with Ollama (phi3:mini) or Gemini fallback.

Voice or text examples:

```text
review code
review my changes
open first issue
fix first issue
```

`fix first issue` only applies safe automatic fixes, such as adding generated folders to `.gitignore`. If a finding needs judgment, JARVIS opens the exact file and line instead of guessing.

Config (`reviewer` in `config.json`):

- `use_ai`: use AI for `review my changes` (default true)
- `merge_rule_findings`: combine AI with local secret and task-marker checks
- `max_diff_chars`: cap diff size sent to the model
- `ollama_model`: local model name (default `phi3:mini`)
- `projects`: map friendly project names to folders, so commands like `review jarvis` know where to go
- `allow_push`: lets JARVIS run `git push` only when the working tree is clean

## Custom Apps

Command-based app:

```json
"chrome": {
  "type": "command",
  "target": "chrome"
}
```

Direct shortcut or executable:

```json
"my app": {
  "type": "path",
  "target": "C:\\Path\\To\\App.lnk"
}
```

## Music And Playlists

JARVIS can open saved Spotify playlists or search for specific songs without needing a Spotify API key.

Saved playlist:

```json
"playlists": {
  "chill": "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID",
  "liked songs": "spotify:collection:tracks"
}
```

Music settings:

```json
"music": {
  "service": "spotify",
  "default_playlist": "liked songs"
}
```

Voice examples:

```text
play music
play chill playlist
play playlist discover weekly
play song blinding lights
play starboy on spotify
```

For exact playlists, add the Spotify playlist URL in the JARVIS sidebar under **Playlists**.

## Custom Modes

Modes are routines made of apps, websites, playlists, folders, and delays:

```json
"chill mode": [
  {
    "type": "app",
    "name": "chrome",
    "delay": 1
  },
  {
    "type": "website",
    "name": "netflix"
  },
  {
    "type": "playlist",
    "name": "chill"
  }
]
```

You can create modes directly in the JARVIS UI.

 5fe6134 (Add web-based UI (webview_ui.py + web/) alongside classic Tkinter UI)
