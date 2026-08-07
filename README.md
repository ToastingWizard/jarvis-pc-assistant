# NaiTRO PC Assistant

A local PC voice assistant for launching apps, opening websites and folders, playing music, running custom modes, reviewing code, and having lightweight butler-style conversation. Windows is the main release target, and source mode also supports Linux.

## Download NaiTRO (Windows, No Setup)

The easiest way to get NaiTRO:

1. Go to the [**Releases**](https://github.com/ToastingWizard/NaiTRO/releases) page.
2. Download `NaiTRO.exe` from the latest release.
3. **Install the Microsoft Edge WebView2 Runtime** if you don't already have it — NaiTRO's UI is built on it, and the app won't display without it. Most Windows 11 and up-to-date Windows 10 machines already have this, but if you get a blank window or a crash on launch, install it:

   ```powershell
   winget install Microsoft.EdgeWebView2Runtime
   ```

   Or download it directly: https://developer.microsoft.com/en-us/microsoft-edge/webview2/
4. Run `NaiTRO.exe`. On first launch it creates a local `config.json` next to the exe — you can customize everything from the app itself.

No Python, Node, or other dev tools are required to just run the exe.

## AI Setup — Bring Your Own Key (For Smart Responses)

NaiTRO can launch apps and automate tasks with **no AI key at all** — the launcher, custom modes, and voice control all work offline.

For smart AI conversations (and the voice assistant's replies), NaiTRO uses **NVIDIA NIM** first, with **Gemini** as a fallback. The app ships with **no API key inside the EXE** — you bring your own free key and paste it into **Settings → Neural Uplink** inside the app.

1. **NVIDIA NIM (recommended, free):** grab a key at [build.nvidia.com](https://build.nvidia.com), then paste it into Settings → Neural Uplink. Default model: `meta/llama-3.3-70b-instruct`.
2. **Gemini (fallback):** get a key at [aistudio.google.com](https://aistudio.google.com/apikey) and add it the same way.
3. **Ollama (fully local, no cloud):** install [Ollama](https://ollama.com/download/windows), then `ollama pull phi3:mini`. NaiTRO uses it whenever it's running and no cloud key is set.

> Your key never leaves your machine — it's stored only in the local `config.json`, sent only to the provider you chose, and never bundled into the EXE you share. Anyone who downloads the release creates their own key.

## Features

- Purple desktop control panel with a voice orb and mode shortcuts
- Voice commands like `hey naitro open chrome`, then natural follow-up commands
- Custom apps, websites, Spotify playlists, folders, and multi-step modes
- Text command box for testing without a microphone
- AI conversation via NVIDIA NIM (free key) with Gemini and local Ollama fallbacks
- Bring-your-own-key: the shipped EXE contains no API key
- Minimize-to-tray support
- One-file Windows `.exe` build with PyInstaller
- Linux source-mode support for launching apps, opening links/folders, voice, and code review
- One-command Linux installer (`install.sh`) and automatic app discovery (`discover_apps.py`) — see below

## Run From Source (Windows)

Install Python 3.10–3.13 (not 3.14 — SpeechRecognition doesn't support it yet) from [python.org](https://www.python.org/downloads/windows/) and enable **Add python.exe to PATH**.

```powershell
py -m pip install -r requirements.txt
py naitro_app.py
```

Or double-click:

```
run_naitro.bat
```

The web control panel requires the React UI to be built once beforehand — see [Build The EXE Locally](#build-the-exe-locally) below for the build command; it's needed for source mode too.

### Linux Setup (Recommended: One Command)

New to Linux, or just want this working with the least hassle? Run the installer — it's the only thing you need to do by hand:

```bash
chmod +x install.sh
./install.sh
```

That's it. This one script:

- Detects your distro (Ubuntu/Debian, Fedora, or Arch) and installs every system package NaiTRO needs — audio libraries (PortAudio, espeak-ng, ffmpeg), the GTK/WebKit stack the web UI runs on, and the build tools needed for the GTK Python bindings.
- Creates a Python 3.13 virtual environment specifically (**not** 3.14 — SpeechRecognition doesn't support it yet).
- Installs every Python package NaiTRO needs, including Playwright + a real Chromium build for it.
- Creates a working desktop icon (`NaiTRO` in your applications menu) and a `naitro-launch.sh` script.

It's safe to re-run any time — for example, after moving the project folder to a new location (a venv breaks if you move it, since it bakes in absolute paths; re-running `install.sh` rebuilds it correctly for wherever the project lives now).

Once it finishes, either click the **NaiTRO** icon in your applications menu, or launch it from the terminal:

```bash
./naitro-launch.sh
```

If it ever prints `Web UI unavailable (...)`, NaiTRO still works fine using its classic interface — that message just means one of the system GTK/WebKit packages couldn't be installed automatically (the exact package name can vary between Ubuntu versions). The error message names what's missing if you want to track it down.

**Doing it manually instead of the script:**

```bash
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

Instead of typing in each app you want NaiTRO to know about by hand, `discover_apps.py` scans your system's own app registry (the same `.desktop` files that populate your applications menu — covers apt/dnf/pacman packages, Flatpak, and Snap) and adds every app it finds to your config automatically.

See what it would add first, without changing anything:

```bash
python3 Python/discover_apps.py --dry-run
```

Then run it for real:

```bash
python3 Python/discover_apps.py
```

It only **adds** apps that aren't already in your config — it never overwrites anything you've already set up by hand, and never touches any other part of `config.json` (your API key, voice settings, etc. are left completely alone). Safe to re-run any time you install something new; it'll just pick up whatever's new since the last run.

Once it's done, just talk to NaiTRO like normal:

```
hey naitro open <app name>
```

Note: this only picks up GUI apps with a proper `.desktop` entry — which is effectively everything in your applications menu. A command-line-only tool with no menu entry needs to be added to `config.json` by hand instead.

## Build The EXE Locally

The React UI has to be built once before packaging, since `NaiTRO.spec` bundles its output:

```powershell
cd web\react-ui
npm install
npm run build
cd ..\..
```

Then build the exe:

```powershell
.\build_windows.ps1
```

Or directly with PyInstaller:

```powershell
pyinstaller NaiTRO.spec --clean
```

The finished app will be:

```
dist\NaiTRO.exe
```

If you rebuild after changing anything under `web/react-ui/`, re-run `npm run build` first — otherwise PyInstaller will bundle the old UI.

## Publishing A New Release

Pushing to `main` or a version tag automatically builds `NaiTRO.exe` via GitHub Actions (`.github/workflows/build-windows.yml`) and, for tags, publishes it as a GitHub Release.

```bash
git add .
git commit -m "Fix packaging and blank-window issues"
git push origin main

# To cut an actual downloadable release:
git tag v1.0.1
git push origin v1.0.1
```

Once the tag is pushed, check the repo's **Actions** tab for build progress. When it finishes, `NaiTRO.exe` appears under the new release on the **Releases** page, ready to share.

## Landing Page (Your Domain)

`web/site/index.html` is a self-contained marketing page (download button, BYOK setup steps, WebView2 note). Point your domain's web root at it — it needs no build step, and the Download button links straight to `https://github.com/ToastingWizard/NaiTRO/releases/latest`. To deploy, upload `index.html` to your host or wire it into a static hosting service (GitHub Pages, Netlify, Vercel, etc.) with `web/site/` as the publish directory.

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

NaiTRO can review local Git changes with the same AI providers (NVIDIA NIM, Gemini, or local Ollama).

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

## Troubleshooting

- **Blank window, or the exe closes immediately with no error**: install/update the WebView2 Runtime — see [Download NaiTRO](#download-naitro-windows-no-setup) above. This is the most common cause of NaiTRO appearing to "not open."
- **A terminal window opens behind the app**: you're running a debug build (`console=True` in `NaiTRO.spec`). Official releases are built with `console=False`; rebuild locally with that setting if you want a debug console back temporarily.
- **`naitro.exe` from Windows Search opens the wrong thing**: this usually means an old copy or an unrelated package's console-script stub is being matched first. Pin a shortcut to your real `dist\NaiTRO.exe` to Start, and remove/rename old project folders so search stops surfacing them.

## About

A personal AI assistant inspired by J.A.R.V.I.S. is built for automation, voice and text interaction, and smart task handling. It is designed for learning and experimenting with AI, APIs, and Python. This assistant can be customized to grow with new features and integrations.
