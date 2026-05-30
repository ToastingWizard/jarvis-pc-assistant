# JARVIS PC Assistant

A local Windows voice assistant for launching apps, opening websites and folders, playing music, running custom modes, and having lightweight butler-style conversation.

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
start ollama
stop ollama
```

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

## GitHub Safety Checklist

- Keep `config.json` private.
- Do not commit `dist/` or `build/`.
- Do not commit API keys.
- Tell friends Windows may show a SmartScreen warning because the exe is not code-signed.
- Friends should customize their own microphone and app paths inside JARVIS.
