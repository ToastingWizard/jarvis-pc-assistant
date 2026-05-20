# JARVIS PC Assistant

A local Windows voice assistant for launching apps, opening websites and folders, running custom modes, and having lightweight butler-style conversation.

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
- Voice commands like `hey jarvis open chrome`
- Custom apps, websites, folders, and multi-step modes
- Text command box for testing without a microphone
- Optional local AI conversation through Ollama
- Optional Gemini fallback with your own API key
- Minimize-to-tray support
- One-file Windows `.exe` build
