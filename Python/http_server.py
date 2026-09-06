"""
http_server.py — FastAPI HTTP server for NaiTRO browser UI.
Replaces PyWebView with a localhost server + browser approach.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from naitro_app import ActionResult, CONFIG_PATH, NaitroEngine
from app_launcher import finalize_app_entry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def resource_root() -> Path:
    """Project root in source mode; PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def web_dist_path() -> Path:
    """Path to the built React UI."""
    return resource_root() / "web" / "react-ui" / "dist"


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(title="NaiTRO API", version="2.0")

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global engine instance
engine: Optional[NaitroEngine] = None
voice_controller: Optional[VoiceController] = None


class VoiceController:
    """Manages voice input loop in a background thread."""

    def __init__(self, engine: NaitroEngine):
        self.engine = engine
        self.voice_running = False
        self._voice_lock = threading.Lock()
        self.conversation_active = False
        self.last_interaction_time = 0.0
        self.voice_error = None

    def start_voice(self):
        with self._voice_lock:
            if self.voice_running:
                return
            self.voice_running = True
            self.voice_error = None
        threading.Thread(target=self.voice_loop, daemon=True).start()

    def stop_voice(self):
        self.voice_running = False

    def voice_loop(self):
        """Voice recognition loop - mirrors webview_ui.py implementation."""
        try:
            import speech_recognition as sr
        except ImportError:
            self.engine.log("NaiTRO: SpeechRecognition not installed.")
            self.voice_running = False
            return

        recognizer = sr.Recognizer()
        voice = self.engine.config.get("voice", {})
        mic_index = voice.get("microphone_index")
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = int(voice.get("energy_threshold", 450))
        recognizer.pause_threshold = float(voice.get("pause_threshold", 0.9))
        recognizer.phrase_threshold = float(voice.get("phrase_threshold", 0.45))

        mic_failures = 0
        while self.voice_running:
            try:
                with sr.Microphone(device_index=mic_index) as source:
                    recognizer.adjust_for_ambient_noise(source, duration=1.2)
                    self.voice_error = None
                    mic_failures = 0
                    self._voice_listen_loop(source, recognizer, sr)
                return
            except Exception as e:
                self.voice_error = "mic"
                self.engine.log(f"NaiTRO: mic error — {e}")
                mic_failures += 1
                if not self.voice_running:
                    return
                time.sleep(2 if mic_failures <= 3 else 10)

    def _voice_listen_loop(self, source, recognizer, sr):
        while self.voice_running:
            try:
                if self.engine.is_audio_output_active():
                    time.sleep(0.12)
                    continue
                audio = recognizer.listen(
                    source,
                    timeout=float(self.engine.config.get("voice", {}).get("listen_timeout", 5)),
                    phrase_time_limit=float(self.engine.config.get("voice", {}).get("phrase_time_limit", 9)),
                )
                if self.engine.is_audio_output_active():
                    self.engine.log("NaiTRO: ignored voice while speaking.")
                    continue
                text = self.recognize_best_text(recognizer, audio, sr)
                if not text:
                    continue
                self.engine.log(f"NaiTRO: heard — {text}")

                addressed = self.engine.was_addressed_to_naitro(text)
                window_open = self.engine.is_conversation_window_open(
                    self.conversation_active, self.last_interaction_time
                )
                if self.conversation_active and not window_open:
                    self.conversation_active = False
                    self.engine.log("NaiTRO: conversation window timed out — say the wake word again.")

                if addressed or window_open:
                    self.conversation_active = True
                    self.last_interaction_time = time.time()
                    self.engine.greet_first_command()
                    if self.is_shutdown_request(text):
                        self.engine.respond("Shutting down. Goodbye, sir.")
                        threading.Timer(3.5, lambda: os._exit(0)).start()
                    else:
                        self.engine.run_command(text)

            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except Exception as e:
                self.engine.log(f"NaiTRO: voice error — {e}")

    def recognize_best_text(self, recognizer, audio, sr):
        try:
            result = recognizer.recognize_google(audio, language="en-US", show_all=True)
        except Exception:
            try:
                return recognizer.recognize_google(audio).lower()
            except:
                return ""

        alternatives = []
        if isinstance(result, dict):
            alternatives = [
                item.get("transcript", "").lower().strip()
                for item in result.get("alternative", [])
                if item.get("transcript")
            ]
        if not alternatives:
            return ""

        self.engine.log(f"NaiTRO: heard options — {', '.join(alternatives[:3])}")
        for candidate in alternatives:
            if self.engine.was_addressed_to_naitro(candidate) or self.is_actionable_voice_command(candidate):
                return self.engine.repair_wake_mishear(candidate)
        return self.engine.repair_wake_mishear(alternatives[0])

    def is_actionable_voice_command(self, text):
        command = self.engine.strip_wake_phrase(text)
        if self.engine.extract_music_target(command):
            return True
        if self.engine.extract_action_target(command):
            return True
        return self.engine.best_target(command) is not None

    def is_shutdown_request(self, text):
        norm = self.engine.normalize(text)
        command = self.engine.strip_wake_phrase(norm)
        shutdown_phrases = {
            "shut down naitro", "shutdown naitro", "exit naitro", "quit naitro",
            "close naitro", "power off naitro", "turn off naitro",
            "goodbye naitro", "bye naitro",
        }
        shutdown_commands = {
            "shut down", "shutdown", "exit", "quit", "close",
            "power off", "turn off", "goodbye", "bye",
            *shutdown_phrases,
        }
        return norm in shutdown_phrases or command in shutdown_commands


# ============================================================
# Request/Response Models
# ============================================================

class CommandRequest(BaseModel):
    text: str

class AddItemRequest(BaseModel):
    kind: str
    name: str
    target: str

class RemoveItemRequest(BaseModel):
    kind: str
    name: str

class SaveModeRequest(BaseModel):
    name: str
    steps: list
    style: str = ""

class DeleteModeRequest(BaseModel):
    name: str

class SettingRequest(BaseModel):
    key: str
    value: bool | str

class AIConfigRequest(BaseModel):
    provider: str
    key: str

class BrowserCommandRequest(BaseModel):
    text: str

class BrowserActionRequest(BaseModel):
    action: dict


# ============================================================
# API Endpoints
# ============================================================

@app.get("/health")
async def health_check():
    """Readiness probe."""
    return {"status": "ready", "service": "NaiTRO"}


@app.get("/api/dashboard")
async def get_dashboard_data():
    """Get dashboard configuration data."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    cfg = engine.config
    removed = cfg.get("removed") or {}
    not_removed = lambda section, name: name not in removed.get(section, [])

    mode_list = []
    for name, entry in cfg.get("modes", {}).items():
        steps = entry.get("steps") if isinstance(entry, dict) else entry
        style = (entry.get("style") if isinstance(entry, dict) else None) or ""
        n = len(steps) if isinstance(steps, list) else 0
        desc = f"{n} step{'s' if n != 1 else ''}" if n else "AI personality"
        mode_list.append({
            "name": name,
            "desc": desc,
            "steps": steps or [],
            "style": style,
        })

    def picker(section):
        return sorted(
            name for name in cfg.get(section, {})
            if not_removed(section, name)
        )

    return {
        "wake_phrase": cfg.get("wake_phrase", "hey naitro"),
        "user_title": cfg.get("conversation", {}).get("user_title", "sir"),
        "allow_push": bool(cfg.get("reviewer", {}).get("allow_push", False)),
        "speak_responses": bool(cfg.get("voice", {}).get("speak_responses", True)),
        "ai_status": {
            "has_nvidia": bool(cfg.get("nvidia_api_key", "").strip()),
            "has_gemini": bool(cfg.get("gemini_api_key", "").strip()),
        },
        "apps": {
            name.title(): {
                "icon": entry.get("icon") if isinstance(entry, dict) else None,
                "available": entry.get("available", True) if isinstance(entry, dict) else True,
            }
            for name, entry in cfg.get("apps", {}).items()
            if not_removed("apps", name)
        },
        "folders": {
            name.title(): {} for name in cfg.get("folders", {})
            if not_removed("folders", name)
        },
        "websites": {
            name.title(): {} for name in cfg.get("websites", {})
            if not_removed("websites", name)
        },
        "modes": {m["name"]: m for m in mode_list},
        "active_mode": cfg.get("active_mode"),
        "picker": {
            "apps": picker("apps"),
            "websites": picker("websites"),
            "folders": picker("folders"),
            "playlists": picker("playlists"),
        },
    }


@app.post("/api/action")
async def run_action(kind: str, name: str):
    """Execute an action (app, folder, website, mode)."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    if kind == "mode":
        result = engine.run_mode(name)
    elif kind in ("app", "folder", "website"):
        result = engine.open_target(name)
    else:
        return {"ok": False, "message": f"Unknown action kind: {kind}"}

    return _result_dict(result)


@app.post("/api/command")
async def send_command(req: CommandRequest):
    """Send a text command to the engine."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    result = engine.run_command(req.text)
    return _result_dict(result)


@app.post("/api/item/add")
async def add_item(req: AddItemRequest):
    """Add a new app, folder, or website."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    key = engine.normalize(req.name)
    if not key:
        return {"ok": False, "message": "Name can't be empty."}

    if req.kind == "app":
        entry = {"type": "command", "target": req.target or req.name}
        try:
            finalize_app_entry(req.name, entry, log=engine.log)
        except Exception as e:
            engine.log(f"App resolve error: {e}")
        engine.config.setdefault("apps", {})[key] = entry
        engine.save_config()
        avail = entry.get("available", False)
        msg = f"Added {entry.get('display_name', req.name)}"
        if avail:
            msg += " (resolved to " + (
                os.path.basename(entry.get("target", ""))
                or req.name
            ) + ")"
        elif not avail:
            msg += " (unavailable)"
        return {"ok": avail, "message": msg}
    elif req.kind == "folder":
        engine.config.setdefault("folders", {})[key] = req.target
    elif req.kind == "website":
        engine.config.setdefault("websites", {})[key] = req.target
    else:
        return {"ok": False, "message": f"Unknown item kind: {req.kind}"}

    engine.save_config()
    return {"ok": True, "message": f"Added {req.name} to {req.kind}s."}


@app.post("/api/item/remove")
async def remove_item(req: RemoveItemRequest):
    """Remove an item from config."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    key = engine.normalize(req.name)
    if not key:
        return {"ok": False, "message": "Name can't be empty."}

    section = {
        "app": "apps",
        "folder": "folders",
        "website": "websites",
        "playlist": "playlists",
    }.get(req.kind)

    if not section:
        return {"ok": False, "message": f"Unknown item kind: {req.kind}"}

    bucket = engine.config.get(section, {})
    if key not in bucket:
        return {"ok": False, "message": f"{req.name} is not in {section}."}

    del bucket[key]

    if req.kind == "website":
        engine.config.get("website_cache", {}).pop(key, None)

    removed = engine.config.setdefault("removed", {})
    removed.setdefault(section, [])
    if key not in removed[section]:
        removed[section].append(key)

    engine.save_config()
    return {"ok": True, "message": f"Removed {req.name}."}


@app.post("/api/mode/save")
async def save_mode(req: SaveModeRequest):
    """Create or update a mode."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    name = (req.name or "").strip()
    if not name:
        return {"ok": False, "message": "Mode name can't be empty."}

    if not isinstance(req.steps, list):
        steps = []
    else:
        steps = req.steps

    for s in steps:
        if not isinstance(s, dict) or s.get("type") not in ("app", "website", "folder", "playlist"):
            return {"ok": False, "message": "Each step needs a valid type."}
        if s["type"] == "website":
            if not s.get("url") and not s.get("name"):
                return {"ok": False, "message": "A website step needs a URL or name."}
        elif not s.get("name"):
            return {"ok": False, "message": f"A {s['type']} step needs a name."}

    key = engine.normalize(name)
    entry = {"steps": steps}
    if req.style and str(req.style).strip():
        entry["style"] = str(req.style).strip()

    engine.config.setdefault("modes", {})[key] = entry
    engine.save_config()
    return {"ok": True, "message": f"Mode '{name}' saved."}


@app.post("/api/mode/delete")
async def delete_mode(req: DeleteModeRequest):
    """Delete a mode."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    modes = engine.config.get("modes", {})
    key = engine.normalize(req.name)

    if key not in modes:
        for k in modes:
            if engine.normalize(k) == key:
                key = k
                break

    if key not in modes:
        return {"ok": False, "message": f"Mode '{req.name}' not found."}

    del modes[key]
    if engine.config.get("active_mode") == key:
        engine.config["active_mode"] = None

    engine.save_config()
    return {"ok": True, "message": f"Mode '{req.name}' deleted."}


@app.post("/api/mode/deactivate")
async def deactivate_mode():
    """Deactivate the current mode."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    result = engine.deactivate_mode()
    return _result_dict(result)


@app.post("/api/setting")
async def set_setting(req: SettingRequest):
    """Update a setting."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    if req.key == "speak_responses":
        engine.config.setdefault("voice", {})["speak_responses"] = bool(req.value)
    elif req.key == "allow_push":
        engine.config.setdefault("reviewer", {})["allow_push"] = bool(req.value)
    else:
        return {"ok": False, "message": f"Unknown setting: {req.key}"}

    engine.save_config()
    return {"ok": True, "message": ""}


@app.post("/api/voice/toggle")
async def toggle_voice(on: bool):
    """Toggle voice input."""
    if not voice_controller:
        return {"ok": False, "message": "Voice controller not available"}

    if on:
        voice_controller.start_voice()
    else:
        voice_controller.stop_voice()

    return {"ok": True, "message": ""}


@app.post("/api/ai/config")
async def save_ai_config(req: AIConfigRequest):
    """Save AI provider key."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    key_field = {
        "nvidia": "nvidia_api_key",
        "gemini": "gemini_api_key",
    }.get(req.provider)

    if not key_field:
        return {"ok": False, "message": f"Unknown AI provider: {req.provider}"}

    engine.config[key_field] = str(req.key or "").strip()
    engine.save_config()

    label = "NVIDIA NIM" if req.provider == "nvidia" else "Gemini"
    return {
        "ok": True,
        "message": f"{label} key saved." if engine.config[key_field] else f"{label} key cleared.",
    }


@app.get("/api/status")
async def get_status():
    """Get current status (speaking, listening, etc)."""
    if not engine or not voice_controller:
        return {
            "speaking": False,
            "listening": False,
            "conversation_active": False,
            "voice_error": None,
        }

    return {
        "speaking": bool(engine._is_speaking),
        "listening": bool(voice_controller.voice_running),
        "conversation_active": bool(voice_controller.conversation_active),
        "voice_error": getattr(voice_controller, "voice_error", None),
    }


# Browser agent endpoints (if available)
@app.get("/api/browser/status")
async def browser_status():
    """Get browser agent status."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    agent = engine._get_browser_agent()
    if agent is None:
        return {
            "running": False,
            "tabs": [],
            "current_snapshot": None,
            "last_action": "",
            "pending_confirmation": None,
        }
    return agent.browser_status()


@app.post("/api/browser/start")
async def browser_start():
    """Start browser agent."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    agent = engine._get_browser_agent()
    if agent is None:
        return {"ok": False, "message": "Browser agent unavailable"}
    return agent.start_browser()


@app.post("/api/browser/stop")
async def browser_stop():
    """Stop browser agent."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    engine.close_browser()
    return {"ok": True, "message": "Browser stopped"}


@app.post("/api/browser/command")
async def browser_command(req: BrowserCommandRequest):
    """Send command to browser agent."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    agent = engine._get_browser_agent()
    if agent is None:
        return {"ok": False, "message": "Browser agent unavailable"}
    return agent.run(req.text or "")


@app.post("/api/browser/execute")
async def browser_execute(req: BrowserActionRequest):
    """Execute browser action."""
    if not engine:
        raise HTTPException(status_code=500, detail="Engine not initialized")

    agent = engine._get_browser_agent()
    if agent is None:
        return {"ok": False, "message": "Browser agent unavailable"}
    return agent.execute_action(req.action)


# ============================================================
# Static Files & SPA Routing
# ============================================================

@app.get("/")
async def serve_index():
    """Serve the React app index.html."""
    index_path = web_dist_path() / "index.html"
    if not index_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"React UI not built. Run: cd web/react-ui && npm run build"
        )
    return FileResponse(index_path)


# Mount static files (JS, CSS, assets) if they exist
# Note: vite-plugin-singlefile bundles everything into index.html,
# so there may not be separate asset files
static_path = web_dist_path()
if static_path.exists() and (static_path / "assets").exists():
    app.mount("/assets", StaticFiles(directory=static_path / "assets"), name="assets")


# ============================================================
# Helper Functions
# ============================================================

def _result_dict(result: ActionResult) -> dict:
    """Convert ActionResult to dict."""
    if isinstance(result, ActionResult):
        return {"ok": result.ok, "message": result.message}
    return {"ok": True, "message": ""}


# ============================================================
# Server Management
# ============================================================

def find_available_port(start_port: int = 8080, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    import socket
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")


def wait_for_server(port: int, timeout: int = 10) -> bool:
    """Wait for server to be ready by checking /health endpoint."""
    import requests
    url = f"http://127.0.0.1:{port}/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                return True
        except:
            pass
        time.sleep(0.2)
    return False


def start_server(port: int, engine_instance: NaitroEngine, voice_instance: VoiceController):
    """Start the FastAPI server."""
    global engine, voice_controller
    engine = engine_instance
    voice_controller = voice_instance

    logger.info(f"Starting NaiTRO HTTP server on port {port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def launch_naitro():
    """Main entry point for browser-based NaiTRO."""
    logger.info("=" * 60)
    logger.info("NaiTRO 2.0 - Browser Interface")
    logger.info("=" * 60)

    # Find available port
    try:
        port = find_available_port(8080)
        logger.info(f"Using port: {port}")
    except RuntimeError as e:
        logger.error(f"Failed to find available port: {e}")
        sys.exit(1)

    # Initialize engine
    logger.info("Initializing NaiTRO engine...")
    engine_instance = NaitroEngine(config_path=CONFIG_PATH)
    voice_instance = VoiceController(engine_instance)

    # Start voice if enabled
    if engine_instance.config.get("voice", {}).get("auto_start", True):
        logger.info("Auto-starting voice input...")
        voice_instance.start_voice()

    # Start server in background thread
    server_thread = threading.Thread(
        target=start_server,
        args=(port, engine_instance, voice_instance),
        daemon=True
    )
    server_thread.start()

    # Wait for server to be ready
    logger.info("Waiting for server to be ready...")
    if wait_for_server(port, timeout=10):
        logger.info("✓ Server is ready")
        url = f"http://127.0.0.1:{port}"
        logger.info(f"Opening browser: {url}")

        # Open browser
        try:
            webbrowser.open(url)
            logger.info("✓ Browser launched")
        except Exception as e:
            logger.error(f"Failed to open browser: {e}")
            logger.info(f"Please manually open: {url}")
    else:
        logger.error("Server failed to start within timeout")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("NaiTRO is running. Close this window to shut down.")
    logger.info("=" * 60)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nShutting down NaiTRO...")
        sys.exit(0)


if __name__ == "__main__":
    launch_naitro()
