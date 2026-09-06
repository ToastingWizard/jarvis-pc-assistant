# NaiTRO 2.0 - AI Assistant

A local AI voice assistant with a minimal, professional browser-based interface. NaiTRO runs entirely on your PC—no cloud dependency required.

## 🚀 Quick Start

### Download & Run (Windows)

1. **Download** `NaiTRO.exe` from [Releases](https://github.com/ToastingWizard/NaiTRO/releases)
2. **Double-click** to launch
3. **Browser opens automatically** to http://localhost:8080
4. **Start using NaiTRO** - say "hey naitro" or type commands

No Python, Node, or dev tools needed for the EXE.

### Requirements

- **Windows 10/11** (or Linux for source mode)
- **Modern browser** (Chrome, Edge, Firefox)
- **Optional**: Microphone for voice commands
- **Optional**: API keys for AI features (see below)

## ✨ What's New in 2.0

### Complete UI Revamp
- **Browser-based interface** - Uses your default browser instead of embedded window
- **Minimal design** - Electric blue + vivid red color scheme
- **Professional layout** - Clean 3-column interface (Navigation | AI Core | System Panel)
- **Localhost architecture** - HTTP server + REST API instead of PyWebView

### Startup Flow
```
Double-click NaiTRO.exe
    ↓
Server starts on localhost:8080
    ↓
Browser opens automatically
    ↓
NaiTRO UI loads
```

Everything runs locally on your machine.

## 🎯 Features

### Core Functionality
- 🎤 **Voice Commands** - Wake phrase detection ("hey naitro")
- 💬 **AI Conversation** - NVIDIA NIM (free), Gemini, or local Ollama
- 🚀 **App Launching** - Open any installed application
- 🌐 **Website Opening** - Smart discovery and shortcuts
- 📁 **Folder Access** - Quick folder shortcuts
- 🎵 **Music Control** - Spotify integration
- ⚙️ **Custom Modes** - Create multi-step routines
- 🖥️ **System Control** - Volume, window management
- 🔍 **Code Review** - Git diff analysis with AI
- 🌐 **Browser Agent** - Automated web interactions (Playwright)

### Visual Interface
- Circular AI core with state-based animations
- Real-time system status (CPU, Memory, Network)
- Command input bar with voice button
- Quick action shortcuts
- Recent activity feed
- AI model indicator

## 🔧 AI Setup (Optional)

NaiTRO works **without AI keys** for launching apps and automation. For smart conversations, configure an AI provider:

### NVIDIA NIM (Recommended, Free)
1. Get free API key at [build.nvidia.com](https://build.nvidia.com)
2. Open **Settings → Neural Uplink** in NaiTRO
3. Paste your key

Default model: `meta/llama-3.3-70b-instruct`

### Google Gemini (Fallback)
1. Get key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Add in Settings → Neural Uplink

### Ollama (Fully Local)
1. Install [Ollama](https://ollama.com/download/windows)
2. Run: `ollama pull phi3:mini`
3. NaiTRO auto-detects when Ollama is running

> Your keys stay local in `config.json` - never bundled in the EXE, never sent anywhere except your chosen provider.

## 💻 Run From Source

### Windows
```powershell
# Install dependencies
pip install -r requirements.txt

# Build React UI (one time)
cd web/react-ui
npm install
npm run build
cd ../..

# Run NaiTRO
python naitro_main.py
```

### Linux
```bash
# One-command installer
chmod +x install.sh
./install.sh

# Or manual install
sudo apt install python3.13 python3.13-venv portaudio19-dev espeak-ng ffmpeg
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd web/react-ui && npm install && npm run build && cd ../..
python naitro_main.py
```

Server starts on http://localhost:8080 and opens your browser.

## 🛠️ Build the EXE

```powershell
# 1. Build React UI
cd web/react-ui
npm install
npm run build
cd ../..

# 2. Build EXE with PyInstaller
pyinstaller NaiTRO.spec --clean
```

Output: `dist/NaiTRO.exe`

## 📖 Usage Examples

### Voice Commands
```
hey naitro open chrome
open spotify
play music
play discover weekly playlist
chill mode
search best sci fi movies
what time is it
review code
what's my ip
```

### Text Commands
Type any command in the command bar at the bottom of the UI.

### Quick Actions
Click shortcuts for common tasks:
- Open YouTube
- Open Discord
- Check the news
- What's my IP?

### Custom Modes
Create multi-step routines in Settings:
```json
{
  "chill mode": {
    "steps": [
      { "type": "app", "name": "spotify", "delay": 1 },
      { "type": "website", "name": "netflix" },
      { "type": "playlist", "name": "chill" }
    ]
  }
}
```

## 🎨 Interface Layout

```
┌──────────────┬──────────────────────────────┬─────────────────────┐
│              │                              │                     │
│  NAVIGATION  │       MAIN AI AREA           │   SYSTEM PANEL      │
│              │                              │                     │
│  NaiTRO      │     [Rotating N Core]        │   System Status     │
│  • Home      │                              │   • CPU Usage       │
│  • Chat      │         IDLE                 │   • Memory Usage    │
│  • Activity  │  What can I do for you?      │   • Network         │
│  • Tools     │                              │   • Audio           │
│  • Settings  │   [Quick Action Buttons]     │                     │
│              │                              │   Current AI Model  │
│  Voice: ✓    │   [Command Input Bar]        │   Qwen2.5:7B        │
│  ● Ready     │   Type or speak...       ➤   │                     │
│              │                              │   Quick Tools       │
└──────────────┴──────────────────────────────┴─────────────────────┘
```

## 🎨 Color System

- **Electric Blue** (`#0EA5E9`) - AI interaction, information, active states
- **Vivid Red** (`#EF4444`) - NaiTRO branding, actions, attention
- **Near-black background** - Professional minimal aesthetic

## ⚙️ Configuration

Config location:
- **Source mode**: `config/config.json`
- **EXE mode**: `config.json` next to the executable

The UI automatically loads settings from the backend API.

### Example config.json
```json
{
  "wake_phrase": "hey naitro",
  "voice": {
    "auto_start": true,
    "speak_responses": true
  },
  "apps": {
    "chrome": { "type": "command", "target": "chrome" },
    "spotify": { "type": "command", "target": "spotify" }
  },
  "websites": {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com"
  },
  "modes": {
    "chill mode": {
      "steps": [
        { "type": "app", "name": "spotify" },
        { "type": "website", "name": "netflix" }
      ]
    }
  }
}
```

## 🔍 Architecture

NaiTRO 2.0 uses a **localhost HTTP server + browser** architecture:

1. **Backend**: FastAPI server (Python) exposes REST API
2. **Frontend**: React UI served as single-file HTML
3. **Communication**: REST API calls over localhost
4. **Startup**: Server launches, waits for ready, opens browser

See [ARCHITECTURE.md](ARCHITECTURE.md) for complete details.

## 🐛 Troubleshooting

### Browser doesn't open
Manually navigate to the URL shown in terminal (usually http://localhost:8080)

### Voice not working
- Check microphone permissions
- Verify `SpeechRecognition` is installed: `pip install SpeechRecognition`
- Windows: `pip install pyaudio` or `pipwin install pyaudio`

### "React UI not built" error
```bash
cd web/react-ui
npm install
npm run build
```

### Port already in use
NaiTRO auto-finds an available port (8080-8090). Check terminal for actual URL.

### Multiple instances
Launching NaiTRO twice is safe - it detects existing instances.

## 📚 Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - Complete architecture guide
- [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) - Development details
- [config.example.json](config/config.example.json) - Configuration reference

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Build and test: `npm run build && python naitro_main.py`
4. Submit a pull request

## 📝 License

MIT License - See [LICENSE](LICENSE)

## 🙏 Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Backend HTTP server
- [React](https://react.dev/) - Frontend UI framework
- [Tailwind CSS](https://tailwindcss.com/) - Styling
- [Lucide](https://lucide.dev/) - Icon library
- [PyInstaller](https://pyinstaller.org/) - EXE packaging

AI providers:
- [NVIDIA NIM](https://build.nvidia.com) - Free cloud AI
- [Google Gemini](https://ai.google.dev/) - Fallback cloud AI
- [Ollama](https://ollama.com/) - Local AI models

---

**NaiTRO 2.0** - Your minimal, professional AI assistant  
Built by [@ToastingWizard](https://github.com/ToastingWizard)
