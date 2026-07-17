"""
webview_ui.py — JARVIS's web-based control panel.

This is an alternative front-end to the Tkinter JarvisUI in JARVIS_app.py.
It renders web/index.html (HTML/CSS/JS) inside a native window via
pywebview, and talks to the *exact same* JarvisEngine used by the Tkinter
UI and covered by the test suite — this file adds zero new decision-making
logic of its own for anything engine-related. It only:

  1. Exposes a small JS-callable API (Api class) that forwards into
     JarvisEngine methods.
  2. Ports JarvisUI.voice_loop's wake-word/conversation-window dispatch
     (unchanged in behavior) so voice control still works from this UI.
  3. Streams engine.log() output into the page's log feed.

Run with:  python webview_ui.py
Requires:  pip install pywebview
"""
from __future__ import annotations

import dataclasses
import threading
import time
from pathlib import Path

import webview

from JARVIS_app import ActionResult, CONFIG_PATH, JarvisEngine

WEB_DIR = Path(__file__).resolve().parent / "web"


def _result_dict(result: ActionResult) -> dict:
    if isinstance(result, ActionResult):
        return dataclasses.asdict(result)
    # A few engine paths (e.g. threaded ones) return None; treat as ack.
    return {"ok": True, "message": ""}


class JarvisWebController:
    """Owns the engine, the pywebview window, and the ported voice loop."""

    def __init__(self, config_path=CONFIG_PATH):
        self.engine = JarvisEngine(config_path=config_path, log=self._on_engine_log)
        self.window: webview.Window | None = None
        self.voice_running = False
        self._voice_lock = threading.Lock()
        self.conversation_active = False
        self.last_interaction_time = 0.0

    # ---------------- window lifecycle ----------------

    def start(self):
        api = Api(self)
        self.window = webview.create_window(
            "JARVIS",
            url=str(WEB_DIR / "index.html"),
            js_api=api,
            width=1180,
            height=760,
            min_size=(860, 600),
            background_color="#050308",
            frameless=True,
            easy_drag=True,
        )
        webview.start(self._on_ready, debug=False)

    def _on_ready(self):
        threading.Thread(target=self._greet_later, daemon=True).start()

    def _greet_later(self):
        time.sleep(0.6)
        self.engine.respond("Good to see you, sir. What are we doing today?")
        # Deliberately not opening the conversation window here — JARVIS
        # should wait for the wake phrase, same as the Tkinter UI. See
        # voice_loop() below for the full reasoning.
        if self.engine.config.get("voice", {}).get("auto_start", True):
            self.start_voice()

    # ---------------- log bridge ----------------

    def _on_engine_log(self, text: str):
        if not self.window:
            return
        safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        try:
            self.window.evaluate_js(f"window.jarvisLog(`{safe}`)")
        except Exception:
            pass  # window may be closing

    # ---------------- voice loop (ported from JarvisUI.voice_loop) ----------------

    def start_voice(self):
        with self._voice_lock:
            if self.voice_running:
                return
            self.voice_running = True
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

        self.engine.log(f"JARVIS: heard options — {', '.join(alternatives[:3])}")
        for candidate in alternatives:
            if self.engine.was_addressed_to_jarvis(candidate) or self.is_actionable_voice_command(candidate):
                return self.engine.repair_wake_mishear(candidate)
        return self.engine.repair_wake_mishear(alternatives[0])

    def is_shutdown_request(self, text):
        norm = self.engine.normalize(text)
        command = self.engine.strip_wake_phrase(norm)
        shutdown_phrases = {
            "shut down jarvis", "shutdown jarvis", "exit jarvis", "quit jarvis",
            "close jarvis", "power off jarvis", "turn off jarvis",
            "goodbye jarvis", "bye jarvis",
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
            "show jarvis", "open jarvis", "bring up jarvis", "show yourself",
            "come back", "jarvis show", "jarvis open", "wake up jarvis",
        }
        show_commands = {"show yourself", "show", "come back", "wake up"}
        return norm in show_phrases or command in show_commands

    def voice_loop(self):
        try:
            import speech_recognition as sr
        except ImportError:
            self.engine.log("JARVIS: SpeechRecognition not installed.")
            self.voice_running = False
            return

        recognizer = sr.Recognizer()
        voice = self.engine.config.get("voice", {})
        mic_index = voice.get("microphone_index")
        recognizer.dynamic_energy_threshold = True
        recognizer.energy_threshold = int(voice.get("energy_threshold", 450))
        recognizer.pause_threshold = float(voice.get("pause_threshold", 0.9))
        recognizer.phrase_threshold = float(voice.get("phrase_threshold", 0.45))

        try:
            with sr.Microphone(device_index=mic_index) as source:
                recognizer.adjust_for_ambient_noise(source, duration=1.2)
                while self.voice_running:
                    try:
                        if self.engine.is_audio_output_active():
                            time.sleep(0.12)
                            continue
                        audio = recognizer.listen(
                            source,
                            timeout=float(voice.get("listen_timeout", 5)),
                            phrase_time_limit=float(voice.get("phrase_time_limit", 9)),
                        )
                        if self.engine.is_audio_output_active():
                            self.engine.log("JARVIS: ignored voice while speaking.")
                            continue
                        text = self.recognize_best_text(recognizer, audio, sr)
                        if not text:
                            continue
                        self.engine.log(f"JARVIS: heard — {text}")

                        addressed = self.engine.was_addressed_to_jarvis(text)
                        window_open = self.engine.is_conversation_window_open(
                            self.conversation_active, self.last_interaction_time
                        )
                        if self.conversation_active and not window_open:
                            self.conversation_active = False
                            self.engine.log("JARVIS: conversation window timed out — say the wake word again.")

                        if addressed or window_open:
                            self.conversation_active = True
                            self.last_interaction_time = time.time()
                            if self.is_shutdown_request(text):
                                self.engine.respond("Shutting down. Goodbye, sir.")
                                threading.Timer(3.5, self._shutdown).start()
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
                        self.engine.log(f"JARVIS: voice error — {e}")
        except Exception as e:
            self.engine.log(f"JARVIS: mic error — {e}")
            self.voice_running = False

    def _shutdown(self):
        if self.window:
            self.window.destroy()


class Api:
    """JS-callable surface. Every method here is reachable in app.js as
    window.pywebview.api.<method_name>(...)."""

    def __init__(self, controller: JarvisWebController):
        self.c = controller

    # ---- dashboard data ----

    def get_dashboard_data(self):
        cfg = self.c.engine.config
        modes = cfg.get("modes", {})
        return {
            "wake_phrase": cfg.get("wake_phrase", "hey jarvis"),
            "user_title": cfg.get("conversation", {}).get("user_title", "sir"),
            "allow_push": bool(cfg.get("reviewer", {}).get("allow_push", False)),
            "speak_responses": bool(cfg.get("voice", {}).get("speak_responses", True)),
            "apps": {name.title(): {} for name in cfg.get("apps", {})},
            "folders": {name.title(): {} for name in cfg.get("folders", {})},
            "websites": {name.title(): {} for name in cfg.get("websites", {})},
            "modes": {
                name.title(): {"desc": f"{len(steps)} step{'s' if len(steps) != 1 else ''}"}
                for name, steps in modes.items()
            },
        }

    # ---- actions ----

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
            engine.config.setdefault("apps", {})[key] = {"type": "command", "target": target}
        elif kind == "folder":
            engine.config.setdefault("folders", {})[key] = target
        elif kind == "website":
            engine.config.setdefault("websites", {})[key] = target
        else:
            return {"ok": False, "message": f"Unknown item kind: {kind}"}
        engine.save_config()
        return {"ok": True, "message": f"Added {name} to {kind}s."}

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

    def get_status(self):
        return {
            "speaking": bool(self.c.engine._is_speaking),
            "listening": bool(self.c.voice_running),
            "conversation_active": bool(self.c.conversation_active),
        }

    # ---- window chrome ----

    def minimize(self):
        if self.c.window:
            self.c.window.minimize()

    def close(self):
        if self.c.window:
            self.c.window.destroy()


if __name__ == "__main__":
    JarvisWebController().start()
