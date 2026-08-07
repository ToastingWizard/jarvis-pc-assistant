import json
import os
import queue
import difflib
import random
import re
import shutil
import shlex
import socket
import subprocess
import threading
import time
import urllib.parse
import webbrowser
import math

from app_launcher import (
    resolve_app, finalize_app_entry, validate_apps, launch_windows,
    set_icon_log,
)
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    Button,
    Canvas,
    Entry,
    Frame,
    Label,
    Listbox,
    StringVar,
    Text,
    Tk,
    Toplevel,
    filedialog,
    messagebox,
    ttk,
)

import sys

import diagnostics

if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    APP_DIR = Path(sys.executable).resolve().parent
else:
    # Running as normal .py script, now living in Python/ -- config/ is a
    # sibling folder one level up, per the reorganized project structure.
    APP_DIR = Path(__file__).resolve().parent.parent / "config"


def _real_config_candidates():
    """Real config files to search, in priority order.

    Source mode: the repo's ``config/config.json`` only.

    Frozen mode: first the source-layout sibling ``dist/../config/`` —
    an EXE launched from a repo checkout must use the SAME config that
    ``python Python/naitro_app.py`` uses.  Before this fix the packaged
    app blindly read a stale, auto-seeded ``dist/config.json`` and
    ignored the user's real config entirely.  Then a portable
    ``config.json`` next to the EXE (the standalone-deployment case).
    """
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).resolve().parent
        return [
            exe_dir.parent / "config" / "config.json",  # repo checkout: dist/../config
            exe_dir / "config.json",                    # portable: next to the EXE
        ]
    return [Path(__file__).resolve().parent.parent / "config" / "config.json"]


def _resolve_config_path():
    """First existing candidate wins; otherwise the primary path, so a
    fresh install seeds a new config in the same place as before."""
    candidates = _real_config_candidates()
    for cand in candidates:
        if cand.is_file():
            return cand
    return candidates[0]


CONFIG_PATH = _resolve_config_path()


def _config_candidates():
    """Every config location the app knows about, in search order, for the
    startup log.  Mirrors ``_real_config_candidates()`` and also notes the
    bundled example under ``_MEIPASS`` (a seed template — never treated as
    a real config)."""
    candidates = [str(c) for c in _real_config_candidates()]
    if getattr(sys, 'frozen', False):
        meipass_dir = getattr(sys, '_MEIPASS', None)
        if meipass_dir:
            candidates.append(str(Path(meipass_dir) / "config" / "config.example.json"))
    return candidates


diagnostics.init()
diagnostics.log_extra("naitro_app.__file__", __file__)
diagnostics.log_extra("APP_DIR", str(APP_DIR))
diagnostics.log_extra("CONFIG_PATH", str(CONFIG_PATH))
diagnostics.log_config_search(str(CONFIG_PATH), _config_candidates())

# Short acknowledgements spoken once, right before the FIRST voice command
# of a session is executed. Startup itself stays silent so listening can
# begin the instant NaiTRO launches -- see NaitroEngine.greet_first_command().
WELCOME_BACK_MESSAGES = (
    "Welcome back. I'll get that right away.",
    "Good to see you again. Working on it.",
)

# Spoken phrases that turn the active mode off (see run_command).
_DEACTIVATE_MODE_PHRASES = frozenset({
    "baseline",
    "deactivate mode",
    "disable mode",
    "turn off mode",
    "turn off the mode",
    "exit mode",
    "leave mode",
    "stop mode",
    "mode off",
})

DEFAULT_CONFIG = {
    "wake_phrase": "hey naitro",
    "voice": {
        "enabled": False,
        "speak_responses": True,
        "microphone_index": None,
        "listen_timeout": 5,
        "phrase_time_limit": 9,
        "energy_threshold": 450,
        "ambient_energy_multiplier": 1.8,
        "pause_threshold": 0.9,
        "phrase_threshold": 0.45,
        "log_unrecognized": False,
        "auto_start": True,
        "tts_engine": "edge_tts",
        "edge_voice": "en-GB-RyanNeural",
        "edge_rate": "-4%",
        "edge_volume": "+0%",
        "pyttsx3_rate": 175,
    },
    "conversation": {
        "enabled": True,
        "name": "NaiTRO",
        "user_title": "sir",
        "style": "calm, witty, loyal butler",
        "session_timeout_seconds": 600,
    },
    "apps": {
        "notepad": {"type": "command", "target": "notepad"},
        "calculator": {"type": "command", "target": "calc"},
        "chrome": {"type": "command", "target": "chrome"},
        "spotify": {"type": "command", "target": "spotify"},
    },
    "websites": {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.com",
        "netflix": "https://www.netflix.com",
    },

    "website_cache": {},
 
    "playlists": {
        "liked songs": "spotify:collection:tracks",
        "discover weekly": "spotify:playlist:37i9dQZEVXcQ",
    },
    "music": {
        "service": "spotify",
        "default_playlist": "liked songs",
    },
    "folders": {
        "downloads": str(Path.home() / "Downloads"),
        "desktop": str(Path.home() / "Desktop"),
    },
    "modes": {
        "chill mode": [
            {"type": "app", "name": "chrome", "delay": 1},
            {"type": "website", "name": "netflix"},
        ],
    },
    # Entries the user deleted from the launcher. deep_merge_defaults must
    # never re-seed a default app/website the user explicitly removed.
    "removed": {
        "apps": [],
        "websites": [],
        "folders": [],
        "playlists": [],
    },
    # The currently-active mode (if any). Persisted so a personality mode's
    # AI style survives restarts. None = baseline.
    "active_mode": None,
    "projects": {
        "naitro": ".",
    },
    "reviewer": {
        "default_project": "naitro",
        "editor": "pycharm",
        "pycharm_exe": "",
        "allow_push": False,
        "use_ai": True,
        "merge_rule_findings": True,
        "max_diff_chars": 60000,
        "ollama_model": "phi3:mini",
    },
    "browser": {
        "headless": False,
        "channel": "",
        "executable_path": "",
        "default_timeout_ms": 15000,
        "download_dir": "",
        "screenshot_dir": "",
    },
}

@dataclass
class ActionResult:
    ok: bool
    message: str

# Signals used by is_suspicious_url() to flag a freshly *discovered*
# website (one found via find_website's live search, never opened
# before) before it's ever auto-opened or saved. None of these prove a
# site is malicious on their own, but any one of them is enough reason
# to ask "are you sure?" instead of silently opening it -- see
# open_target()'s find_website branch and handle_pending_confirmation's
# "open_url" case for how the confirmation itself works.
SUSPICIOUS_TLDS = {
    "zip", "mov", "top", "click", "country", "gq", "tk", "ml", "cf",
    "ga", "work", "support", "loan", "download", "review", "kim",
    "men", "party", "date", "stream", "science",
}
URL_SHORTENERS = {
    "bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd",
    "buff.ly", "rebrand.ly", "cutt.ly", "shorturl.at",
}

class NaitroEngine:
    def __init__(self, config_path=CONFIG_PATH, log=None):
        self.config_path = Path(config_path)
        # Every engine log line is ALSO written to logs/startup.log, so
        # nothing the engine reports is lost before the UI bridge exists
        # (in frozen mode the webview window is not up during __init__).
        base_log = log or (lambda text: None)

        def _log(text):
            diagnostics.log(text)
            base_log(text)

        self.log = _log
        set_icon_log(self.log)
        self.discovered_apps = None
        diagnostics.mark(f"NaitroEngine.__init__ loading config: {self.config_path}")
        self.config = self.load_config()
        diagnostics.mark("NaitroEngine.__init__ config loaded")
        self._is_speaking = False
        self._speech_cooldown_until = 0
        self._tts_engine = None
        self._speech_queue = queue.Queue()
        self._speech_worker_started = False
        self.last_review = None
        self.pending_confirmation = None
        self._browser_agent = None
        # Set once the first voice command of this session has been
        # acknowledged -- see greet_first_command(). Resets naturally on
        # every fresh process launch since this is instance state, not
        # persisted config.
        self.session_greeted = False

    def is_windows(self):
        return os.name == "nt"

    def is_suspicious_url(self, url):
        """Heuristic-only check for a freshly *discovered* website (see
        SUSPICIOUS_TLDS/URL_SHORTENERS above) -- not a real reputation
        service, just enough to catch the obvious red flags (raw IP
        addresses, punycode/homograph domains, link shorteners that hide
        the real destination, throwaway TLDs commonly abused for
        phishing/malware) before find_website's search result gets
        auto-opened. Saved websites and anything already in
        website_cache never pass through here -- only a brand-new
        search result does."""
        try:
            host = (urllib.parse.urlparse(url).hostname or "").lower()
        except Exception:
            return True
        if not host:
            return True
        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host):
            return True  # raw IP, no real domain at all
        if host.startswith("xn--") or ".xn--" in host:
            return True  # punycode -- classic homograph-attack pattern
        if host in URL_SHORTENERS:
            return True  # can't tell where this actually leads
        tld = host.rsplit(".", 1)[-1]
        if tld in SUSPICIOUS_TLDS:
            return True
        if host.count("-") >= 4:
            return True  # heavily hyphenated, typosquat-style domain
        return False

    def quiet_subprocess_kwargs(self):
        if self.is_windows() and hasattr(subprocess, "CREATE_NO_WINDOW"):
            return {"creationflags": subprocess.CREATE_NO_WINDOW}
        return {}

    def open_system_target(self, target):
        target = str(target)
        if self.is_windows():
            os.startfile(target)
            return
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        if shutil.which(opener):
            subprocess.Popen([opener, target], **self.quiet_subprocess_kwargs())
            return
        webbrowser.open(target)

    def load_config(self):
        with diagnostics.timing(f"load_config ({self.config_path})"):
            diagnostics.lookup("config", "config path", str(self.config_path))
            if not self.config_path.exists():
                diagnostics.log(
                    f"[config] '{self.config_path}' missing — seeding from DEFAULT_CONFIG"
                )
                self.save_config(DEFAULT_CONFIG)
            try:
                with self.config_path.open("r", encoding="utf-8-sig") as file:
                    config = json.load(file)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                # A truncated/corrupted config (e.g. interrupted write or
                # a hand-edit typo) must never brick the app. Back the bad
                # file up, reseed from defaults, and keep booting so a demo
                # machine recovers instead of crashing on launch.
                backup = self.config_path.with_name(
                    f"{self.config_path.name}.bak-{int(time.time())}"
                )
                try:
                    backup.write_bytes(self.config_path.read_bytes())
                except Exception:
                    pass
                diagnostics.log(
                    f"[config] '{self.config_path.name}' unparseable ({exc}) — "
                    f"backed up to {backup.name} and reseeded from DEFAULT_CONFIG"
                )
                self.save_config(DEFAULT_CONFIG)
                with self.config_path.open("r", encoding="utf-8-sig") as file:
                    config = json.load(file)
            migrated, changed = self.migrate_config(config)
            if changed:
                self.save_config(migrated)
            return migrated

    def migrate_config(self, config):
        changed = False
        config, did_change = self.deep_merge_defaults(config, DEFAULT_CONFIG)
        changed = changed or did_change
        # Validate app entries: fill missing display_names, mark unavailable,
        # extract icons where possible.
        try:
            with diagnostics.timing("migrate_config.validate_apps"):
                if validate_apps(config, log=self.log):
                    changed = True
        except Exception as e:
            diagnostics.exception("validate_apps", e)
            self.log(f"App validation error: {e}")
        return config, changed

    def deep_merge_defaults(self, config, defaults):
        changed = False
        for key, value in defaults.items():
            if key not in config:
                config[key] = value
                changed = True
            elif isinstance(value, dict) and isinstance(config.get(key), dict):
                config[key], child_changed = self.deep_merge_defaults(config[key], value)
                changed = changed or child_changed
        # Honor deletions: never resurrect an entry the user removed from
        # the launcher (see the "removed" section in DEFAULT_CONFIG).
        removed = config.get("removed") or {}
        for section, names in removed.items():
            bucket = config.get(section)
            if isinstance(bucket, dict) and names:
                for name in names:
                    if bucket.pop(name, None) is not None:
                        changed = True
        return config, changed

    def save_config(self, config=None):
        data = config if config is not None else self.config
        # Atomic write: dump to a temp file then os.replace() it over the
        # real path. A crash / os._exit(0) mid-write can never leave a
        # truncated config.json that bricks the next launch.
        tmp_path = self.config_path.with_name(self.config_path.name + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
        os.replace(tmp_path, self.config_path)

    def refresh(self):
        self.discovered_apps = None
        self.config = self.load_config()

    def _get_tts_engine(self):
        if self._tts_engine is None:
            try:
                import pyttsx3
                self._tts_engine = pyttsx3.init()
            except Exception:
                self._tts_engine = None
        return self._tts_engine

    def _ensure_speech_worker(self):
        # One persistent thread owns all speech. This fixes two bugs:
        # (1) on Linux, creating a fresh pyttsx3 engine per call could get
        #     garbage-collected mid-speech while espeak's C callback still
        #     referenced it, producing glitchy/garbled audio or crashes;
        # (2) on Windows, pyttsx3's SAPI5 driver is thread-affinity
        #     sensitive, so the engine must always run on the SAME thread
        #     it was created on -- a single long-lived worker guarantees
        #     that instead of a new thread spinning up per response.
        if self._speech_worker_started:
            return
        self._speech_worker_started = True

        def _worker():
            while True:
                text = self._speech_queue.get()
                try:
                    self._is_speaking = True
                    voice_config = self.config.get("voice", {})
                    if voice_config.get("tts_engine", "pyttsx3") == "edge_tts":
                        self.speak_with_edge_tts(text, voice_config)
                    else:
                        self.speak_with_pyttsx3(text, voice_config)
                    self._speech_cooldown_until = time.time() + 1.25
                except Exception as e:
                    self.log(f"TTS Error: {e}")
                    try:
                        self.speak_with_pyttsx3(text, self.config.get("voice", {}))
                    except Exception as fallback_error:
                        self.log(f"TTS fallback error: {fallback_error}")
                    self._speech_cooldown_until = time.time() + 0.75
                finally:
                    self._is_speaking = False
                    self._speech_queue.task_done()

        threading.Thread(target=_worker, daemon=True).start()

    def respond(self, text):
        self.log(f"NaiTRO: {text}")
        self._speech_cooldown_until = max(self._speech_cooldown_until, time.time() + 1.5)
        if self.config.get("voice", {}).get("speak_responses", True):
            self._ensure_speech_worker()
            self._speech_queue.put(text)

    def greet_first_command(self):
        """Speak a short, once-per-session acknowledgement right as the
        first voice command is recognized -- never at startup.

        This is called from the voice loop the instant a command is
        confirmed to be addressed to NaiTRO, immediately before that
        command is executed. respond() only enqueues text onto the
        speech worker's queue and returns right away, so this never
        delays recognizing or running the command that triggered it.
        """
        if self.session_greeted:
            return
        self.session_greeted = True
        self.respond(random.choice(WELCOME_BACK_MESSAGES))

    def is_audio_output_active(self):
        return self._is_speaking or time.time() < self._speech_cooldown_until

    def speak_with_pyttsx3(self, text, voice_config):
        engine = self._get_tts_engine()
        if engine is None:
            raise RuntimeError("pyttsx3 engine unavailable")
        rate = voice_config.get("pyttsx3_rate")
        if rate:
            engine.setProperty("rate", int(rate))
        engine.say(text)
        engine.runAndWait()

    def speak_with_edge_tts(self, text, voice_config):
        import asyncio
        import tempfile
        import uuid

        import edge_tts

        async def _save_audio(path):
            # edge_tts supports native connect/receive timeouts (its
            # defaults of 10s/60s can stall a voice reply on a dead
            # network). Honor the values configured in voice.* — a
            # timeout surfaces as an exception the speech worker catches
            # and falls back to pyttsx3 instead of hanging forever.
            communicate = edge_tts.Communicate(
                text,
                voice_config.get("edge_voice", "en-GB-RyanNeural"),
                rate=voice_config.get("edge_rate", "-4%"),
                volume=voice_config.get("edge_volume", "+0%"),
                connect_timeout=int(voice_config.get("edge_connect_timeout", 3)),
                receive_timeout=int(voice_config.get("edge_receive_timeout", 20)),
            )
            await communicate.save(path)

        temp_path = os.path.join(tempfile.gettempdir(), f"naitro_tts_{uuid.uuid4().hex}.mp3")
        alias = f"naitro_tts_{uuid.uuid4().hex}"
        try:
            asyncio.run(_save_audio(temp_path))
            self.play_audio_file(temp_path, alias)
        finally:
            try:
                os.remove(temp_path)
            except Exception:
                pass

    def play_audio_file(self, path, alias):
        if not self.is_windows():
            players = (
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
                ["mpg123", "-q", path],
                ["mpv", "--no-video", "--really-quiet", path],
                ["cvlc", "--play-and-exit", "--quiet", path],
            )
            for command in players:
                if shutil.which(command[0]):
                    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
            self.log(
                "No audio player found (install ffmpeg, mpg123, mpv, or vlc) "
                "-- skipping spoken playback for this response."
            )
            return

        import ctypes
        winmm = ctypes.windll.winmm

        def mci(command):
            buffer = ctypes.create_unicode_buffer(255)
            result = winmm.mciSendStringW(command, buffer, 254, 0)
            if result != 0:
                raise RuntimeError(f"MCI audio command failed: {command}")
            return buffer.value

        mci(f'open "{path}" type mpegvideo alias {alias}')
        try:
            mci(f"play {alias} wait")
        finally:
            try:
                mci(f"close {alias}")
            except Exception:
                pass

    def run_command(self, raw_command):
        command = self.strip_wake_phrase(raw_command)
        title = self.config.get("conversation", {}).get("user_title", "sir")
        self.log(f"YOU: {raw_command}")
        if not command:
            self.respond("I am here. What are we doing today?")
            return ActionResult(True, "Ready")

        confirmation_result = self.handle_pending_confirmation(command)
        if confirmation_result is not None:
            return confirmation_result

        music_target = self.extract_music_target(command)
        if music_target:
            kind, target = music_target
            return self.play_music(target, kind)

        if any(p in command for p in ("start ollama", "load ollama", "wake up ollama")):
            def _start():
                subprocess.Popen(["ollama", "serve"], **self.quiet_subprocess_kwargs())
                time.sleep(2)
                self.respond(f"Ollama is running, {title}. AI is online.")
            threading.Thread(target=_start, daemon=True).start()
            return ActionResult(True, "ollama started")

        if any(p in command for p in ("stop ollama", "close ollama", "kill ollama")):
            if self.is_windows():
                subprocess.run(["taskkill", "/f", "/im", "ollama.exe"], capture_output=True, **self.quiet_subprocess_kwargs())
            else:
                subprocess.run(["pkill", "-f", "ollama"], capture_output=True)
            self.respond(f"Ollama stopped, {title}. VRAM is free for gaming.")
            return ActionResult(True, "ollama stopped")

        review_action = self.extract_review_action(command)
        if review_action:
            kind, target = review_action
            if kind == "review":
                return self.review_project(target)
            if kind == "open_issue":
                return self.open_review_issue(target)
            if kind == "fix_issue":
                return self.apply_review_fix(target)
            if kind == "push":
                return self.push_project(target)

        # Browser agent — "browser ...", "browse ...", "automate ..."
        browser_result = self._handle_browser_command(command)
        if browser_result is not None:
            return browser_result

        # Mode deactivation — handled before extract_action_target so phrases
        # like "exit mode" / "stop mode" don't get captured by the close_/
        # stop_ prefixes below.
        if self.normalize(command) in _DEACTIVATE_MODE_PHRASES:
            return self.deactivate_mode()

        action_target = self.extract_action_target(command)
        if action_target:
            action, target = action_target
            if action == "search":
                return self.search_web(target)
            if action == "mode":
                return self.run_mode(target)
            if action == "close":
                return self.close_app(target)
            if action in ("focus", "minimize", "maximize", "restore"):
                return self.control_window(action, target)
            if action == "open":
                targets = self.split_multi_targets(target)
                if len(targets) > 1:
                    return self.open_multiple_targets(targets)
            return self.open_target(target)
        
        # Fallback to best target match
        known = self.best_target(command)
        if known:
            kind, name = known
            if kind == "modes": return self.run_mode(name)
            if kind == "playlists": return self.play_music(name, "playlist")
            return self.open_target(name)

        return self.chat(command)

    def normalize(self, text):
        text = text.strip().lower()
        text = re.sub(r"[^a-z0-9:/?.&%+,\-\\ ]+", " ", text)
        return text.strip()

    def strip_wake_phrase(self, text):
        command = self.normalize(text)
        wake = self.normalize(self.config.get("wake_phrase", "hey naitro"))
        command = self.repair_wake_mishear(command)
        # Exact strip
        if command.startswith(wake):
            return self.repair_command_mishear(command[len(wake):].strip())
        # Try stripping first 1-2 words if they look like the wake phrase
        words = command.split()
        for n in (2, 1):
            prefix = " ".join(words[:n])
            if difflib.SequenceMatcher(None, prefix, wake).ratio() > 0.6:
                return self.repair_command_mishear(" ".join(words[n:]).strip())
        return self.repair_command_mishear(command)

    def repair_wake_mishear(self, command):
        wake = self.normalize(self.config.get("wake_phrase", "hey naitro"))
        aliases = (
            "hazardous", "hey hazardous", "hazard is", "hey hazard is",
            "hey service", "service", "jarves", "naitro", "travis",
            "hey travis", "hey jarves", "hey jars", "javis", "hey javis",
            "naitro open", "hazardous open"
        )
        words = command.split()
        for alias in aliases:
            if command.startswith(alias):
                rest = command[len(alias):].strip()
                return f"hey naitro {rest}".strip()

        # Google sometimes returns a short phrase that sounds close but is not spelled close.
        for n in (2, 1):
            prefix = " ".join(words[:n])
            if prefix and difflib.SequenceMatcher(None, prefix, wake).ratio() > 0.55:
                return f"hey naitro {' '.join(words[n:])}".strip()
        return command

    def repair_command_mishear(self, command):
        command = self.normalize(command)
        command = re.sub(r"\b(shut\s*down|shutdown|exit|quit|close|power off|turn off|goodbye|bye)\s+jar\b", r"\1 naitro", command)
        command = re.sub(r"\b(start|load|wake up|stop|close|kill)\s+(ola|olama|llama)\b", r"\1 ollama", command)
        return command

    def extract_action_target(self, command):
        command = self.normalize(command)
        close_prefixes = ["close ", "quit ", "kill ", "exit ", "stop ", "shut down ", "shutdown "]
        for prefix in close_prefixes:
            if command.startswith(prefix):
                return "close", command[len(prefix):].strip()

        mode_prefixes = ["activate ", "enable "]
        for prefix in mode_prefixes:
            if command.startswith(prefix):
                return "mode", command[len(prefix):].strip()

        # Desktop window control (see focus_window/minimize_window/etc.
        # below) -- distinct from "close X" above, which kills the whole
        # process rather than just managing its window.
        window_actions = {
            "focus ": "focus", "switch to ": "focus", "show me ": "focus",
            "minimize ": "minimize", "minimise ": "minimize",
            "maximize ": "maximize", "maximise ": "maximize",
            "restore ": "restore", "unminimize ": "restore",
        }
        for prefix, action in window_actions.items():
            if command.startswith(prefix):
                return action, command[len(prefix):].strip()

 

        search_prefixes = ["search for ", "search ", "google ", "look up "]
        for prefix in search_prefixes:
            if command.startswith(prefix):
                return "search", command[len(prefix):].strip()

        open_prefixes = ["open ", "launch ", "start ", "run ", "pull up ", "bring up "]
        for prefix in open_prefixes:
            if command.startswith(prefix):
                target = command[len(prefix):].strip()
                # If the target matches a known mode name, treat it as a mode
                if target in self.config.get("modes", {}):
                    return "mode", target
                # Also check if target ends with "mode" and a close match exists
                modes = self.config.get("modes", {})
                if target in modes:
                    return "mode", target
                return "open", target

        # No prefix — check if bare command is a mode name
        if command in self.config.get("modes", {}):
            return "mode", command

        return None

    def is_known_target_name(self, name):
        name = self.normalize(name)
        for kind in ("modes", "apps", "websites", "playlists", "folders"):
            if name in self.config.get(kind, {}):
                return True
        return False

    def find_app_entry(self, name):
        """Find an app by exact, prefix, substring, or fuzzy match against
        config keys and installed apps.  Returns (config_key_or_name, entry)
        or None."""
        name = self.normalize(name)
        apps = self.config.get("apps", {})

        # Exact match
        if name in apps:
            return name, apps[name]

        # Prefix / substring match ("google chrome" contains "chrome",
        # "obs" is a prefix of "obs studio" in config)
        best_key = None
        best_score = 0
        for key in apps:
            if key.startswith(name) and len(name) >= 3:
                score = 0.8 + 0.2 * (len(name) / max(len(key), 1))
            elif name.startswith(key):
                score = 0.6 + 0.3 * (len(key) / max(len(name), 1))
            elif key in name:
                score = len(key) / max(len(name), 1)
            elif name in key:
                score = len(name) / max(len(key), 1) * 0.5
            else:
                continue
            if score > best_score:
                best_score = score
                best_key = key
        if best_key and best_score >= 0.5:
            return best_key, apps[best_key]

        # Fuzzy match (config keys only — user-added apps, so safe to be looser)
        matches = difflib.get_close_matches(
            name, list(apps.keys()), n=1, cutoff=0.7
        )
        if matches:
            return matches[0], apps[matches[0]]

        # Live discovery against installed apps (Start Menu / App Paths)
        if self.is_windows():
            resolved = resolve_app(name)
            if resolved and resolved.get("available"):
                entry = {
                    "type": ("shortcut" if resolved.get("kind") == "shortcut"
                             else "exe"),
                    "target": (resolved.get("launch")
                               or resolved.get("exe_path", name)),
                    "display_name": resolved.get("display_name", name.title()),
                    "exe_path": resolved.get("exe_path", ""),
                    "available": True,
                }
                return name, entry
        return None

    def split_multi_targets(self, target):
        target = self.normalize(target)
        if not target or self.is_known_target_name(target):
            return [target] if target else []

        parts = [
            part.strip()
            for part in re.split(r"\s*(?:,|\band\b|\bplus\b|\bwith\b)\s*", target)
            if part.strip()
        ]
        if len(parts) < 2:
            return [target]
        return parts

    def best_target(self, command):
        command = self.normalize(command)
        # Exact match first
        for kind in ["modes", "apps", "websites", "playlists", "folders"]:
            data = self.config.get(kind, {})
            if command in data:
                return kind, command
        # Fuzzy match across all kinds
        for kind in ["modes", "apps", "websites", "playlists", "folders"]:
            data = self.config.get(kind, {})
            matches = difflib.get_close_matches(command, data.keys(), n=1, cutoff=0.75)
            if matches:
                return kind, matches[0]
        # Substring match for apps ("google chrome" -> "chrome")
        apps = self.config.get("apps", {})
        for key in apps:
            if key in command and len(key) >= 3:
                return "apps", key
        # Live discovery against installed apps
        if self.is_windows():
            resolved = resolve_app(command)
            if resolved and resolved.get("available"):
                return "apps", command
        return None

    def extract_music_target(self, command):
        command = self.normalize(command)
        if command in ("play music", "start music", "resume music", "put on music"):
            default_playlist = self.config.get("music", {}).get("default_playlist", "")
            return "playlist", default_playlist or "liked songs"

        playlist_patterns = (
            r"^(?:play|start|put on)\s+(.+?)\s+playlist$",
            r"^(?:play|start|put on)\s+playlist\s+(.+)$",
        )
        for pattern in playlist_patterns:
            match = re.match(pattern, command)
            if match:
                return "playlist", match.group(1).strip()

        song_patterns = (
            r"^(?:play|start|put on)\s+song\s+(.+)$",
            r"^(?:play|start|put on)\s+(.+?)\s+on\s+spotify$",
            r"^(?:play|start|put on)\s+(.+)$",
        )
        for index, pattern in enumerate(song_patterns):
            match = re.match(pattern, command)
            if match:
                target = match.group(1).strip()
                if target and target not in ("music", "spotify"):
                    if index == 2 and self.best_target(target):
                        return None
                    return "track", target

        return None

    def play_music(self, target, kind="track"):
        target = self.normalize(target)
        playlists = self.config.get("playlists", {})

        if kind == "playlist":
            playlist_name = self.best_playlist_name(target)
            if playlist_name:
                url = playlists[playlist_name]
                self.respond(f"Playing {playlist_name}, sir.")
                self.open_url(url)
                return ActionResult(True, url)
            if target:
                self.respond(f"I do not have a playlist called {target}, sir. Searching Spotify instead.")
                return self.open_spotify_search(target)

        if target in playlists:
            self.respond(f"Playing {target}, sir.")
            self.open_url(playlists[target])
            return ActionResult(True, playlists[target])

        return self.open_spotify_search(target)

    def best_playlist_name(self, target):
        playlists = self.config.get("playlists", {})
        if not target:
            return None
        if target in playlists:
            return target
        stripped = target.replace(" playlist", "").strip()
        if stripped in playlists:
            return stripped
        matches = difflib.get_close_matches(stripped, playlists.keys(), n=1, cutoff=0.72)
        return matches[0] if matches else None

    def open_spotify_search(self, query):
        query = self.normalize(query)
        if not query:
            return self.play_music(self.config.get("music", {}).get("default_playlist", "liked songs"), "playlist")
        encoded = urllib.parse.quote(query)
        spotify_uri = f"spotify:search:{encoded}"
        web_url = f"https://open.spotify.com/search/{encoded}"
        self.respond(f"Looking for {query} on Spotify, sir.")
        try:
            self.open_system_target(spotify_uri)
            return ActionResult(True, spotify_uri)
        except Exception:
            self.open_url(web_url)
            return ActionResult(True, web_url)

    def open_url(self, url):
        try:
            self.open_system_target(url)
        except Exception:
            webbrowser.open(url)

    def open_multiple_targets(self, names):
        names = [self.normalize(name) for name in names if self.normalize(name)]
        if not names:
            return ActionResult(False, "No targets")

        if len(names) == 2:
            spoken = f"{names[0]} and {names[1]}"
        else:
            spoken = f"{', '.join(names[:-1])}, and {names[-1]}"
        self.respond(f"Opening {spoken}, sir.")

        failures = []
        for name in names:
            result = self.open_target(name, announce=False)
            if not result.ok:
                failures.append(name)
            time.sleep(0.35)

        if failures:
            self.respond(f"I could not find {', '.join(failures)}, sir.")
            return ActionResult(False, f"Missing: {', '.join(failures)}")
        return ActionResult(True, f"Opened {spoken}")

    def open_target(self, name, announce=True):
        name = self.normalize(name)

        # Prefer apps over websites when names overlap, e.g. Spotify.
        # find_app_entry handles exact, prefix, substring, fuzzy, and
        # live discovery against installed apps.
        match = self.find_app_entry(name)
        if match:
            config_key, app = match
            target = app.get("target", config_key)
            if announce:
                self.respond(f"Opening {name}, sir.")
            return self.launch(target, name=config_key)

        site = self.config.get("websites", {}).get(name)
        if site:
            if announce:
                self.respond(f"Opening {name} in your browser, sir.")
            self.open_url(site)
            return ActionResult(True, site)

        playlist = self.config.get("playlists", {}).get(name)
        if playlist:
            if announce:
                self.respond(f"Playing {name}, sir.")
            self.open_url(playlist)
            return ActionResult(True, playlist)

        # Check Folders
        folder = self.config.get("folders", {}).get(name)
        if folder:
            expanded = os.path.expandvars(folder)
            if announce:
                self.respond(f"Opening your {name} folder, sir.")
            return self.launch(expanded)


        # Learned website cache: a URL the website finder already found
        # once (see find_website below). Checking this before searching
        # again means a repeat "open X" is instant, not a fresh search.
        cached = self.config.get("website_cache", {}).get(name)
        if cached:
            if announce:
                self.respond(f"Opening {name} in your browser, sir.")
            self.open_url(cached)
            return ActionResult(True, cached)

        # Final fallback: search the web for the official site. Only
        # runs once nothing faster (app, saved website, cache, folder)
        # matched — see find_website() for the single place that talks
        # to a search provider.
        found = self.find_website(name)
        if found:
            if self.is_suspicious_url(found):
                # Never auto-open a first-time result that trips the
                # heuristic checks -- arm a confirmation instead, same
                # pattern as push_project(). Nothing is cached or opened
                # until the user explicitly says yes.
                self.pending_confirmation = {
                    "type": "open_url",
                    "name": name,
                    "url": found,
                    "expires": time.time() + self.CONFIRMATION_TIMEOUT_SECONDS,
                }
                if announce:
                    self.respond(
                        f"I found {name} at {found}, sir, but it looks unusual and "
                        f"I'm not fully confident it's safe. Say 'confirm open' to "
                        f"continue anyway, or 'cancel' to skip it."
                    )
                return ActionResult(True, "Awaiting open confirmation")
            self._remember_website(name, found)
            if announce:
                self.respond(f"Found {name}, sir. Opening it now.")
            self.open_url(found)
            return ActionResult(True, found)

        # Nothing found even after searching -- open a search results page
        # instead of dead-ending, so there's always something useful on
        # screen rather than just an apology.
        if announce:
            self.respond(f"I couldn't find an official site for {name}, sir. Let me pull up a search instead.")
        return self.search_web(name)

    def _remember_website(self, name, url):
        """Saves a newly-confirmed-safe discovered website so the next
        'open X' is instant (website_cache), and also mirrors it into
        the regular 'websites' config -- the same list the dashboard UI
        already displays -- so it shows up there automatically with no
        separate UI code needed."""
        self.config.setdefault("website_cache", {})[name] = url
        self.config.setdefault("websites", {})[name] = url
        self.save_config()


 
    def find_website(self, query):
        """The one place NaiTRO talks to a search provider to resolve
        'open <something>' when it's not an app, saved website, or
        already-cached lookup. Swapping providers later (DuckDuckGo ->
        Bing/Brave/etc.) only means changing this function."""
        query = self.normalize(query)
        if not query:
            return None
        try:
            from ddgs import DDGS
        except ImportError:
            self.log("Website finder unavailable: run 'pip install ddgs'.")
            return None
        try:
            results = DDGS().text(f"{query} official website", max_results=5)
        except Exception as error:
            self.log(f"Website finder search failed: {error}")
            return None
        skip_domains = ("google.", "bing.com", "duckduckgo.com", "search.yahoo.com", "wikipedia.org")
        for item in results or []:
            url = str((item or {}).get("href") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            if any(domain in url for domain in skip_domains):
                continue
            return url
        return None

    def search_web(self, query):
        """Explicit 'search for X' command — opens a normal search
        results page. Distinct from find_website(), which silently
        resolves a single 'open X' request to one official site."""
        title = self.config.get("conversation", {}).get("user_title", "sir")
        query = query.strip()
        if not query:
            self.respond(f"What would you like me to search for, {title}?")
            return ActionResult(False, "No query")
        url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
        self.respond(f"Searching for {query}, {title}.")
        self.open_url(url)
        return ActionResult(True, url)
    def launch(self, target, name=None):
        target = os.path.expandvars(os.path.expanduser(str(target)))

        if self.is_windows():
            entry = None
            if name:
                entry = self.config.get("apps", {}).get(name)
                if not isinstance(entry, dict):
                    entry = None
            try:
                ok, msg = launch_windows(target, entry=entry, log=self.log)
                return ActionResult(ok, msg)
            except Exception as e:
                self.log(f"Launch error: {e}")
                return ActionResult(False, str(e))

        # Linux / macOS
        try:
            if os.path.exists(target) or re.match(
                r"^[a-z]+://", target, re.IGNORECASE
            ):
                self.open_system_target(target)
            else:
                subprocess.Popen(
                    shlex.split(target), **self.quiet_subprocess_kwargs()
                )
            return ActionResult(True, target)
        except Exception as e:
            self.log(f"Launch error: {e}")
            return ActionResult(False, str(e))

    def close_app(self, name):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        name = self.normalize(name)
        process_map = self.process_name_map()
        # Browsers and apps that need graceful close (no /f flag)
        graceful = {"chrome.exe", "msedge.exe", "opera.exe", "firefox.exe"}
        processes = process_map.get(name, [f"{name.replace(' ', '')}.exe", f"{name}.exe"] if self.is_windows() else [name.replace(" ", ""), name])
        killed = False
        for proc in processes:
            try:
                if self.is_windows():
                    # Use graceful close for browsers, force kill for everything else
                    flags = [] if proc in graceful else ["/f"]
                    result = subprocess.run(
                        ["taskkill"] + flags + ["/im", proc],
                        capture_output=True, text=True, **self.quiet_subprocess_kwargs()
                    )
                else:
                    result = subprocess.run(["pkill", "-f", proc], capture_output=True, text=True)
                if result.returncode == 0:
                    killed = True
                    break
            except Exception:
                continue
        if killed:
            self.respond(random.choice([
                f"Closed {name}, {title}.",
                f"{name.title()} is shut down, {title}.",
                f"Done — {name} is closed, {title}.",
            ]))
            return ActionResult(True, f"Closed {name}")
        else:
            websites = self.config.get("websites", {})
            website_cache = self.config.get("website_cache", {})
            if name in websites or name in website_cache:
                self.respond(
                    f"I can't close a single browser tab, {title} — only the "
                    f"whole browser. Say 'close chrome' (or whichever browser "
                    f"you're using) if you'd like me to close all of it."
                )
                return ActionResult(False, f"Cannot close individual tab: {name}")
            self.respond(random.choice([
                f"Could not find {name} running, {title}.",
                f"{name.title()} does not appear to be open, {title}.",
            ]))
            return ActionResult(False, f"Not running: {name}")

    def list_windows(self):
        """Titles of every visible, non-empty top-level window, most
        recently active first. Windows-only (uses pywin32); returns an
        empty list everywhere else so callers never need an is_windows()
        check of their own."""
        if not self.is_windows():
            return []
        try:
            import win32gui
        except ImportError:
            self.log("Window control unavailable: run 'pip install pywin32'.")
            return []

        titles = []

        def _collect(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                text = win32gui.GetWindowText(hwnd)
                if text.strip():
                    titles.append((hwnd, text))

        win32gui.EnumWindows(_collect, None)
        return titles

    def _find_window(self, name):
        """Best-match visible window handle for a spoken/typed name
        fragment, e.g. 'chrome' matching 'PCBWay - Google Chrome'. Tries
        an exact case-insensitive substring match first, then falls back
        to a fuzzy match so small mishears still resolve."""
        name = self.normalize(name)
        windows = self.list_windows()
        if not windows:
            return None
        for hwnd, title in windows:
            if name in title.lower():
                return hwnd, title
        best = difflib.get_close_matches(name, [t.lower() for _, t in windows], n=1, cutoff=0.5)
        if best:
            for hwnd, title in windows:
                if title.lower() == best[0]:
                    return hwnd, title
        return None

    def control_window(self, action, name):
        """Handles focus/minimize/maximize/restore for extract_action_target's
        window_actions -- see NaitroEngine.extract_action_target. Distinct
        from close_app: this manages an existing window, it never ends
        the process."""
        title = self.config.get("conversation", {}).get("user_title", "sir")
        name = self.normalize(name)
        if not self.is_windows():
            self.respond(f"Window control is only available on Windows right now, {title}.")
            return ActionResult(False, "Windows only")
        try:
            import win32con
            import win32gui
        except ImportError:
            self.respond(f"I need pywin32 installed to control windows, {title}. Run: pip install pywin32")
            return ActionResult(False, "pywin32 missing")

        match = self._find_window(name)
        if not match:
            self.respond(f"I don't see a window open for {name}, {title}.")
            return ActionResult(False, f"No window found: {name}")
        hwnd, window_title = match

        try:
            if action == "focus":
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                self.respond(f"Switching to {window_title}, {title}.")
            elif action == "minimize":
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                self.respond(f"Minimized {window_title}, {title}.")
            elif action == "maximize":
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                self.respond(f"Maximized {window_title}, {title}.")
            elif action == "restore":
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                self.respond(f"Restored {window_title}, {title}.")
            else:
                return ActionResult(False, f"Unknown window action: {action}")
        except Exception as error:
            self.log(f"Window control error: {error}")
            self.respond(f"I couldn't do that to {window_title}, {title}.")
            return ActionResult(False, str(error))
        return ActionResult(True, f"{action} {window_title}")

    def process_name_map(self):
        if self.is_windows():
            return {
                "chrome": ["chrome.exe"], "google chrome": ["chrome.exe"],
                "opera gx": ["opera.exe"], "edge": ["msedge.exe"],
                "discord": ["discord.exe"], "obs": ["obs64.exe", "obs.exe"],
                "obs studio": ["obs64.exe", "obs.exe"], "steam": ["steam.exe"],
                "epic games": ["epicgameslauncher.exe"], "valorant": ["valorant.exe", "vanguard.exe"],
                "spotify": ["spotify.exe"], "zoom": ["zoom.exe"],
                "codex": ["codex.exe", "Codex.exe"], "openai codex": ["codex.exe", "Codex.exe"],
                "roblox": ["robloxplayerbeta.exe"], "pycharm": ["pycharm64.exe"],
                "notepad": ["notepad.exe"], "calculator": ["calculatorapp.exe", "calc.exe"],
                "task manager": ["taskmgr.exe"], "davinci resolve": ["resolve.exe"],
                "resolve": ["resolve.exe"], "medal": ["medal.exe"],
                "word": ["winword.exe"], "excel": ["excel.exe"],
                "powerpoint": ["powerpnt.exe"], "onenote": ["onenote.exe"],
                "vpn": ["privadovpn.exe"], "privado vpn": ["privadovpn.exe"],
                "nvidia app": ["nvclient.exe"], "rainmeter": ["rainmeter.exe"],
            }
        return {
            "chrome": ["chrome", "google-chrome", "google-chrome-stable"],
            "google chrome": ["chrome", "google-chrome", "google-chrome-stable"],
            "edge": ["microsoft-edge", "msedge"],
            "firefox": ["firefox"],
            "spotify": ["spotify"],
            "steam": ["steam"],
            "obs": ["obs", "obs-studio"],
            "obs studio": ["obs", "obs-studio"],
            "discord": ["discord"],
            "pycharm": ["pycharm", "pycharm.sh"],
            "codex": ["codex"],
            "openai codex": ["codex"],
        }

    def _resolve_mode(self, mode_name):
        """Resolve a mode name to its stored (key, entry).

        Mirrors the fuzzy matching NaiTRO understands in speech: exact key
        first, then equal-normalized keys ("Study Mode" → "study mode"),
        then a substring match on the stored key ("gaming" → "gaming mode").
        Shared by run_mode and chat() so both agree on what key is active.
        """
        modes = self.config.get("modes", {})
        if mode_name in modes:
            return mode_name, modes[mode_name]
        for key in modes:
            if self.normalize(key) == self.normalize(mode_name):
                return key, modes[key]
        stripped = mode_name.replace(" mode", "").strip()
        for key in modes:
            if stripped in self.normalize(key):
                return key, modes[key]
        return None, None

    def run_mode(self, mode_name):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        resolved, mode = self._resolve_mode(mode_name)
        if mode is None:
            self.respond(f"I don't have a routine called {mode_name}, {title}.")
            return ActionResult(False, "Mode not found")
        mode_name = resolved

        # Modes are stored either as a plain list of steps (legacy) or as
        # {"steps": [...], "style": "..."} so a mode can also carry an AI
        # personality. A personality-only mode has no steps and just retunes
        # how NaiTRO talks.
        steps = mode.get("steps") if isinstance(mode, dict) else mode
        style = mode.get("style") if isinstance(mode, dict) else None

        # Persist the active mode so the AI style applies to subsequent chat
        # and survives restarts.
        self.config["active_mode"] = mode_name
        self.save_config()

        self.respond(random.choice([
            f"Activating {mode_name}, {title}.",
            f"On it, {title}. Starting {mode_name}.",
            f"Right away, {title}.",
        ]))

        def _run():
            for step in steps or []:
                delay = step.get("delay", 0.5)
                time.sleep(delay)
                m_type = step.get("type")
                m_name = step.get("name", "")
                if m_type == "app":
                    app = self.config.get("apps", {}).get(m_name)
                    if app:
                        self.launch(app.get("target", m_name), name=m_name)
                    else:
                        # App not in config — try resolving live
                        match = self.find_app_entry(m_name)
                        if match:
                            key, entry = match
                            self.launch(
                                entry.get("target", m_name), name=key
                            )
                        else:
                            self.launch(m_name)
                elif m_type == "website":
                    url = step.get("url") or self.config.get("websites", {}).get(m_name)
                    if url:
                        self.open_url(url)
                elif m_type == "folder":
                    folder = self.config.get("folders", {}).get(m_name)
                    if folder:
                        self.launch(os.path.expandvars(folder))
                elif m_type == "playlist":
                    self.play_music(m_name, "playlist")

        threading.Thread(target=_run, daemon=True).start()
        return ActionResult(True, f"Started {mode_name}")

    def deactivate_mode(self):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        if not self.config.get("active_mode"):
            self.respond(f"No mode is active, {title}. Running baseline.")
            return ActionResult(False, "No active mode")
        self.config["active_mode"] = None
        self.save_config()
        self.respond(random.choice([
            f"Mode disengaged, {title}. Back to baseline.",
            f"Reverting to baseline, {title}.",
            f"Alright, {title}. Returning to standard operation.",
        ]))
        return ActionResult(True, "Mode deactivated")

    def chat(self, text):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        # An active mode with a "style" overrides the global conversation
        # personality — personality modes retune how NaiTRO talks.
        style = self.config.get("conversation", {}).get("style", "sharp, calm, witty")
        active = self.config.get("active_mode")
        if active:
            # Resolve fuzzy like run_mode — active_mode can be stored under a
            # slightly different key than the modes dict (case, "mode" suffix).
            _, mode = self._resolve_mode(active)
            if isinstance(mode, dict) and mode.get("style"):
                style = mode["style"]
        norm = self.normalize(text)
        now = datetime.now()
        hour = now.hour

        # Local time/date (no API needed)
        if "time" in norm and "what" in norm:
            suffix = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
            return self.respond(f"It is {now.strftime('%I:%M %p')}, {title}. Good {suffix}.")
        if ("date" in norm or "what day" in norm) and any(p in norm for p in ("what", "today", "is it")):
            return self.respond(f"Today is {now.strftime('%A, %B %d, %Y')}, {title}.")

        if any(p in norm for p in ("how are you", "you good", "you okay", "you alright")):
            return self.respond(random.choice([f"Running clean, {title}. No complaints.", f"Operational and mildly entertained, {title}.", f"Perfectly calibrated, {title}."]))
        # Whole-word match only: plain substring matching makes "something"
        # trigger the "hi" greeting.  \b boundaries keep "hey" from matching
        # inside e.g. "they" and "hi" inside "something".
        if re.search(r"\b(?:hello|hi|hey|wassup|sup|yo)\b", norm):
            return self.respond(random.choice([f"Hey {title}. What do you need?", f"Here and ready, {title}. What's the move?"]))
        if any(p in norm for p in ("thank you", "thanks", "good job", "cheers")):
            return self.respond(random.choice([f"Just doing my job, {title}.", f"Anytime, {title}.", f"Try not to make a habit of thanking the AI, {title}."]))
        if any(p in norm for p in ("good morning", "morning")):
            return self.respond(random.choice([f"Good morning, {title}.", f"Morning, {title}. What are we getting into?"]))
        if any(p in norm for p in ("good night", "night", "going to sleep")):
            return self.respond(random.choice([f"Rest well, {title}.", f"Goodnight, {title}."]))
        if any(p in norm for p in ("who are you", "what are you", "your name")):
            return self.respond(f"I am NaiTRO - your personal PC assistant, {title}.")
        if any(p in norm for p in ("what can you do", "help", "commands")):
            return self.respond(f"I can open apps, websites, folders, play music, and run your custom modes, {title}. Try 'open Codex', 'play music', or 'study mode'.")

        # Try OpenRouter API for everything else
        # Try Gemini API if key is set
        gemini_key = self.config.get("gemini_api_key", "").strip()
        if True:  # Always try AI
            def _ask_ai():
                from ai_client import AIClientError, query_ai as _query_ai
                system_prompt = (
                    f"You are NaiTRO, a sharp, witty, loyal personal AI assistant running on a Windows PC. "
                    f"Personality: {style}. Address the user as '{title}'. "
                    f"You have knowledge of gaming, tech, and current trends. "
                    f"Be conversational, confident, never sycophantic. "
                    f"Keep responses to 1-3 sentences unless more detail is genuinely needed. "
                    f"Answer only the user's latest message. Do not invent extra User questions. "
                    f"Do not write labels like User:, NaiTRO:, Assistant:, or transcript examples."
                )
                full_prompt = f"{system_prompt}\n\nUser: {text}\nNaiTRO:"
                try:
                    raw = _query_ai(
                        full_prompt,
                        config=self.config,
                        response_format="text",
                        timeout=30,
                        log=self.log,
                    )
                    reply = self.clean_ai_reply(raw)
                    self.respond(reply)
                    return
                except AIClientError as exc:
                    self.log(f"AI chat unavailable: {exc}")

                # Distinguish "no key configured yet" (a setup problem the
                # user can fix) from "key present but providers are down"
                # (a transient outage). On a fresh install with no key the
                # answer points them at Settings -> Neural Uplink instead
                # of a generic outage message.
                has_key = bool(
                    self.config.get("nvidia_api_key", "").strip()
                    or self.config.get("gemini_api_key", "").strip()
                )
                if not has_key:
                    self.respond(
                        f"I can't reach the AI yet, {title} — no API key is set. "
                        f"Open Settings, then Neural Uplink, and paste a free "
                        f"NVIDIA NIM or Gemini key to wake me up."
                    )
                else:
                    self.respond(random.choice([
                        f"Both AI services are unavailable right now, {title}. Try again in a moment.",
                        f"No AI connection at the moment, {title}. Give me a second.",
                    ]))

            threading.Thread(target=_ask_ai, daemon=True).start()
            return ActionResult(True, "chat")


        # Built-in replies
        if any(p in norm for p in ("how are you", "you good", "you okay", "you alright")):
            return self.respond(random.choice([f"Running clean, {title}. No complaints.", f"Operational and mildly entertained, {title}.", f"Perfectly calibrated, {title}."]))
        # Whole-word match only: plain substring matching makes "something"
        # trigger the "hi" greeting.  \b boundaries keep "hey" from matching
        # inside e.g. "they" and "hi" inside "something".
        if re.search(r"\b(?:hello|hi|hey|wassup|sup|yo)\b", norm):
            return self.respond(random.choice([f"Hey {title}. What do you need?", f"Here and ready, {title}. What's the move?"]))
        if any(p in norm for p in ("thank you", "thanks", "good job", "cheers")):
            return self.respond(random.choice([f"Just doing my job, {title}.", f"Anytime, {title}.", f"Try not to make a habit of thanking the AI, {title}."]))
        if any(p in norm for p in ("good morning", "morning")):
            return self.respond(random.choice([f"Good morning, {title}.", f"Morning, {title}. What are we getting into?"]))
        if any(p in norm for p in ("good night", "night", "going to sleep")):
            return self.respond(random.choice([f"Rest well, {title}.", f"Goodnight, {title}."]))
        if any(p in norm for p in ("who are you", "what are you", "your name")):
            return self.respond(f"I am NaiTRO — your personal PC assistant, {title}.")
        if any(p in norm for p in ("what can you do", "help", "commands")):
            return self.respond(f"I can open apps, websites, folders, and run your custom modes, {title}. Try 'open Discord', 'gaming mode', or 'search best GPU 2025'.")

        self.respond(random.choice([
            f"Did not quite catch that, {title}. Try 'open [app]', a mode name, or 'search [something]'.",
            f"Not sure what to do with that one, {title}. Give me an app, a mode, or a search.",
        ]))
        return ActionResult(True, "chat")

    def clean_ai_reply(self, reply):
        reply = str(reply or "").strip()
        for marker in ("\nUser:", "\nNaiTRO:", "\nAssistant:", "\nHuman:", "\nAI:"):
            if marker in reply:
                reply = reply.split(marker, 1)[0].strip()
        for prefix in ("NaiTRO:", "Assistant:", "AI:", "User:", "Human:"):
            if reply.startswith(prefix):
                reply = reply[len(prefix):].strip()
        return reply or "I am here, sir."

    def was_addressed_to_naitro(self, text):
        norm = self.repair_wake_mishear(self.normalize(text))
        wake = self.normalize(self.config.get("wake_phrase", "hey naitro"))
        # Exact match
        if wake in norm:
            return True
        # Fuzzy match — catches mishearings like "hay naitro", "hey javis", "hazardous naitro" etc
        words = norm.split()
        for i in range(len(words)):
            chunk = " ".join(words[i:i+2])
            if difflib.SequenceMatcher(None, chunk, wake).ratio() > 0.7:
                return True
        # Also catch just "naitro" alone
        if "naitro" in norm:
            return True
        return False

    def is_conversation_window_open(self, conversation_active, last_interaction_time, now=None):
        """Whether the 'skip the wake word for a bit' follow-up window is
        still open. This is the fix for NaiTRO reacting to background
        speech (e.g. singing) indefinitely: the window must expire based
        on conversation.session_timeout_seconds, and merely LOOKING like a
        command is not, by itself, enough to open or extend it — see
        NaitroUI.voice_loop, which is the only caller of this in practice."""
        if not conversation_active:
            return False
        now = time.time() if now is None else now
        timeout = float(self.config.get("conversation", {}).get("session_timeout_seconds", 600))
        return (now - last_interaction_time) <= timeout

    def extract_review_action(self, command):
        command = self.normalize(command)
        ordinal_map = {
            "first": 1, "one": 1, "1": 1,
            "second": 2, "two": 2, "2": 2,
            "third": 3, "three": 3, "3": 3,
            "fourth": 4, "four": 4, "4": 4,
            "fifth": 5, "five": 5, "5": 5,
        }

        if any(command.startswith(p) for p in ("review", "check code", "scan code", "inspect code")):
            target = command
            for prefix in ("review my changes", "review code", "review project", "review", "check code", "scan code", "inspect code"):
                if target.startswith(prefix):
                    target = target[len(prefix):].strip()
                    break
            return "review", target or None

        if re.match(r"^(open|show)\s+(.+\s+)?issue\b", command):
            return "open_issue", self.extract_issue_number(command, ordinal_map)

        if re.match(r"^(fix|apply)\s+(.+\s+)?(issue|fix)\b", command):
            return "fix_issue", self.extract_issue_number(command, ordinal_map)

        if command in ("push", "push code", "push to github", "push project") or command.startswith("push "):
            target = command
            for prefix in ("push to github", "push project", "push code", "push"):
                if target.startswith(prefix):
                    target = target[len(prefix):].strip()
                    break
            return "push", target or None

        return None

    def extract_issue_number(self, command, ordinal_map):
        for word, number in ordinal_map.items():
            if re.search(rf"\b{re.escape(word)}\b", command):
                return number
        match = re.search(r"\bissue\s+(\d+)\b|\bfix\s+(\d+)\b", command)
        if match:
            return int(next(group for group in match.groups() if group))
        return 1

    def resolve_project(self, target=None):
        projects = self.config.get("projects", {})
        reviewer = self.config.get("reviewer", {})
        key = self.normalize(target or "") or reviewer.get("default_project") or "naitro"
        if key in projects:
            raw_path = projects[key]
        elif target and Path(os.path.expandvars(os.path.expanduser(target))).exists():
            raw_path = target
            key = Path(raw_path).name
        else:
            raw_path = projects.get(reviewer.get("default_project", "naitro"), ".")
            key = reviewer.get("default_project", "naitro")
        path = Path(os.path.expandvars(os.path.expanduser(str(raw_path))))
        if not path.is_absolute():
            path = (APP_DIR / path).resolve()
        return key, path

    def run_git(self, project_path, args):
        return subprocess.run(
            ["git"] + list(args),
            cwd=str(project_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **self.quiet_subprocess_kwargs(),
        )

    def review_project(self, target=None):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        key, project_path = self.resolve_project(target)
        if not project_path.exists():
            self.respond(f"I cannot find the {key} project, {title}.")
            return ActionResult(False, "Project not found")

        try:
            from naitro_reviewer import changed_files_from_status, get_local_diff, query_ai_structured
        except Exception as error:
            self.respond(f"The reviewer module is not available, {title}.")
            self.log(f"Reviewer import error: {error}")
            return ActionResult(False, str(error))

        status_text, diff_text = get_local_diff(self.run_git, project_path)
        changed_files = changed_files_from_status(status_text)

        # Check for secret-shaped files that are already tracked by git,
        # regardless of whether there are any uncommitted changes right
        # now. A file merely being listed in .gitignore only stops FUTURE
        # commits — it does nothing for a file (like config.json, which
        # can hold the Gemini API key) that was already committed before
        # the ignore rule existed.
        tracked_secret_findings = self.check_tracked_secret_files(project_path)

        if not changed_files and not tracked_secret_findings:
            self.last_review = {"project": key, "path": str(project_path), "findings": []}
            self.respond(f"I reviewed {key}. No local changes found, {title}.")
            return ActionResult(True, "No changes")

        findings = []
        rule_findings = self.build_review_findings(project_path, status_text, diff_text)
        rule_findings.extend(tracked_secret_findings)
        if self.config.get("reviewer", {}).get("use_ai", True) and diff_text.strip():
            try:
                ai_issues = query_ai_structured(self.config, diff_text, changed_files, self.log)
                findings.extend(issue.to_display_dict() for issue in ai_issues)
            except Exception as error:
                self.log(f"AI review unavailable: {error}")
        if self.config.get("reviewer", {}).get("merge_rule_findings", True):
            seen = {(f.get("file"), f.get("line"), f.get("message", "")[:50]) for f in findings}
            for item in rule_findings:
                key_tuple = (item.get("file"), item.get("line"), item.get("message", "")[:50])
                if key_tuple not in seen:
                    findings.append(item)
                    seen.add(key_tuple)

        severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        findings.sort(key=lambda item: severity_order.get(str(item.get("severity", "LOW")).upper(), 2))
        self.last_review = {
            "project": key,
            "path": str(project_path),
            "findings": findings,
            "changed_files": changed_files,
            "status": status_text,
        }

        self.log(f"Review: {key} ({len(changed_files)} changed file(s))")
        if findings:
            for index, finding in enumerate(findings[:10], start=1):
                auto = " [auto-fix available]" if finding.get("auto_fix") else ""
                self.log(
                    f"{index}. {finding.get('severity', 'LOW')} {finding.get('file')}:{finding.get('line')} "
                    f"- {finding.get('message')}{auto}"
                )
                if finding.get("fix"):
                    self.log(f"   Fix: {finding.get('fix')}")
            self.respond(f"I found {len(findings)} thing{'s' if len(findings) != 1 else ''} in {key}, {title}. Say 'open first issue' or 'fix first issue'.")
        else:
            self.respond(f"I reviewed {key}. No obvious issues in the local changes, {title}.")
        return ActionResult(True, "Reviewed")

    def check_tracked_secret_files(self, project_path):
        """Flags files that are already tracked by git and commonly hold
        secrets (API keys, tokens, credentials), independent of the
        current diff. Being listed in .gitignore only prevents FUTURE
        commits of a file — it does not remove it if it was already
        committed, so this checks what git actually has tracked."""
        dangerous_names = {"config.json", ".env", "credentials.json", "secrets.json", "id_rsa"}
        dangerous_suffixes = (".pem", ".key")
        findings = []
        try:
            result = self.run_git(project_path, ["ls-files"])
        except Exception as error:
            self.log(f"Could not check tracked files: {error}")
            return findings
        for line in result.stdout.splitlines():
            rel = line.strip().replace("\\", "/")
            if not rel:
                continue
            name = rel.rsplit("/", 1)[-1].lower()
            if name in dangerous_names or name.endswith(dangerous_suffixes):
                findings.append({
                    "file": rel,
                    "line": 1,
                    "severity": "HIGH",
                    "message": (
                        f"{rel} is tracked by git and commonly holds secrets (API keys, tokens). "
                        f"Adding it to .gitignore does not remove it from history if it was already committed."
                    ),
                    "fix": (
                        f"Run 'git rm --cached {rel}', confirm it's in .gitignore, commit that removal, "
                        f"and rotate any keys inside it since they may already be in your git history."
                    ),
                })
        return findings

    def build_review_findings(self, project_path, status_text, diff_text):
        findings = []
        changed = {}
        current_file = None
        current_line = 0
        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                current_file = line[6:].strip()
                changed.setdefault(current_file, [])
            elif line.startswith("@@"):
                match = re.search(r"\+(\d+)", line)
                current_line = int(match.group(1)) - 1 if match else 0
            elif current_file and line.startswith("+") and not line.startswith("+++"):
                current_line += 1
                changed[current_file].append((current_line, line[1:]))
            elif current_file and not line.startswith("-"):
                current_line += 1

        for line in status_text.splitlines():
            if not line.strip():
                continue
            rel = line[3:].strip().replace("\\", "/")
            if " -> " in rel:
                rel = rel.split(" -> ", 1)[1].strip()
            root = rel.split("/", 1)[0]
            if root in {"build", "dist", "voice_samples", "__pycache__"} or rel.endswith((".pyc", ".pyo", ".log")):
                pattern = f"{root}/" if "/" in rel else rel
                if root in {"build", "dist", "voice_samples", "__pycache__"}:
                    pattern = f"{root}/"
                findings.append({
                    "file": rel,
                    "line": 1,
                    "severity": "LOW",
                    "message": "Generated or local artifact is showing up in git changes.",
                    "fix": f"Add {pattern} to .gitignore instead of committing local artifacts.",
                    "auto_fix": "gitignore",
                    "ignore_pattern": pattern,
                })

        secret_re = re.compile(r"(api[_-]?key|token|secret|password)\s*[:=]\s*['\"][^'\"]{8,}", re.IGNORECASE)
        for file_path, additions in changed.items():
            for line_number, added in additions:
                lower = added.lower()
                if secret_re.search(added):
                    findings.append({
                        "file": file_path,
                        "line": line_number,
                        "severity": "HIGH",
                        "message": "Possible secret or API key added to source control.",
                        "fix": "Move the secret into config.json or an environment variable, then rotate it if it was real.",
                    })
                if re.search(r"(#|//|/\*)\s*(todo|fixme)\b", lower) or re.search(r"\b(todo|fixme):", lower):
                    findings.append({
                        "file": file_path,
                        "line": line_number,
                        "severity": "LOW",
                        "message": "New task marker added in changed code.",
                        "fix": "Resolve it now or create a tracked issue before pushing.",
                    })
                if re.search(r"except\s+exception\s*:\s*$", lower):
                    findings.append({
                        "file": file_path,
                        "line": line_number,
                        "severity": "MEDIUM",
                        "message": "Broad exception handler can hide real failures.",
                        "fix": "Catch a narrower exception or log the exception details.",
                    })
        return findings

    def open_review_issue(self, number=1):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        findings = (self.last_review or {}).get("findings", [])
        if not findings:
            self.respond(f"I do not have review findings open yet, {title}. Say 'review code' first.")
            return ActionResult(False, "No review")
        index = max(1, int(number or 1)) - 1
        if index >= len(findings):
            self.respond(f"There are only {len(findings)} issue(s), {title}.")
            return ActionResult(False, "Issue out of range")
        finding = findings[index]
        project_path = Path(self.last_review.get("path", APP_DIR))
        self.open_file_in_editor(project_path / finding.get("file", ""), int(finding.get("line") or 1))
        self.respond(f"Opened issue {index + 1}, {title}. {finding.get('fix', 'Review the highlighted code before pushing.')}")
        return ActionResult(True, "Opened issue")

    def apply_review_fix(self, number=1):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        findings = (self.last_review or {}).get("findings", [])
        if not findings:
            self.respond(f"I need to review the project first, {title}. Say 'review code'.")
            return ActionResult(False, "No review")
        index = max(1, int(number or 1)) - 1
        if index >= len(findings):
            self.respond(f"There are only {len(findings)} issue(s), {title}.")
            return ActionResult(False, "Issue out of range")
        finding = findings[index]
        project_path = Path(self.last_review.get("path", APP_DIR))
        if finding.get("auto_fix") == "gitignore":
            pattern = finding.get("ignore_pattern")
            if not pattern:
                return self.open_review_issue(index + 1)
            gitignore = project_path / ".gitignore"
            existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
            lines = [line.strip() for line in existing.splitlines()]
            if pattern not in lines:
                ending = "" if existing.endswith("\n") or not existing else "\n"
                gitignore.write_text(f"{existing}{ending}{pattern}\n", encoding="utf-8")
                self.log(f"Applied fix: added {pattern} to .gitignore")
            else:
                self.log(f"Fix already present: {pattern} is in .gitignore")
            self.respond(f"I applied the safe fix for issue {index + 1}, {title}. Run review again to verify.")
            return ActionResult(True, "Applied fix")

        self.open_review_issue(index + 1)
        self.respond(f"That issue needs human approval, {title}. I opened it and gave you the suggested fix.")
        return ActionResult(False, "Manual fix required")

    def open_file_in_editor(self, path, line=1):
        path = Path(path)
        reviewer = self.config.get("reviewer", {})
        editor = self.normalize(reviewer.get("editor", "pycharm"))
        pycharm = reviewer.get("pycharm_exe") or self.find_pycharm_exe()
        try:
            if editor == "pycharm" and pycharm:
                subprocess.Popen([pycharm, "--line", str(line), str(path)], **self.quiet_subprocess_kwargs())
                return
            if editor in {"code", "vscode"} and shutil.which("code"):
                subprocess.Popen(["code", "-g", f"{path}:{line}"], **self.quiet_subprocess_kwargs())
                return
            self.open_system_target(path)
        except Exception as error:
            self.log(f"Could not open editor: {error}")

    def find_pycharm_exe(self):
        for name in ("pycharm64.exe", "pycharm.exe", "pycharm", "pycharm.sh"):
            found = shutil.which(name)
            if found:
                return found
        if self.is_windows():
            roots = [
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
                Path(os.environ.get("PROGRAMFILES", "")) / "JetBrains",
                Path(os.environ.get("PROGRAMFILES(X86)", "")) / "JetBrains",
            ]
            for root in roots:
                if root.exists():
                    matches = list(root.glob("**/pycharm64.exe"))
                    if matches:
                        return str(matches[0])
        return None

    CONFIRMATION_TIMEOUT_SECONDS = 30

    def push_project(self, target=None):
        """Voice/text entry point for 'push to github'. Does NOT push
        immediately — a single misheard phrase should never be able to
        push code. Instead this validates the request, then arms a
        pending confirmation that must be explicitly confirmed (see
        handle_pending_confirmation) before any git command runs."""
        title = self.config.get("conversation", {}).get("user_title", "sir")
        if not self.config.get("reviewer", {}).get("allow_push", False):
            self.respond(f"Push is disabled in config, {title}.")
            return ActionResult(False, "Push disabled")
        key, project_path = self.resolve_project(target)
        status = self.run_git(project_path, ["status", "--porcelain"]).stdout.strip()
        if status:
            self.respond(f"I will not push {key} while local changes are uncommitted, {title}. Commit or stash them first.")
            return ActionResult(False, "Dirty tree")

        self.pending_confirmation = {
            "type": "push",
            "key": key,
            "project_path": project_path,
            "expires": time.time() + self.CONFIRMATION_TIMEOUT_SECONDS,
        }
        self.respond(
            f"Ready to push {key} to GitHub, {title}. Say 'confirm push' to go a, "
            f"or 'cancel' to stop."
        )
        return ActionResult(True, "Awaiting push confirmation")

    def handle_pending_confirmation(self, command):
        """Checks a normalized command against any pending confirmation
        (currently only git push). Returns an ActionResult if it consumed
        the command, or None if there was nothing pending / it wasn't a
        confirm/cancel reply, so normal command parsing should continue."""
        pending = self.pending_confirmation
        if not pending:
            return None

        title = self.config.get("conversation", {}).get("user_title", "sir")
        if time.time() > pending.get("expires", 0):
            self.pending_confirmation = None
            return None  # expired silently; treat this as a fresh command

        confirm_phrases = {"confirm push", "confirm", "yes", "yes push", "push confirm", "confirmed", "do it", "confirm open", "open confirm"}
        cancel_phrases = {"cancel push", "cancel", "no", "never mind", "nevermind", "stop", "abort"}

        if command in confirm_phrases:
            self.pending_confirmation = None
            if pending["type"] == "push":
                return self._execute_push(pending["key"], pending["project_path"])
            if pending["type"] == "open_url":
                name, url = pending["name"], pending["url"]
                self._remember_website(name, url)
                self.respond(f"Opening {name} now, {title}.")
                self.open_url(url)
                return ActionResult(True, url)

        if command in cancel_phrases:
            self.pending_confirmation = None
            if pending["type"] == "open_url":
                self.respond(f"Skipped it, {title}. That site was not opened or saved.")
                return ActionResult(True, "Open cancelled")
            self.respond(f"Cancelled, {title}. Nothing was pushed.")
            return ActionResult(True, "Push cancelled")

        # Anything else: leave the confirmation pending (still within its
        # timeout window) and let the command parse normally, so an
        # unrelated command right after a push request doesn't get
        # silently swallowed.
        return None

    def _execute_push(self, key, project_path):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        result = self.run_git(project_path, ["push"])
        if result.returncode == 0:
            self.respond(f"{key} is pushed to GitHub, {title}.")
            return ActionResult(True, "Pushed")
        self.log(result.stderr or result.stdout)
        self.respond(f"Git push failed for {key}, {title}. I logged the details.")
        return ActionResult(False, "Push failed")

    # ------------------------------------------------------------------ browser agent

    def _get_browser_agent(self):
        if self._browser_agent is None:
            try:
                from browser_agent import BrowserAgent
                self._browser_agent = BrowserAgent(
                    config=self.config, log=self.log
                )
            except Exception as exc:
                self.log(f"Browser agent unavailable: {exc}")
                return None
        return self._browser_agent

    def close_browser(self):
        if self._browser_agent is not None:
            self._browser_agent.close_browser()
            self._browser_agent = None

    def _handle_browser_command(self, command):
        """Detect and handle browser-agent commands.  Returns an
        :class:`ActionResult` if the command was consumed, or ``None``
        so normal parsing continues."""
        text = (command or "").strip()
        norm = self.normalize(text)
        title = self.config.get("conversation", {}).get("user_title", "sir")

        # "close browser" / "stop browser" / "kill browser"
        if any(p in norm for p in ("close browser", "stop browser", "kill browser")):
            self.close_browser()
            self.respond(f"Browser closed, {title}.")
            return ActionResult(True, "Browser closed")

        # Bare "browser" / "open browser" — start the browser
        if norm in ("browser", "open browser", "start browser", "launch browser", "start browsing"):
            agent = self._get_browser_agent()
            if agent is None:
                self.respond(f"Browser agent not available, {title}. Check that Playwright is installed.")
                return ActionResult(False, "Browser agent unavailable")
            result = agent.start_browser()
            self.respond(result.get("message", "Browser started") + f", {title}.")
            return ActionResult(True, "Browser started")

        # "browser tabs" / "list tabs" — needs agent but no Playwright
        if any(p in norm for p in ("browser tabs", "list tabs", "show tabs")):
            agent = self._get_browser_agent()
            if agent is None:
                self.respond(f"Browser agent not available, {title}.")
                return ActionResult(False, "Browser agent unavailable")
            tabs = agent.tabs()
            if not tabs:
                self.respond(f"No open tabs, {title}.")
            else:
                lines = [f"Tab {i+1}: {t.get('title') or t.get('url') or 'untitled'}" for i, t in enumerate(tabs[:5])]
                self.respond("Open tabs: " + "; ".join(lines))
            return ActionResult(True, "Browser tabs")

        # Strip "browser" prefix for agent commands
        is_browser_prefix = False
        agent_prefixes = ("browser ", "browse ", "automate ")
        for prefix in agent_prefixes:
            if norm.startswith(prefix):
                text = text[len(prefix):].strip()
                is_browser_prefix = True
                break

        if not is_browser_prefix:
            return None

        if not text:
            # bare "browser" or "browse" with no sub-command: start browser
            agent = self._get_browser_agent()
            if agent is None:
                self.respond(f"Browser agent not available, {title}. Check that Playwright is installed.")
                return ActionResult(False, "Browser agent unavailable")
            result = agent.start_browser()
            self.respond(result.get("message", "Browser started") + f", {title}.")
            return ActionResult(True, "Browser started")

        # Route to the agent
        agent = self._get_browser_agent()
        if agent is None:
            self.respond(f"Browser agent not available, {title}. Check that Playwright is installed.")
            return ActionResult(False, "Browser agent unavailable")

        def _run():
            result = agent.run(text)
            if result.get("confirmation_required"):
                action = result.get("pending_action") or {}
                self.respond(
                    f"Browser wants to {action.get('type', '?')} {action.get('target', '')} — "
                    f"say 'confirm' or 'cancel'."
                )
            elif result.get("ok"):
                msg = result.get("message", "Done")
                self.respond(f"Browser: {msg}")
            else:
                msg = result.get("message", "Could not complete that")
                self.respond(f"Browser: {msg}")

        threading.Thread(target=_run, daemon=True).start()
        return ActionResult(True, "browser command")

class NaitroUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("NaiTRO Control Panel")
        try:
            if getattr(sys, 'frozen', False):
                # If running as EXE, look in the temp folder
                icon_path = os.path.join(sys._MEIPASS, "NaiTRO.ico")
            else:
                # If running as .py, look in the current folder
                icon_path = "NaiTRO.ico"

            diagnostics.lookup("icon", "Tk window icon", icon_path)
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as exc:
            diagnostics.exception("Tk window icon lookup", exc)
        self.root.geometry("1100x750")
        self.root.configure(bg="#0a0a0a")
        
        self.colors = {
            "bg": "#0a0a0a",
            "panel": "#121018",
            "panel_2": "#1b1426",
            "accent": "#a855f7",
            "accent_2": "#7c3aed",
            "accent_dim": "#4c1d95",
            "text": "#f5f3ff",
            "muted": "#a7a0b8",
            "border": "#2b2140",
            "line": "#2b2140",
            "dark": "#1e1b4b",
        }
        
        self.events = queue.Queue()
        self.engine = NaitroEngine(log=self.enqueue_log)
        self.voice_running = False
        self.orb_angle = 0
        self.orb_scale = 1.0
        self.orb_target_scale = 1.0
        self.sidebar_visible = False
        self.list_kind = StringVar(value="modes")
        self.conversation_active = False
        self.last_interaction_time = 0
        
        self.status_text = StringVar(value="SYSTEMS ONLINE")
        self.command_text = StringVar()
        
        self.setup_styles()
        self.build_ui()
        self.animate()
        self.root.after(100, self.flush_events)
        self.root.after(500, self.setup_tray)

        # No startup greeting: NaiTRO stays silent on launch and starts
        # listening immediately so the first command can be spoken right
        # away. A short "welcome back" line is spoken once, right before
        # the first recognized command runs -- see
        # NaitroEngine.greet_first_command(), called from voice_loop().
        if self.engine.config.get("voice", {}).get("auto_start", True):
            self.root.after(0, self.start_voice)

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.colors["bg"])
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["text"])
        style.configure("TButton", background=self.colors["panel"], foreground=self.colors["text"], borderwidth=0, padding=(10, 6))
        style.map("TButton", background=[("active", self.colors["accent_2"])])
        style.configure("Primary.TButton", background=self.colors["accent"], foreground="#ffffff", borderwidth=0, padding=(10, 6))
        style.map("Primary.TButton", background=[("active", self.colors["accent_2"])])
        style.configure("Sidebar.TFrame", background=self.colors["panel"])
        style.configure("Tab.TButton", padding=(8, 4), font=("Consolas", 9))

    def build_ui(self):
        self.app_container = Frame(self.root, bg=self.colors["bg"])
        self.app_container.pack(fill=BOTH, expand=True)
        
        self.sidebar = Frame(self.app_container, bg=self.colors["panel"], width=350, padx=20, pady=20)
        self.sidebar.pack_propagate(False)
        
        Label(self.sidebar, text="NaiTRO", font=("Consolas", 18, "bold"), fg=self.colors["accent"], bg=self.colors["panel"]).pack(anchor="w")
        Label(self.sidebar, text="Control center", font=("Consolas", 9), fg=self.colors["muted"], bg=self.colors["panel"]).pack(anchor="w", pady=(2, 18))
        
        tab_row = Frame(self.sidebar, bg=self.colors["panel"])
        tab_row.pack(fill="x", pady=(0, 10))
        for kind in ("apps", "websites", "playlists", "folders", "modes"):
            btn = ttk.Button(tab_row, text=kind.title(), style="Tab.TButton", command=lambda k=kind: self._switch_tab(k))
            btn.pack(side=LEFT, padx=(0, 4))

        self.section_title = Label(
            self.sidebar,
            text="Your Modes",
            font=("Consolas", 11, "bold"),
            fg=self.colors["text"],
            bg=self.colors["panel"]
        )
        self.section_title.pack(anchor="w", pady=(4, 0))
        self.section_hint = Label(
            self.sidebar,
            text="Saved routines you can run or edit.",
            font=("Consolas", 8),
            fg=self.colors["muted"],
            bg=self.colors["panel"]
        )
        self.section_hint.pack(anchor="w", pady=(2, 6))
            
        self.items_list = Listbox(
            self.sidebar,
            bg=self.colors["bg"],
            fg=self.colors["text"],
            font=("Consolas", 10),
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.colors["border"],
            selectbackground=self.colors["accent"]
        )
        self.items_list.pack(fill=BOTH, expand=True, pady=10)
        self.items = self.items_list  # alias for ModeBuilder/ItemEditor compatibility

        # Action buttons
        action_row = Frame(self.sidebar, bg=self.colors["panel"])
        action_row.pack(fill="x", pady=(0, 6))
        ttk.Button(action_row, text="Run", style="Primary.TButton", command=self.run_selected).pack(side=LEFT)
        ttk.Button(action_row, text="Edit", command=self.edit_item).pack(side=LEFT, padx=(6, 0))
        ttk.Button(action_row, text="Delete", command=self.delete_item).pack(side=LEFT, padx=(6, 0))

        add_row = Frame(self.sidebar, bg=self.colors["panel"])
        add_row.pack(fill="x", pady=(0, 10))
        ttk.Button(add_row, text="+ Add", command=self._add_for_tab).pack(side=LEFT)
        self.new_mode_btn = ttk.Button(add_row, text="+ New Mode", style="Primary.TButton", command=self.create_mode)
        self.new_mode_btn.pack(side=LEFT, padx=(6, 0))

        self.refresh_lists()
        
        self.main_panel = Frame(self.app_container, bg=self.colors["bg"], padx=30, pady=20)
        self.main_panel.pack(side=RIGHT, fill=BOTH, expand=True)
        
        er = Frame(self.main_panel, bg=self.colors["bg"])
        er.pack(fill="x")
        ttk.Button(er, text="Menu", width=8, command=self.toggle_sidebar).pack(side=LEFT)
        Label(er, textvariable=self.status_text, font=("Consolas", 10), fg=self.colors["muted"], bg=self.colors["bg"]).pack(side=LEFT, padx=15)
        ttk.Button(er, text="Shut Down", command=self.shutdown).pack(side=RIGHT)

        # X button minimizes to background, no confirm dialog
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_background)

        self.home_modes = Frame(self.main_panel, bg=self.colors["panel"], padx=16, pady=12)
        self.home_modes.pack(fill="x", pady=(18, 0))
        mode_ = Frame(self.home_modes, bg=self.colors["panel"])
        mode_.pack(fill="x")
        Label(
            mode_,
            text="Your Modes",
            font=("Consolas", 12, "bold"),
            fg=self.colors["text"],
            bg=self.colors["panel"],
        ).pack(side=LEFT)
        ttk.Button(mode_, text="+ New Mode", style="Primary.TButton", command=self.create_mode).pack(side=RIGHT)
        ttk.Button(mode_, text="View Modes", command=self.open_modes_sidebar).pack(side=RIGHT, padx=(0, 8))
        self.home_modes_row = Frame(self.home_modes, bg=self.colors["panel"])
        self.home_modes_row.pack(fill="x", pady=(10, 0))
        self.refresh_home_modes()
        
        center_frame = Frame(self.main_panel, bg=self.colors["bg"])
        center_frame.pack(fill=BOTH, expand=True)
        
        self.canvas = Canvas(center_frame, width=400, height=400, bg=self.colors["bg"], highlightthickness=0)
        self.canvas.pack(expand=True)
        
        self.output = Text(self.main_panel, height=8, bg=self.colors["panel"], fg=self.colors["text"], 
                          font=("Consolas", 11), relief="flat", padx=20, pady=20,
                          highlightthickness=1, highlightbackground=self.colors["border"])
        self.output.pack(fill="x", pady=20)
        self.output.configure(state="disabled")
        
        input_frame = Frame(self.main_panel, bg=self.colors["bg"])
        input_frame.pack(fill="x")
        
        self.entry = Entry(input_frame, textvariable=self.command_text, bg=self.colors["panel"], 
                          fg=self.colors["text"], font=("Consolas", 14), relief="flat",
                          insertbackground=self.colors["accent"], highlightthickness=1, 
                          highlightbackground=self.colors["border"])
        self.entry.pack(side=LEFT, fill="x", expand=True, ipady=10, padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self.send_command())
        
        btn = Button(input_frame, text="SEND", command=self.send_command, bg=self.colors["accent"], 
                     fg="white", font=("Orbitron", 10, "bold"), relief="flat", padx=20)
        btn.pack(side=RIGHT, ipady=8)

    def _switch_tab(self, kind):
        self.list_kind.set(kind)
        labels = {
            "apps": ("Apps", "Launchable app shortcuts."),
            "websites": ("Websites", "Saved links NaiTRO can open."),
            "playlists": ("Playlists", "Spotify playlists NaiTRO can play."),
            "folders": ("Folders", "Saved folders on this PC."),
            "modes": ("Your Modes", "Saved routines you can run or edit."),
        }
        if hasattr(self, "section_title"):
            title, hint = labels.get(kind, (kind.title(), ""))
            self.section_title.configure(text=title)
            self.section_hint.configure(text=hint)
        if hasattr(self, "new_mode_btn"):
            if not self.new_mode_btn.winfo_ismapped():
                self.new_mode_btn.pack(side=LEFT, padx=(6, 0))
        self.refresh_lists()

    def open_modes_sidebar(self):
        self._switch_tab("modes")
        if not self.sidebar_visible:
            self.toggle_sidebar()

    def _add_for_tab(self):
        kind = self.list_kind.get()
        if kind == "modes":
            self.create_mode()
        else:
            self.add_item()

    def select_kind(self, kind):
        self._switch_tab(kind)

    def refresh_lists(self):
        self.items_list.delete(0, END)
        kind = self.list_kind.get()
        data = self.engine.config.get(kind, {})
        for name in sorted(data.keys()):
            self.items_list.insert(END, name)
        self.refresh_home_modes()

    def refresh_home_modes(self):
        if not hasattr(self, "home_modes_row"):
            return
        for child in self.home_modes_row.winfo_children():
            child.destroy()
        modes = sorted(self.engine.config.get("modes", {}).keys())
        if not modes:
            Label(
                self.home_modes_row,
                text="No modes yet.",
                font=("Consolas", 10),
                fg=self.colors["muted"],
                bg=self.colors["panel"],
            ).pack(side=LEFT)
            return
        for name in modes[:7]:
            ttk.Button(
                self.home_modes_row,
                text=name.title(),
                command=lambda mode=name: self.engine.run_mode(mode),
            ).pack(side=LEFT, padx=(0, 8), pady=(0, 2))

    def setup_tray(self):
        def _tray():
            try:
                import pystray
                from PIL import Image, ImageDraw
                img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
                d = ImageDraw.Draw(img)
                d.ellipse([4, 4, 60, 60], fill="#a855f7")
                d.ellipse([16, 16, 48, 48], fill="#1e1b4b")
                d.ellipse([24, 24, 40, 40], fill="#a855f7")
                menu = pystray.Menu(
                    pystray.MenuItem("Show NaiTRO", lambda: self.root.after(0, self._show_window), default=True),
                    pystray.MenuItem("Shut Down", lambda: self.root.after(0, self.shutdown)),
                )
                self.tray_icon = pystray.Icon("NaiTRO", img, "NaiTRO", menu)
                self.tray_icon.run()
            except Exception as e:
                print(f"Tray not available: {e}")
        threading.Thread(target=_tray, daemon=True).start()

    def _show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def minimize_to_background(self):
        self.root.withdraw()

    def shutdown(self):
        self.voice_running = False
        try:
            if hasattr(self, 'tray_icon'):
                self.tray_icon.stop()
        except Exception:
            pass
        self.root.destroy()

    def toggle_sidebar(self):
        if self.sidebar_visible:
            self.sidebar.pack_forget()
            self.sidebar_visible = False
        else:
            self.sidebar.pack(side=LEFT, fill="y", before=self.main_panel)
            self.sidebar_visible = True

    def start_voice(self):
        if self.voice_running: return
        self.voice_running = True
        threading.Thread(target=self.voice_loop, daemon=True).start()

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

        self.enqueue_log(f"Heard options: {', '.join(alternatives[:3])}")
        for candidate in alternatives:
            if self.engine.was_addressed_to_naitro(candidate) or self.is_actionable_voice_command(candidate):
                return self.engine.repair_wake_mishear(candidate)
        return self.engine.repair_wake_mishear(alternatives[0])

    def voice_loop(self):
        try:
            import speech_recognition as sr
        except ImportError:
            self.enqueue_log("SpeechRecognition not installed.")
            self.voice_running = False
            return

        recognizer = sr.Recognizer()
        mic_index = self.engine.config.get("voice", {}).get("microphone_index")
        voice = self.engine.config.get("voice", {})
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
                            self.enqueue_log("Ignored voice while NaiTRO was speaking.")
                            continue
                        text = self.recognize_best_text(recognizer, audio, sr)
                        if not text:
                            continue
                        self.enqueue_log(f"Heard: {text}")

                        addressed = self.engine.was_addressed_to_naitro(text)

                        # A follow-up "conversation window" lets you skip the
                        # wake word for a little while after NaiTRO was last
                        # addressed. It must expire — otherwise, once opened
                        # (e.g. right after "hey naitro"), NaiTRO keeps
                        # treating *everything* it hears as a command
                        # forever, including song lyrics, other people
                        # talking, or the TV.
                        window_open = self.engine.is_conversation_window_open(
                            self.conversation_active, self.last_interaction_time
                        )
                        if self.conversation_active and not window_open:
                            self.conversation_active = False
                            self.enqueue_log("Conversation window timed out — say the wake word again.")

                        # Only react if NaiTRO was directly addressed, or
                        # we're inside an already-open follow-up window.
                        # Note: a phrase merely *looking* like a command
                        # (e.g. "play" or "stop" appearing in a song lyric)
                        # is intentionally NOT enough on its own anymore —
                        # that used to make NaiTRO jump on background
                        # speech/singing even when nobody was talking to it.
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
                                self.root.after(3500, self.shutdown)
                            elif self.is_show_request(text):
                                self.root.after(0, lambda: (self.root.deiconify(), self.root.lift(), self.root.focus_force()))
                            else:
                                self.root.after(0, lambda t=text: self.engine.run_command(t))
                            
                    except sr.WaitTimeoutError: continue
                    except sr.UnknownValueError: continue
                    except Exception as e:
                        self.enqueue_log(f"Voice error: {e}")
        except Exception as e:
            self.enqueue_log(f"Mic error: {e}")
            self.voice_running = False

    def animate(self):
        self.canvas.delete("all")
        cx, cy = 200, 200
        
        if self.engine._is_speaking:
            self.orb_target_scale = 1.3 + 0.2 * math.sin(time.time() * 10)
        elif self.voice_running:
            self.orb_target_scale = 1.1 + 0.1 * math.sin(time.time() * 5)
        else:
            self.orb_target_scale = 1.0
            
        self.orb_scale += (self.orb_target_scale - self.orb_scale) * 0.1
        self.orb_angle += 0.05
        
        for i in range(3):
            r = (80 + i * 20) * self.orb_scale
            offset = i * 0.5
            self.draw_ring(cx, cy, r, self.orb_angle + offset, self.colors["accent"])
            
        core_r = 50 * self.orb_scale
        self.canvas.create_oval(cx-core_r, cy-core_r, cx+core_r, cy+core_r, 
                               fill=self.colors["bg"], outline=self.colors["accent"], width=2)
        
        glow_r = 30 * self.orb_scale
        self.canvas.create_oval(cx-glow_r, cy-glow_r, cx+glow_r, cy+glow_r, 
                               fill=self.colors["accent_dim"], outline="")

        self.root.after(16, self.animate)

    def draw_ring(self, cx, cy, r, angle, color):
        points = []
        for i in range(0, 361, 10):
            a = math.radians(i)
            wave = 5 * math.sin(a * 4 + angle * 2)
            x = cx + (r + wave) * math.cos(a)
            y = cy + (r + wave) * math.sin(a)
            points.extend([x, y])
        self.canvas.create_line(points, fill=color, smooth=True, width=1)

    def enqueue_log(self, text):
        self.events.put(text)

    def flush_events(self):
        while not self.events.empty():
            self.log(self.events.get())
        self.root.after(100, self.flush_events)

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert(END, f"{text}\n")
        self.output.see(END)
        self.output.configure(state="disabled")

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
            "shut down naitro", "shutdown naitro", "exit naitro", "quit naitro",
            "close naitro", "power off naitro", "turn off naitro",
            "goodbye naitro", "bye naitro",
        }
        return norm in shutdown_phrases or command in shutdown_commands

    def is_show_request(self, text):
        norm = self.engine.normalize(text)
        command = self.engine.strip_wake_phrase(norm)
        show_phrases = {
            "show naitro", "open naitro", "bring up naitro", "show yourself",
            "come back", "naitro show", "naitro open", "wake up naitro",
        }
        show_commands = {
            "show yourself", "show", "come back", "wake up",
        }
        return norm in show_phrases or command in show_commands

    def send_command(self):
        cmd = self.command_text.get().strip()
        if not cmd:
            return
        self.command_text.set("")
        if self.is_shutdown_request(cmd):
            self.engine.respond(f"Shutting down. Goodbye, sir.")
            self.root.after(3500, self.shutdown)
            return
        if self.is_show_request(cmd):
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            return
        self.engine.run_command(cmd)

    def selected_name(self):
        sel = self.items_list.curselection()
        return self.items_list.get(sel[0]) if sel else None

    def create_mode(self):
        ModeBuilder(self)

    def run_selected(self):
        name = self.selected_name()
        if not name:
            return
        kind = self.list_kind.get()
        if kind == "modes":
            self.engine.run_mode(name)
        else:
            self.engine.open_target(name)

    def add_item(self):
        ItemEditor(self, self.list_kind.get())

    def edit_item(self):
        name = self.selected_name()
        if name:
            ItemEditor(self, self.list_kind.get(), name)

    def delete_item(self):
        name = self.selected_name()
        if not name:
            return
        kind = self.list_kind.get()
        if messagebox.askyesno("Delete", f"Remove {name} from {kind}?"):
            self.engine.config.get(kind, {}).pop(name, None)
            self.engine.save_config()
            self.refresh_lists()

    def open_config(self):
        try:
            self.engine.open_system_target(CONFIG_PATH)
        except Exception:
            editor = "notepad.exe" if self.engine.is_windows() else os.environ.get("EDITOR", "nano")
            subprocess.Popen([editor, str(CONFIG_PATH)], **self.engine.quiet_subprocess_kwargs())

    def reload_config(self):
        self.engine.refresh()
        self.refresh_lists()
        self.status_text.set("Configuration reloaded.")

    def run(self):
        self.root.mainloop()


class ModeBuilder:
    def __init__(self, ui):
        self.ui = ui
        self.window = Toplevel(ui.root)
        self.window.title("Create New Mode")
        self.window.geometry("760x520")
        self.window.configure(bg=ui.colors["bg"])
        self.window.grab_set()
        self.mode_name = StringVar()
        self.source_kind = StringVar(value="apps")
        self.steps = []
        self.build()
        self.refresh_source()

    def build(self):
        c = self.ui.colors
        body = Frame(self.window, padx=18, pady=18, bg=c["bg"])
        body.pack(fill=BOTH, expand=True)

        Label(body, text="Create New Mode", bg=c["bg"], fg=c["accent"],
              font=("Consolas", 16, "bold")).pack(anchor="w")
        Label(body, text="Pick apps, websites, playlists, or folders. NaiTRO will run them all when you say the mode name.",
              bg=c["bg"], fg=c["muted"], font=("Consolas", 9)).pack(anchor="w", pady=(2, 14))

        name_row = Frame(body, bg=c["bg"])
        name_row.pack(fill="x", pady=(0, 14))
        Label(name_row, text="Mode name", bg=c["bg"], fg=c["muted"], font=("Consolas", 10)).pack(side=LEFT, padx=(0, 10))
        Entry(name_row, textvariable=self.mode_name, bg=c["panel"], fg=c["text"],
              relief="flat", highlightthickness=1, highlightbackground=c["line"],
              insertbackground=c["accent"], font=("Consolas", 11)).pack(side=LEFT, fill="x", expand=True, ipady=7)

        columns = Frame(body, bg=c["bg"])
        columns.pack(fill=BOTH, expand=True)
        left = Frame(columns, bg=c["bg"])
        left.pack(side=LEFT, fill=BOTH, expand=True)
        right = Frame(columns, bg=c["bg"])
        right.pack(side=RIGHT, fill=BOTH, expand=True, padx=(16, 0))

        kind_row = Frame(left, bg=c["bg"])
        kind_row.pack(fill="x", pady=(0, 8))
        for kind in ("apps", "websites", "playlists", "folders"):
            ttk.Button(kind_row, text=kind.title(), command=lambda v=kind: self.select_source(v)).pack(side=LEFT, padx=(0, 6))

        Label(left, text="Available", bg=c["bg"], fg=c["muted"], font=("Consolas", 9)).pack(anchor="w")
        self.source_list = Listbox(left, selectmode="multiple", bg=c["panel"], fg=c["text"],
                                   selectbackground=c["accent"], selectforeground="#fff",
                                   relief="flat", highlightthickness=1, highlightbackground=c["line"],
                                   font=("Consolas", 10))
        self.source_list.pack(fill=BOTH, expand=True, pady=(4, 8))
        ttk.Button(left, text="Add Selected →", style="Primary.TButton", command=self.add_selected).pack(fill="x")

        Label(right, text="Mode steps", bg=c["bg"], fg=c["muted"], font=("Consolas", 9)).pack(anchor="w")
        self.steps_list = Listbox(right, bg=c["panel"], fg=c["text"],
                                  selectbackground=c["accent"], selectforeground="#fff",
                                  relief="flat", highlightthickness=1, highlightbackground=c["line"],
                                  font=("Consolas", 10))
        self.steps_list.pack(fill=BOTH, expand=True, pady=(4, 8))

        step_btns = Frame(right, bg=c["bg"])
        step_btns.pack(fill="x")
        ttk.Button(step_btns, text="Remove", command=self.remove_step).pack(side=LEFT)
        ttk.Button(step_btns, text="Clear", command=self.clear_steps).pack(side=LEFT, padx=(8, 0))
        ttk.Button(step_btns, text="Save Mode", style="Primary.TButton", command=self.save).pack(side=RIGHT)

    def select_source(self, kind):
        self.source_kind.set(kind)
        self.refresh_source()

    def refresh_source(self):
        self.source_list.delete(0, END)
        data = self.ui.engine.config.get(self.source_kind.get(), {})
        for name in sorted(set(data.keys())):
            self.source_list.insert(END, name)

    def add_selected(self):
        kind = self.source_kind.get()
        step_type = kind[:-1] if kind.endswith("s") else kind
        if kind == "playlists":
            step_type = "playlist"
        for index in self.source_list.curselection():
            name = self.source_list.get(index)
            self.steps.append({"type": step_type, "name": name})
            self.steps_list.insert(END, f"{step_type}: {name}")

    def remove_step(self):
        for index in reversed(self.steps_list.curselection()):
            self.steps_list.delete(index)
            self.steps.pop(index)

    def clear_steps(self):
        self.steps.clear()
        self.steps_list.delete(0, END)

    def save(self):
        name = self.mode_name.get().strip().lower()
        if not name:
            messagebox.showerror("Missing name", "Give this mode a command name.")
            return
        if not self.steps:
            messagebox.showerror("No steps", "Add at least one step.")
            return
        self.ui.engine.config.setdefault("modes", {})[name] = self.steps
        self.ui.engine.save_config()
        self.ui._switch_tab("modes")
        self.ui.refresh_lists()
        self.ui.status_text.set(f"Mode '{name}' created.")
        self.window.destroy()


class ItemEditor:
    def __init__(self, ui, kind, name=None):
        self.ui = ui
        self.kind = kind
        self.original_name = name
        self.window = Toplevel(ui.root)
        self.window.title(f"{'Edit' if name else 'Add'} {kind[:-1].title()}")
        self.window.geometry("620x420")
        self.window.configure(bg=ui.colors["bg"])
        self.window.grab_set()
        self.name = StringVar(value=name or "")
        self.value = StringVar(value=self.current_value(name))
        self.build()

    def current_value(self, name):
        if not name:
            return ""
        data = self.ui.engine.config.get(self.kind, {}).get(name)
        if self.kind == "apps":
            return data.get("target", "") if isinstance(data, dict) else str(data)
        if self.kind == "modes":
            return json.dumps(data, indent=2)
        return str(data) if data else ""

    def build(self):
        c = self.ui.colors
        self.window.configure(bg=c["bg"])
        body = Frame(self.window, padx=16, pady=16, bg=c["bg"])
        body.pack(fill=BOTH, expand=True)

        def lbl(parent, text):
            Label(parent, text=text, bg=c["bg"], fg=c["muted"], font=("Consolas", 9)).pack(anchor="w")

        def entry(parent, var):
            e = Entry(parent, textvariable=var, bg=c["panel"], fg=c["text"],
                      insertbackground=c["accent"], relief="flat",
                      highlightthickness=1, highlightbackground=c["line"],
                      font=("Consolas", 11))
            e.pack(fill="x", pady=(2, 10), ipady=6)
            return e

        lbl(body, "Name")
        entry(body, self.name)

        if self.kind == "apps":
            lbl(body, "Command or full .exe / .lnk path")
            entry(body, self.value)
            ttk.Button(body, text="Browse", command=self.browse_file).pack(anchor="w")
        elif self.kind == "folders":
            lbl(body, "Folder path")
            entry(body, self.value)
            ttk.Button(body, text="Browse Folder", command=self.browse_folder).pack(anchor="w")
        elif self.kind == "websites":
            lbl(body, "URL")
            entry(body, self.value)
        elif self.kind == "playlists":
            lbl(body, "Spotify playlist URL or URI")
            entry(body, self.value)
        else:
            lbl(body, "Steps as JSON")
            self.mode_text = Text(body, height=12, font=("Consolas", 10),
                                  bg=c["panel"], fg=c["text"], insertbackground=c["accent"],
                                  relief="flat", highlightthickness=1, highlightbackground=c["line"])
            self.mode_text.pack(fill=BOTH, expand=True, pady=(2, 10))
            self.mode_text.insert(END, self.value.get() or json.dumps(
                [{"type": "app", "name": "chrome"}, {"type": "website", "name": "youtube"}], indent=2))

        btns = Frame(body, bg=c["bg"])
        btns.pack(fill="x", pady=(10, 0))
        ttk.Button(btns, text="Save", style="Primary.TButton", command=self.save).pack(side=RIGHT)
        ttk.Button(btns, text="Cancel", command=self.window.destroy).pack(side=RIGHT, padx=(0, 8))

    def browse_file(self):
        path = filedialog.askopenfilename(filetypes=[("Programs", "*.exe *.lnk"), ("All files", "*.*")])
        if path:
            self.value.set(path)

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.value.set(path)

    def save(self):
        name = self.name.get().strip().lower()
        if not name:
            messagebox.showerror("Missing name", "Give this item a name.")
            return
        data = self.ui.engine.config.setdefault(self.kind, {})
        if self.original_name and self.original_name != name:
            data.pop(self.original_name, None)
        if self.kind == "apps":
            target = self.value.get().strip()
            app_type = "path" if any(target.lower().endswith(x) for x in (".exe", ".lnk", ".bat", ".url")) or "\\" in target else "command"
            entry = {"type": app_type, "target": target}
            try:
                finalize_app_entry(name, entry, log=self.ui.engine.log)
            except Exception as e:
                self.ui.engine.log(f"App finalize error: {e}")
            data[name] = entry
        elif self.kind == "modes":
            try:
                data[name] = json.loads(self.mode_text.get("1.0", END))
            except json.JSONDecodeError as exc:
                messagebox.showerror("JSON error", str(exc))
                return
        else:
            data[name] = self.value.get().strip()
        self.ui.engine.save_config()
        self.ui.refresh_lists()
        self.window.destroy()


_SINGLE_INSTANCE_SOCKET = None


def acquire_single_instance_lock(port=47771):
    """Stops a second NaiTRO process from starting alongside one that's
    already running. Two live processes means two engines, two
    microphone listeners, and two text-to-speech threads, all reacting
    to the same thing you say — that's what was causing websites to
    open twice and NaiTRO's voice to sound doubled. Returns True if this
    is the only instance; False if another one already holds the lock."""
    global _SINGLE_INSTANCE_SOCKET
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
    except OSError:
        s.close()
        return False
    _SINGLE_INSTANCE_SOCKET = s  # kept open for the life of the process
    return True


if __name__ == "__main__":
    diagnostics.mark("entry: __main__")
    if not acquire_single_instance_lock():
        diagnostics.log("[startup] single-instance lock held by another process — exiting")
        print("NaiTRO is already running — not starting a second instance.")
        sys.exit(0)
    diagnostics.log("[startup] acquired single-instance lock")

    # Prefer the new web-based UI (webview_ui.py). Falls back to the
    # classic Tkinter interface if pywebview isn't installed or the
    # web/ assets aren't next to this file, so this never leaves you
    # with nothing running.
    try:
        from webview_ui import NaitroWebController
        NaitroWebController().start()
    except Exception as exc:
        diagnostics.exception("webview_ui start", exc)
        print(f"Web UI unavailable ({exc}); falling back to the classic interface.")
        try:
            NaitroUI().run()
        except Exception as fallback_exc:
            # Don't let the fallback die silently — a fresh install that
            # can't open either UI should print the real reason, not hang
            # or vanish.
            diagnostics.exception("NaitroUI fallback", fallback_exc)
            print(f"Classic interface also failed: {fallback_exc}")
            raise

