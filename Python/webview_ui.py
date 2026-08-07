"""
webview_ui.py — NaiTRO's web-based control panel.
"""
from __future__ import annotations


import dataclasses
import diagnostics
import json
import os
import sys
import threading
import time
from pathlib import Path

import webview

from naitro_app import ActionResult, CONFIG_PATH, NaitroEngine
from app_launcher import finalize_app_entry


def resource_root() -> Path:
    """Project root in source mode; PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def web_index_path() -> Path:
    index = resource_root() / "web" / "react-ui" / "dist" / "index.html"
    diagnostics.lookup("asset", "react-ui index.html", str(index))
    return index


# #region agent log
def _agent_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    try:
        log_path = Path.cwd() / "debug-0b3274.log"
        payload = {
            "sessionId": "0b3274",
            "location": location,
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
            "timestamp": int(time.time() * 1000),
            "runId": os.environ.get("NAITRO_DEBUG_RUN", "runtime"),
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except Exception as exc:
        # cwd is unreliable in frozen mode (shortcut "Start in" is often
        # not set), so surfacing the write failure beats silently dropping it.
        diagnostics.log(f"[agent-log] failed writing {Path.cwd() / 'debug-0b3274.log'}: {exc!r}")
# #endregion


def _result_dict(result: ActionResult) -> dict:
    if isinstance(result, ActionResult):
        return dataclasses.asdict(result)
    return {"ok": True, "message": ""}


class NaitroWebController:
    # Tell pywebview's JS-bridge introspection (webview.util.get_functions)
    # to stop here.  Without this it recursively walks every attribute of
    # the controller — including self.window.native, the .NET WinForms /
    # WebView2 object — which trips Python's recursion limit and throws
    # "CoreWebView2Controller members can only be accessed from the UI
    # thread" errors on every launch.  All bridge methods live on Api, so
    # nothing is lost by not exposing c.*.
    _serializable = False

    def __init__(self, config_path=CONFIG_PATH):
        self.window: webview.Window | None = None
        diagnostics.mark("NaitroWebController.__init__ building engine")
        with diagnostics.timing("NaitroWebController.__init__ (NaitroEngine)"):
            self.engine = NaitroEngine(config_path=config_path, log=self._on_engine_log)
        self.voice_running = False
        self._voice_lock = threading.Lock()
        self.conversation_active = False
        self.last_interaction_time = 0.0
        # Set to "mic" when the microphone can't be opened (unplugged /
        # busy), cleared once a listen session starts. Surfaced to the UI
        # via get_status() so a dead mic is diagnosable instead of silent.
        self.voice_error = None

    def start(self):
        web_index = web_index_path()
        frozen = getattr(sys, "frozen", False)
        diagnostics.mark("webview start() — resolving React UI path")
        # #region agent log
        _agent_log(
            "webview_ui.py:start",
            "Resolving React UI path",
            {
                "frozen": frozen,
                "resource_root": str(resource_root()),
                "web_index": str(web_index),
                "exists": web_index.is_file(),
                "meipass": getattr(sys, "_MEIPASS", None),
            },
            "H1",
        )
        # #endregion
        if not web_index.is_file():
            diagnostics.report_missing("react-ui index.html", str(web_index))
            raise FileNotFoundError(
                f"React UI build not found at {web_index}. "
                f"Run: cd web/react-ui && npm install && npm run build"
            )
        api = Api(self)
        diagnostics.log(f"[webview] frozen={frozen} resource_root={resource_root()}")
        diagnostics.log(f"[webview] index_uri={web_index.resolve().as_uri()}")
        self.window = webview.create_window(
            "NaiTRO",
            url=web_index.resolve().as_uri(),
            js_api=api,
            width=1180,
            height=760,
            min_size=(860, 600),
            background_color="#050308",
            frameless=True,
            easy_drag=True,
        )
        diagnostics.mark("window created — entering webview.start() (blocks until close)")
        with diagnostics.timing("webview.start (GUI lifetime)"):
            webview.start(self._on_ready, debug=False)
        # webview.start() blocks until the window is closed.
        # When it returns, force a clean process exit so no background
        # threads (voice loop, TTS worker, etc.) keep NaiTRO alive
        # invisibly — which is exactly what caused the "4 NaiTROes
        # talking at once" bug.
        os._exit(0)

    def _on_ready(self):
        diagnostics.mark("webview _on_ready — window shown")
        # No startup greeting: NaiTRO stays silent on launch and starts
        # listening immediately so the first command can be spoken right
        # away. start_voice() spawns its own daemon thread and returns
        # immediately, so this never blocks the webview's ready callback.
        # A short "welcome back" line is spoken once, right before the
        # first recognized command runs -- see
        # NaitroEngine.greet_first_command(), called from voice_loop().
        if self.engine.config.get("voice", {}).get("auto_start", True):
            diagnostics.log("[webview] voice.auto_start=true — spawning voice thread")
            self.start_voice()
        else:
            diagnostics.log("[webview] voice.auto_start=false — voice not started")

    def _on_engine_log(self, text: str):
        """Bridge engine.log() to the React UI via window.naitroLog().

        CRITICAL: This is called from background threads (voice loop, TTS worker,
        API handlers). PyWebView's evaluate_js uses Control.Invoke + semaphore,
        which blocks the caller until the UI thread processes it. To avoid
        blocking the voice/TTS threads, we dispatch the JS call in a daemon
        thread with a short timeout.
        """
        if not self.window:
            return
        safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        js_code = f"window.naitroLog(`{safe}`)"

        def _dispatch():
            try:
                # Schedule JS on UI thread with 1s timeout
                self.window.evaluate_js(js_code)
            except Exception as exc:
                # UI not ready or timed out — log it instead of dropping
                # silently, since a saturated evaluate_js bridge is a
                # symptom of the frozen UI freezing up.
                diagnostics.log(f"[webview] evaluate_js failed for log line: {exc!r}")

        # Fire-and-forget: never block the voice/TTS threads
        threading.Thread(target=_dispatch, daemon=True).start()

    def start_voice(self):
        with self._voice_lock:
            if self.voice_running:
                return
            self.voice_running = True
            self.voice_error = None
        threading.Thread(target=self.voice_loop, daemon=True).start()

    def stop_voice(self):
        self.voice_running = False

    def is_actionable_voice_command(self, text):
        command = self.engine.strip_wake_phrase(text)
        if self.engine.extract_music_target(command):
            return True
        if self.engine.extract_action_target(command):
            return True
        return self.engine.best_target(command) is not None

    def recognize_best_text(self, recognizer, audio, sr):
        try:
            result = recognizer.recognize_google(audio, language="en-US", show_all=True)
        except Exception:
            return recognizer.recognize_google(audio).lower()

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

    def is_show_request(self, text):
        norm = self.engine.normalize(text)
        command = self.engine.strip_wake_phrase(norm)
        show_phrases = {
            "show naitro", "open naitro", "bring up naitro", "show yourself",
            "come back", "naitro show", "naitro open", "wake up naitro",
        }
        show_commands = {"show yourself", "show", "come back", "wake up"}
        return norm in show_phrases or command in show_commands

    def voice_loop(self):
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

        # Keep the loop alive across mic failures instead of dying
        # permanently on one bad open (unplugged/busy mic). Fast retries
        # first, then a slow heartbeat so a replugged mic recovers without
        # an app restart. A demo that loses its mic should retry, not go
        # permanently mute.
        mic_failures = 0
        while self.voice_running:
            try:
                with sr.Microphone(device_index=mic_index) as source:
                    recognizer.adjust_for_ambient_noise(source, duration=1.2)
                    self.voice_error = None
                    mic_failures = 0
                    self._voice_listen_loop(source, recognizer, sr)
                return  # listen loop exited because voice_running went False
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
                    # One-time "welcome back" line, spoken right as
                    # the first command of the session is recognized
                    # -- never at launch. No-ops on every later
                    # command. See NaitroEngine.greet_first_command().
                    self.engine.greet_first_command()
                    if self.is_shutdown_request(text):
                        self.engine.respond("Shutting down. Goodbye, sir.")
                        threading.Timer(3.5, self._hard_exit).start()
                    elif self.is_show_request(text):
                        if self.window:
                            self.window.restore()
                    else:
                        self.engine.run_command(text)

            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except Exception as e:
                self.engine.log(f"NaiTRO: voice error — {e}")

    def _hard_exit(self):
        """Destroy the window and force the process to exit cleanly."""
        # Close the browser agent (Playwright + Chromium) before pywebview
        # so no orphan browser processes linger.
        try:
            self.engine.close_browser()
        except Exception:
            pass
        try:
            if self.window:
                self.window.destroy()
        except Exception:
            pass
        # Give pywebview/GTK 1 second to clean up, then hard-exit.
        # This is the only reliable way to stop all daemon threads
        # (voice loop, TTS worker, etc.) on all platforms.
        threading.Timer(1.0, lambda: os._exit(0)).start()


class Api:

    def __init__(self, controller: NaitroWebController):
        self.c = controller

    def get_dashboard_data(self):
        cfg = self.c.engine.config
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
            # Booleans only — the actual key values never leave the
            # engine, so a key can't be exfiltrated through the bridge.
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

    def run_action(self, kind, name):
        engine = self.c.engine
        if kind == "mode":
            return _result_dict(engine.run_mode(name))
        if kind in ("app", "folder", "website"):
            return _result_dict(engine.open_target(name))
        return {"ok": False, "message": f"Unknown action kind: {kind}"}

    def send_command(self, text):
        return _result_dict(self.c.engine.run_command(text))

    def add_item(self, kind, name, target):
        engine = self.c.engine
        key = engine.normalize(name)
        if not key:
            return {"ok": False, "message": "Name can't be empty."}
        if kind == "app":
            entry = {"type": "command", "target": target or name}
            try:
                finalize_app_entry(name, entry, log=engine.log)
            except Exception as e:
                engine.log(f"App resolve error: {e}")
            engine.config.setdefault("apps", {})[key] = entry
            engine.save_config()
            avail = entry.get("available", False)
            msg = f"Added {entry.get('display_name', name)}"
            if avail:
                msg += " (resolved to " + (
                    os.path.basename(entry.get("target", ""))
                    or name
                ) + ")"
            elif not avail:
                msg += (
                    " (unavailable — add via the Tkinter UI "
                    "with a full .exe/.lnk path)"
                )
            return {"ok": avail, "message": msg}
        elif kind == "folder":
            engine.config.setdefault("folders", {})[key] = target
        elif kind == "website":
            engine.config.setdefault("websites", {})[key] = target
        else:
            return {"ok": False, "message": f"Unknown item kind: {kind}"}
        engine.save_config()
        return {"ok": True, "message": f"Added {name} to {kind}s."}

    def remove_item(self, kind, name):
        """Remove a UI-added shortcut (or any entry) from the real config.

        Mirrors add_item: apps are keyed by engine.normalize(name), folders
        and websites by the same normalized key.  Returns ok=False if the
        key doesn't exist so the UI can fall back to clearing local extras.
        """
        engine = self.c.engine
        key = engine.normalize(name)
        if not key:
            return {"ok": False, "message": "Name can't be empty."}
        section = {
            "app": "apps",
            "folder": "folders",
            "website": "websites",
            "playlist": "playlists",
        }.get(kind)
        if not section:
            return {"ok": False, "message": f"Unknown item kind: {kind}"}
        bucket = engine.config.get(section, {})
        if key not in bucket:
            return {"ok": False, "message": f"{name} is not in {section}."}
        del bucket[key]
        if kind == "website":
            # Also forget the learned URL so the site can't be reached via
            # website_cache / best_target anymore.
            engine.config.get("website_cache", {}).pop(key, None)
        # Remember the deletion so deep_merge_defaults never re-seeds a
        # built-in default with the same name on the next launch.
        removed = engine.config.setdefault("removed", {})
        removed.setdefault(section, [])
        if key not in removed[section]:
            removed[section].append(key)
        engine.save_config()
        return {"ok": True, "message": f"Removed {name}."}

    def save_mode(self, name, steps, style=""):
        """Create or replace a mode.

        ``steps`` is a list of step dicts in the config shape
        {"type": "app|website|folder|playlist", "name": ..., "url"?: ..., "delay"?: N}.
        ``style`` is an optional AI personality string that overrides how
        NaiTRO talks while the mode is active.
        """
        engine = self.c.engine
        name = (name or "").strip()
        if not name:
            return {"ok": False, "message": "Mode name can't be empty."}
        if not isinstance(steps, list):
            steps = []
        for s in steps:
            if not isinstance(s, dict) or s.get("type") not in ("app", "website", "folder", "playlist"):
                return {"ok": False, "message": "Each step needs a valid type (app, website, folder, playlist)."}
            if s["type"] == "website":
                if not s.get("url") and not s.get("name"):
                    return {"ok": False, "message": "A website step needs a URL or a saved site name."}
            elif not s.get("name"):
                return {"ok": False, "message": f"A {s['type']} step needs a name."}
        key = engine.normalize(name)
        entry = {"steps": steps}
        if style and str(style).strip():
            entry["style"] = str(style).strip()
        engine.config.setdefault("modes", {})[key] = entry
        engine.save_config()
        return {"ok": True, "message": f"Mode '{name}' saved."}

    def delete_mode(self, name):
        """Remove a mode. Clears the active mode if it was the one deleted."""
        engine = self.c.engine
        modes = engine.config.get("modes", {})
        key = engine.normalize(name)
        # Mirror run_mode's fuzzy resolution so the exact stored key is found.
        if key not in modes:
            for k in modes:
                if engine.normalize(k) == key:
                    key = k
                    break
        if key not in modes:
            return {"ok": False, "message": f"Mode '{name}' not found."}
        del modes[key]
        if engine.config.get("active_mode") == key:
            engine.config["active_mode"] = None
        engine.save_config()
        return {"ok": True, "message": f"Mode '{name}' deleted."}

    def deactivate_mode(self):
        return _result_dict(self.c.engine.deactivate_mode())

    def set_setting(self, key, value):
        engine = self.c.engine
        if key == "speak_responses":
            engine.config.setdefault("voice", {})["speak_responses"] = bool(value)
        elif key == "allow_push":
            engine.config.setdefault("reviewer", {})["allow_push"] = bool(value)
        else:
            return {"ok": False, "message": f"Unknown setting: {key}"}
        engine.save_config()
        return {"ok": True, "message": ""}

    def toggle_voice(self, on):
        if on:
            self.c.start_voice()
        else:
            self.c.stop_voice()
        return {"ok": True, "message": ""}

    def save_ai_config(self, provider, key):
        """Persist an AI provider key. Never returns the key value back."""
        key_field = {
            "nvidia": "nvidia_api_key",
            "gemini": "gemini_api_key",
        }.get(provider)
        if not key_field:
            return {"ok": False, "message": f"Unknown AI provider: {provider}"}
        engine = self.c.engine
        engine.config[key_field] = str(key or "").strip()
        engine.save_config()
        label = "NVIDIA NIM" if provider == "nvidia" else "Gemini"
        return {
            "ok": True,
            "message": f"{label} key saved." if engine.config[key_field] else f"{label} key cleared.",
        }

    def get_status(self):
        return {
            "speaking": bool(self.c.engine._is_speaking),
            "listening": bool(self.c.voice_running),
            "conversation_active": bool(self.c.conversation_active),
            "voice_error": getattr(self.c, "voice_error", None),
        }

    # -------- Browser Agent API --------
    def browser_status(self):
        agent = self.c.engine._get_browser_agent()
        if agent is None:
            return {
                "running": False,
                "tabs": [],
                "current_snapshot": None,
                "last_action": "",
                "pending_confirmation": None,
            }
        return agent.browser_status()

    def browser_start(self):
        agent = self.c.engine._get_browser_agent()
        if agent is None:
            return {"ok": False, "message": "Browser agent unavailable — install Playwright"}
        return agent.start_browser()

    def browser_stop(self):
        self.c.engine.close_browser()
        return {"ok": True, "message": "Browser stopped"}

    def browser_command(self, text):
        agent = self.c.engine._get_browser_agent()
        if agent is None:
            return {"ok": False, "message": "Browser agent unavailable — install Playwright"}
        return agent.run(text or "")

    def browser_tabs(self):
        agent = self.c.engine._get_browser_agent()
        if agent is None:
            return {"tabs": [], "current_snapshot": None}
        return {
            "tabs": agent.tabs(),
            "current_snapshot": agent.current_page(),
        }

    def browser_execute(self, action_dict):
        agent = self.c.engine._get_browser_agent()
        if agent is None:
            return {"ok": False, "message": "Browser agent unavailable — install Playwright"}
        return agent.execute_action(action_dict)

    def minimize(self):
        if self.c.window:
            self.c.window.minimize()

    def close(self):
        # Trigger a hard exit so no background threads linger.
        threading.Thread(target=self.c._hard_exit, daemon=True).start()


if __name__ == "__main__":
    NaitroWebController().start()
