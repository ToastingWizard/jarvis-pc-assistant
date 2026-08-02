"""
webview_ui.py — NaiTRO's web-based control panel.
"""
from __future__ import annotations


import dataclasses
import json
import os
import sys
import threading
import time
from pathlib import Path

import webview

from naitro_app import ActionResult, CONFIG_PATH, NaitroEngine


def resource_root() -> Path:
    """Project root in source mode; PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def web_index_path() -> Path:
    return resource_root() / "web" / "react-ui" / "dist" / "index.html"


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
    except Exception:
        pass
# #endregion


def _result_dict(result: ActionResult) -> dict:
    if isinstance(result, ActionResult):
        return dataclasses.asdict(result)
    return {"ok": True, "message": ""}


class NaitroWebController:

    def __init__(self, config_path=CONFIG_PATH):
        self.engine = NaitroEngine(config_path=config_path, log=self._on_engine_log)
        self.window: webview.Window | None = None
        self.voice_running = False
        self._voice_lock = threading.Lock()
        self.conversation_active = False
        self.last_interaction_time = 0.0

    def start(self):
        web_index = web_index_path()
        frozen = getattr(sys, "frozen", False)
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
            raise FileNotFoundError(
                f"React UI build not found at {web_index}. "
                f"Run: cd web/react-ui && npm install && npm run build"
            )
        api = Api(self)
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
        webview.start(self._on_ready, debug=False)
        # webview.start() blocks until the window is closed.
        # When it returns, force a clean process exit so no background
        # threads (voice loop, TTS worker, etc.) keep NaiTRO alive
        # invisibly — which is exactly what caused the "4 NaiTROes
        # talking at once" bug.
        os._exit(0)

    def _on_ready(self):
        threading.Thread(target=self._greet_later, daemon=True).start()

    def _greet_later(self):
        time.sleep(0.6)
        self.engine.respond("Good to see you, sir. What are we doing today?")
        if self.engine.config.get("voice", {}).get("auto_start", True):
            self.start_voice()

    def _on_engine_log(self, text: str):
        if not self.window:
            return
        safe = text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
        try:
            self.window.evaluate_js(f"window.naitroLog(`{safe}`)")
        except Exception:
            pass

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
        except Exception as e:
            self.engine.log(f"NaiTRO: mic error — {e}")
            self.voice_running = False

    def _hard_exit(self):
        """Destroy the window and force the process to exit cleanly."""
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
        modes = cfg.get("modes", {})
        return {
            "wake_phrase": cfg.get("wake_phrase", "hey naitro"),
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

    def minimize(self):
        if self.c.window:
            self.c.window.minimize()

    def close(self):
        # Trigger a hard exit so no background threads linger.
        threading.Thread(target=self.c._hard_exit, daemon=True).start()


if __name__ == "__main__":
    NaitroWebController().start()
