# NaiTRO PC Assistant

A local PC voice assistant for launching apps, opening websites and folders, playing music, running custom modes, reviewing code, and having lightweight butler-style conversation. Windows is the main release target, and source mode also supports Linux.

## AI Setup (Required For Smart Responses)

NaiTRO can launch apps and automate tasks without AI.

For smart AI conversations, install Ollama and the Phi-3 Mini model:

1. Install Ollama: https://ollama.com/download/windows

2. Open PowerShell and run:

```
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
- One-command Linux installer (`install.sh`) and automatic app discovery (`discover_apps.py`) -- see below

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

```
py -m pip install -r requirements.txt
py naitro_app.py
```

Or double-click:

```
run_naitro.bat
```

### Linux Setup (Recommended: One Command)

New to Linux, or just want this working with the least hassle? Run the installer -- it's the only thing you need to do by hand:

```
chmod +x install.sh
./install.sh
```

That's it. This one script:

- Detects your distro (Ubuntu/Debian, Fedora, or Arch) and installs every system package NaiTRO needs -- audio libraries (PortAudio, espeak-ng, ffmpeg), the GTK/WebKit stack the web UI runs on, and the build tools needed for the GTK Python bindings.
- Creates a Python 3.13 virtual environment specifically (**not** 3.14 -- SpeechRecognition doesn't support it yet).
- Installs every Python package NaiTRO needs, including Playwright + a real Chromium build for it.
- Creates a working desktop icon (`NaiTRO` in your applications menu) and a `naitro-launch.sh` script.

It's safe to re-run any time -- for example, after moving the project folder to a new location (a venv breaks if you move it, since it bakes in absolute paths; re-running `install.sh` rebuilds it correctly for wherever the project lives now).

Once it finishes, either click the **NaiTRO** icon in your applications menu, or launch it from the terminal:

```
./naitro-launch.sh
```

If it ever prints `Web UI unavailable (...)`, NaiTRO still works fine using its classic interface -- that message just means one of the system GTK/WebKit packages couldn't be installed automatically (the exact package name can vary between Ubuntu versions). The error message names what's missing if you want to track it down.

**Doing it manually instead of the script:**

```
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev \
    portaudio19-dev python3-tk ffmpeg espeak-ng \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
    libgirepository-2.0-dev gir1.2-girepository-2.0 libcairo2-dev pkg-config gcc
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pycairo PyGObject
python naitro_app.py
```

On Linux, NaiTRO uses `xdg-open` for links/folders and normal shell commands for apps. For custom apps, set the target to the Linux command, for example `google-chrome`, `spotify`, `pycharm`, or `/home/you/AppImageName.AppImage`.

### Link All Your Installed Apps Automatically

Instead of typing in each app you want NaiTRO to know about by hand, `discover_apps.py` scans your system's own app registry (the same `.desktop` files that populate your applications menu -- covers apt/dnf/pacman packages, Flatpak, and Snap) and adds every app it finds to your config automatically.

See what it would add first, without changing anything:

```
python3 Python/discover_apps.py --dry-run
```

Then run it for real:

```
python3 Python/discover_apps.py
```

It only **adds** apps that aren't already in your config -- it never overwrites anything you've already set up by hand, and never touches any other part of `config.json` (your API key, voice settings, etc. are left completely alone). Safe to re-run any time you install something new; it'll just pick up whatever's new since the last run.

Once it's done, just talk to NaiTRO like normal:

```
hey naitro open <app name>
```

Note: this only picks up GUI apps with a proper `.desktop` entry -- which is effectively everything in your applications menu. A command-line-only tool with no menu entry needs to be added to `config.json` by hand instead.

## Build The EXE Locally

```
.\build_windows.ps1
```

The finished app will be:

```
dist\NaiTRO.exe
```

## Voice Setup Notes

Voice input uses `SpeechRecognition` and `PyAudio`. If PyAudio refuses to install on Windows, try:

```
python -m pip install pipwin
pipwin install pyaudio
python -m pip install -r requirements.txt
```

For best recognition, use headphones or keep speaker volume low so NaiTRO does not hear its own voice.

## Personal Config

Do not commit your real `config.json`. It can contain personal Windows paths, microphone indexes, and API keys. The repo includes `config.example.json` as a safe starter.

If you want to reset your local setup:

```
copy config.example.json config.json
```

## Commands

```
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

```
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

```
"chrome": {
  "type": "command",
  "target": "chrome"
}
```

Direct shortcut or executable:

```
"my app": {
  "type": "path",
  "target": "C:\\Path\\To\\App.lnk"
}
```

## Music And Playlists

NaiTRO can open saved Spotify playlists or search for specific songs without needing a Spotify API key.

Saved playlist:

```
"playlists": {
  "chill": "https://open.spotify.com/playlist/YOUR_PLAYLIST_ID",
  "liked songs": "spotify:collection:tracks"
}
```

Music settings:

```
"music": {
  "service": "spotify",
  "default_playlist": "liked songs"
}
```

Voice examples:

```
play music
play chill playlist
play playlist discover weekly
play song blinding lights
play starboy on spotify
```

For exact playlists, add the Spotify playlist URL in the NaiTRO sidebar under **Playlists**.

## Custom Modes

Modes are routines made of apps, websites, playlists, folders, and delays:

```
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

## About

A personal AI assistant inspired by J.A.R.V.I.S. is built for automation, voice and text interaction, and smart task handling. It is designed for learning and experimenting with AI, APIs, and Python. This assistant can be customized to grow with new features and integrations.
