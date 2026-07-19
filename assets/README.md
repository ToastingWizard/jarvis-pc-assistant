# NaiTRO PC Assistant

A local PC voice assistant for launching apps, opening websites and folders, playing music, running custom modes, reviewing code, and having lightweight butler-style conversation. Windows is the main release target, and source mode also supports Linux.

## AI Setup (Required For Smart Responses)

NaiTRO can launch apps and automate tasks without AI.

For smart AI conversations, install Ollama and the Phi-3 Mini model:

1. Install Ollama:
https://ollama.com/download/windows

2. Open PowerShell and run:

```powershell
ollama pull phi3:mini
```

## Features

- Purple desktop control panel with a voice orb and mode shortcuts
- Voice commands like `hey naitro open chrome`, then natural follow-up commands
- Custom apps, websites, Spotify playlists, folders, and multi-step modes
- Text command box for testing without a microphone
- Optional local AI conversation through Ollama
- Optional Gemini fallback with your own API key
- Minimize-to-tray support
- One-file Windows `.exe` build with PyInstaller
- Linux source-mode support for launching apps, opening links/folders, voice, and code review

## Installation Guide

The easiest way to share NaiTRO is through GitHub Releases:

1. Push this project to GitHub.
2. Go to the repository's **Actions** tab.
3. Run **Build Windows EXE** manually, or push a version tag like `v1.0.0`.
4. Download `NaiTRO.exe` from the workflow artifact or the GitHub Release.
5. Send friends the release link.

When they launch the exe, NaiTRO creates a fresh local `config.json` next to the exe. They can customize everything from the app.

## Run From Source

Install Python 3.10.x -3.13.x dont install 3.14.x cause speach recognition wont work from [python.org](https://www.python.org/downloads/windows/) and enable **Add python.exe to PATH**.

```powershell
py -m pip install -r requirements.txt
py naitro_app.py
```

Or double-click:

```text
run_naitro.bat
```

### Linux Notes

The easiest way to get set up on Ubuntu/Debian is the included setup script.
It installs everything NaiTRO needs -- audio libraries, and the GTK/WebKit
stack the web UI runs on -- and creates a Python 3.13 virtual environment
(3.14 breaks voice recognition, so this matters):

```bash
chmod +x setup_linux.sh
./setup_linux.sh
```

Then, every time you want to run NaiTRO:

```bash
source venv/bin/activate
python naitro_app.py
```

If it ever prints `Web UI unavailable (...)`, NaiTRO still works fine using
its classic interface -- that message just means one of the system GTK/WebKit
packages couldn't be installed automatically (the exact package name can
vary between Ubuntu versions). The error message names what's missing if you
want to track it down; search `apt-cache search webkit2` for the matching
package name on your release.

**Doing it manually instead of the script:**

```bash
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev \
    portaudio19-dev python3-tk ffmpeg \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
    libgirepository-2.0-dev gir1.2-girepository-2.0 libcairo2-dev pkg-config gcc
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pycairo PyGObject
python naitro_app.py
```

On Linux, NaiTRO uses `xdg-open` for links/folders and normal shell commands for apps. For custom apps, set the target to the Linux command, for example `google-chrome`, `spotify`, `pycharm`, or `/home/you/AppImageName.AppImage`.

## Build The EXE Locally

```powershell
.\build_windows.ps1
```

The finished app will be:

```text
dist\NaiTRO.exe
```

## Voice Setup Notes

Voice input uses `SpeechRecognition` and `PyAudio`. If PyAudio refuses to install on Windows, try:

```powershell
python -m pip install pipwin
pipwin install pyaudio
python -m pip install -r requirements.txt
```

For best recognition, use headphones or keep speaker volume low so NaiTRO does not hear its own voice.

## Personal Config

Do not commit your real `config.json`. It can contain personal Windows paths, microphone indexes, and API keys. The repo includes `config.example.json` as a safe starter.

If you want to reset your local setup:

```powershell
copy config.example.json config.json
```

## Commands

```text
hey naitro open chrome
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

NaiTRO can review local Git changes with Ollama (phi3:mini) or Gemini fallback.

Voice or text examples:

```text
review code
review my changes
open first issue
fix first issue
```

`fix first issue` only applies safe automatic fixes, such as adding generated folders to `.gitignore`. If a finding needs judgment, NaiTRO opens the exact file and line instead of guessing.

Config (`reviewer` in `config.json`):

- `use_ai`: use AI for `review my changes` (default true)
- `merge_rule_findings`: combine AI with local secret and task-marker checks
- `max_diff_chars`: cap diff size sent to the model
- `ollama_model`: local model name (default `phi3:mini`)
- `projects`: map friendly project names to folders, so commands like `review naitro` know where to go
- `allow_push`: lets NaiTRO run `git push` only when the working tree is clean

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

NaiTRO can open saved Spotify playlists or search for specific songs without needing a Spotify API key.

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

For exact playlists, add the Spotify playlist URL in the NaiTRO sidebar under **Playlists**.

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

You can create modes directly in the NaiTRO UI.
