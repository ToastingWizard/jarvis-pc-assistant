# NaiTRO 2.0 - Complete UI Revamp

## Architecture Overview

NaiTRO 2.0 moves from a PyWebView desktop window to a **localhost HTTP server + browser** architecture.

### Startup Flow

```
User double-clicks NaiTRO.exe
    ↓
FastAPI HTTP server starts on localhost:8080
    ↓
Backend becomes ready (polls /health endpoint)
    ↓
Default browser opens automatically to http://localhost:8080
    ↓
React UI loads in the browser
    ↓
Everything runs locally - no cloud dependency
```

### Key Changes

1. **Browser-based UI** - Uses your default browser instead of embedded WebView
2. **REST API** - Backend exposes HTTP endpoints instead of PyWebView bridge
3. **Minimal Design** - Electric blue + vivid red color scheme (no more purple)
4. **Professional Layout** - Clean 3-column interface (Navigation | Main | System Panel)
5. **Smart Startup** - Server readiness detection + automatic browser launch

## Visual Design

### Color System

- **Electric Blue** (`rgb(14, 165, 233)`) - AI/interaction/information/active states
- **Vivid Red** (`rgb(239, 68, 68)`) - NaiTRO branding/actions/attention/execution
- **Near-black background** - Professional minimal aesthetic
- **Restrained effects** - No heavy particles, minimal animations

### Layout

```
┌──────────────┬──────────────────────────────┬─────────────────────┐
│              │                              │                     │
│  NAVIGATION  │       MAIN AI AREA           │   SYSTEM PANEL      │
│              │                              │                     │
│  • NaiTRO    │       NaiTRO Core            │   • System Status   │
│  • Home      │       (Circular N logo)      │   • AI Model        │
│  • Chat      │                              │   • Quick Tools     │
│  • Activity  │       Status Display         │   • Recent Activity │
│  • Tools     │       Command Input          │                     │
│  • Settings  │       Quick Actions          │                     │
│              │                              │                     │
└──────────────┴──────────────────────────────┴─────────────────────┘
```

## Development

### Build the React UI

```bash
cd web/react-ui
npm install
npm run build
```

This creates `web/react-ui/dist/` with the bundled single-file HTML.

### Run from Source

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run NaiTRO
python naitro_main.py
```

The server will:
1. Start on http://localhost:8080
2. Automatically open your browser
3. Keep running until you close the terminal

### Build the EXE

```bash
# First, build the React UI
cd web/react-ui
npm run build
cd ../..

# Then build the EXE with PyInstaller
pyinstaller NaiTRO.spec --clean
```

The packaged executable will be at `dist/NaiTRO.exe`.

## API Endpoints

The FastAPI server exposes these endpoints:

### Core
- `GET /health` - Server readiness check
- `GET /api/dashboard` - Dashboard configuration data
- `POST /api/command` - Send text command
- `POST /api/action` - Execute action (app/folder/website/mode)

### Configuration
- `POST /api/item/add` - Add app/folder/website
- `POST /api/item/remove` - Remove item
- `POST /api/mode/save` - Save mode
- `POST /api/mode/delete` - Delete mode
- `POST /api/setting` - Update setting

### Status
- `GET /api/status` - Real-time status (speaking/listening/etc)
- `POST /api/voice/toggle` - Toggle voice input

### AI
- `POST /api/ai/config` - Save AI provider key

### Browser Agent
- `GET /api/browser/status` - Browser agent status
- `POST /api/browser/start` - Start browser
- `POST /api/browser/command` - Send browser command

## Component Structure

```
web/react-ui/src/
├── App.tsx                     # Main application shell
├── components/
│   ├── Navigation.tsx          # Left sidebar navigation
│   ├── NaiTROCore.tsx          # Central circular AI core
│   ├── CommandBar.tsx          # Command input at bottom
│   ├── QuickActions.tsx        # Quick action buttons
│   ├── SystemStatus.tsx        # CPU/Memory/Network status
│   ├── ModelCard.tsx           # Current AI model display
│   ├── QuickTools.tsx          # Tool shortcuts grid
│   └── ActivityPanel.tsx       # Recent activity feed
├── lib/
│   └── api.ts                  # REST API client
└── index.css                   # Minimal blue+red styling
```

## Preserved Functionality

All existing NaiTRO features still work:

✅ Voice input & wake phrase detection  
✅ Text-to-speech responses  
✅ App launching (Windows/Linux)  
✅ Website opening & discovery  
✅ Folder shortcuts  
✅ Custom modes  
✅ AI conversation (NVIDIA NIM, Gemini, Ollama)  
✅ Code review functionality  
✅ Browser agent (Playwright)  
✅ System controls (volume, window management)  

## Configuration

Config location remains the same:
- **Source mode**: `config/config.json`
- **EXE mode**: `config.json` next to the executable (or `dist/../config/config.json` in repo)

The UI automatically loads settings from the backend API.

## Port Management

If port 8080 is unavailable, NaiTRO automatically finds the next available port (8081, 8082, etc).

If NaiTRO is already running, launching it again will detect the existing instance.

## Troubleshooting

### Browser doesn't open automatically
Manually navigate to the URL shown in the terminal (usually http://localhost:8080)

### "React UI not built" error
Run `cd web/react-ui && npm run build` first

### Voice not working
- Check microphone permissions
- Verify `SpeechRecognition` is installed: `pip install SpeechRecognition`
- For Windows, you may need: `pip install pyaudio` or `pipwin install pyaudio`

### Port already in use
NaiTRO automatically finds an available port. Check the terminal output for the actual URL.

## Design Philosophy

The new UI follows these principles:

1. **Minimal over decorative** - Clean, professional interface
2. **Functional over flashy** - Animations only for state communication
3. **Readable over stylized** - Clear typography and spacing
4. **Responsive over fixed** - Adapts to different window sizes
5. **Fast over fancy** - Lightweight, no heavy effects

## Future Enhancements

Potential improvements for future versions:

- [ ] WebSocket for real-time log streaming (currently uses polling)
- [ ] Multiple theme support (keep blue+red as default)
- [ ] Draggable/resizable panels
- [ ] Persistent activity log in database
- [ ] Real system metrics (psutil integration)
- [ ] Plugin system for custom tools
- [ ] Mobile-responsive layout

---

**NaiTRO 2.0** - Your minimal, professional AI assistant interface
