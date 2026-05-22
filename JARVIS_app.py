import json
import os
import queue
import difflib
import random
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
import webbrowser
import math
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

if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    APP_DIR = Path(sys.executable).resolve().parent
else:
    # Running as normal .py script
    APP_DIR = Path(__file__).resolve().parent

CONFIG_PATH = APP_DIR / "config.json"

DEFAULT_CONFIG = {
    "wake_phrase": "hey jarvis",
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
    },
    "conversation": {
        "enabled": True,
        "name": "JARVIS",
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
}

@dataclass
class ActionResult:
    ok: bool
    message: str

class JarvisEngine:
    def __init__(self, config_path=CONFIG_PATH, log=None):
        self.config_path = Path(config_path)
        self.log = log or (lambda text: None)
        self.discovered_apps = None
        self.config = self.load_config()
        self._is_speaking = False
        self._speech_cooldown_until = 0
        self._tts_engine = None

    def load_config(self):
        if not self.config_path.exists():
            self.save_config(DEFAULT_CONFIG)
        with self.config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
        migrated, changed = self.migrate_config(config)
        if changed:
            self.save_config(migrated)
        return migrated

    def migrate_config(self, config):
        changed = False
        config, did_change = self.deep_merge_defaults(config, DEFAULT_CONFIG)
        changed = changed or did_change
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
        return config, changed

    def save_config(self, config=None):
        data = config if config is not None else self.config
        with self.config_path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

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

    def respond(self, text):
        self.log(f"JARVIS: {text}")
        self._speech_cooldown_until = max(self._speech_cooldown_until, time.time() + 1.5)
        if self.config.get("voice", {}).get("speak_responses", True):
            def _speak():
                try:
                    import pyttsx3
                    # Initialize inside thread to avoid COM issues on Windows
                    self._is_speaking = True
                    engine = pyttsx3.init()
                    engine.say(text)
                    engine.runAndWait()
                    self._is_speaking = False
                    self._speech_cooldown_until = time.time() + 1.25
                except Exception as e:
                    self.log(f"TTS Error: {e}")
                    self._is_speaking = False
                    self._speech_cooldown_until = time.time() + 0.75
            threading.Thread(target=_speak, daemon=True).start()

    def is_audio_output_active(self):
        return self._is_speaking or time.time() < self._speech_cooldown_until

    def run_command(self, raw_command):
        command = self.strip_wake_phrase(raw_command)
        title = self.config.get("conversation", {}).get("user_title", "sir")
        self.log(f"YOU: {raw_command}")
        if not command:
            self.respond("I am here. What are we doing today?")
            return ActionResult(True, "Ready")

        music_target = self.extract_music_target(command)
        if music_target:
            kind, target = music_target
            return self.play_music(target, kind)

        if any(p in command for p in ("start ollama", "load ollama", "wake up ollama")):
            def _start():
                NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000
                subprocess.Popen(["ollama", "serve"], creationflags=NO_WINDOW)
                time.sleep(2)
                self.respond(f"Ollama is running, {title}. AI is online.")
            threading.Thread(target=_start, daemon=True).start()
            return ActionResult(True, "ollama started")

        if any(p in command for p in ("stop ollama", "close ollama", "kill ollama")):
            NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000
            subprocess.run(["taskkill", "/f", "/im", "ollama.exe"], creationflags=NO_WINDOW, capture_output=True)
            self.respond(f"Ollama stopped, {title}. VRAM is free for gaming.")
            return ActionResult(True, "ollama stopped")

        action_target = self.extract_action_target(command)
        if action_target:
            action, target = action_target
            if action == "search":
                return self.search_web(target)
            if action == "mode":
                return self.run_mode(target)
            if action == "close":
                return self.close_app(target)
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
        text = re.sub(r"[^a-z0-9:/?.&%+\-\\ ]+", " ", text)
        return text.strip()

    def strip_wake_phrase(self, text):
        command = self.normalize(text)
        wake = self.normalize(self.config.get("wake_phrase", "hey jarvis"))
        command = self.repair_wake_mishear(command)
        # Exact strip
        if command.startswith(wake):
            return command[len(wake):].strip()
        # Try stripping first 1-2 words if they look like the wake phrase
        words = command.split()
        for n in (2, 1):
            prefix = " ".join(words[:n])
            if difflib.SequenceMatcher(None, prefix, wake).ratio() > 0.6:
                return " ".join(words[n:]).strip()
        return command

    def repair_wake_mishear(self, command):
        wake = self.normalize(self.config.get("wake_phrase", "hey jarvis"))
        aliases = (
            "hazardous", "hey hazardous", "hazard is", "hey hazard is",
            "hey service", "service", "jarves", "jarvis", "travis",
            "hey travis", "hey jarves", "hey jars", "javis", "hey javis",
            "jarvis open", "hazardous open"
        )
        words = command.split()
        for alias in aliases:
            if command.startswith(alias):
                rest = command[len(alias):].strip()
                return f"hey jarvis {rest}".strip()

        # Google sometimes returns a short phrase that sounds close but is not spelled close.
        for n in (2, 1):
            prefix = " ".join(words[:n])
            if prefix and difflib.SequenceMatcher(None, prefix, wake).ratio() > 0.55:
                return f"hey jarvis {' '.join(words[n:])}".strip()
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

    def best_target(self, command):
        command = self.normalize(command)
        # Exact match first
        for kind in ["modes", "apps", "websites", "playlists", "folders"]:
            data = self.config.get(kind, {})
            if command in data:
                return kind, command
        # Fuzzy match for modes so "gaming mode" finds "gaming mode" even with typos
        for kind in ["modes", "apps", "websites", "playlists", "folders"]:
            data = self.config.get(kind, {})
            matches = difflib.get_close_matches(command, data.keys(), n=1, cutoff=0.75)
            if matches:
                return kind, matches[0]
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
            os.startfile(spotify_uri)
            return ActionResult(True, spotify_uri)
        except Exception:
            self.open_url(web_url)
            return ActionResult(True, web_url)

    def open_url(self, url):
        try:
            os.startfile(url)
        except Exception:
            webbrowser.open(url)

    def open_target(self, name):
        name = self.normalize(name)

        # Prefer apps over websites when names overlap, e.g. Spotify.
        app = self.config.get("apps", {}).get(name)
        if app:
            target = app.get("target")
            self.respond(f"Opening {name}, sir.")
            return self.launch(target)

        site = self.config.get("websites", {}).get(name)
        if site:
            self.respond(f"Opening {name} in your browser, sir.")
            self.open_url(site)
            return ActionResult(True, site)

        playlist = self.config.get("playlists", {}).get(name)
        if playlist:
            self.respond(f"Playing {name}, sir.")
            self.open_url(playlist)
            return ActionResult(True, playlist)

        # Check Folders
        folder = self.config.get("folders", {}).get(name)
        if folder:
            expanded = os.path.expandvars(folder)
            self.respond(f"Opening your {name} folder, sir.")
            return self.launch(expanded)

        self.respond(f"I couldn't find {name}, sir. Try adding it in the sidebar.")
        return ActionResult(False, "Not found")

    def launch(self, target):
        NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000
        try:
            os.startfile(target)
            return ActionResult(True, target)
        except Exception:
            try:
                import ctypes
                ret = ctypes.windll.shell32.ShellExecuteW(None, "open", target, None, None, 1)
                if ret > 32:
                    return ActionResult(True, target)
            except Exception:
                pass
            try:
                subprocess.Popen(target, shell=False, creationflags=NO_WINDOW)
                return ActionResult(True, target)
            except Exception as e2:
                self.log(f"Launch error: {e2}")
                return ActionResult(False, str(e2))

    def close_app(self, name):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        name = self.normalize(name)
        process_map = {
            "chrome": ["chrome.exe"], "google chrome": ["chrome.exe"],
            "opera gx": ["opera.exe"], "edge": ["msedge.exe"],
            "discord": ["discord.exe"], "obs": ["obs64.exe", "obs.exe"],
            "obs studio": ["obs64.exe", "obs.exe"], "steam": ["steam.exe"],
            "epic games": ["epicgameslauncher.exe"], "valorant": ["valorant.exe", "vanguard.exe"],
            "spotify": ["spotify.exe"], "zoom": ["zoom.exe"],
            "roblox": ["robloxplayerbeta.exe"], "pycharm": ["pycharm64.exe"],
            "notepad": ["notepad.exe"], "calculator": ["calculatorapp.exe", "calc.exe"],
            "task manager": ["taskmgr.exe"], "davinci resolve": ["resolve.exe"],
            "resolve": ["resolve.exe"], "medal": ["medal.exe"],
            "word": ["winword.exe"], "excel": ["excel.exe"],
            "powerpoint": ["powerpnt.exe"], "onenote": ["onenote.exe"],
            "vpn": ["privadovpn.exe"], "privado vpn": ["privadovpn.exe"],
            "nvidia app": ["nvclient.exe"], "rainmeter": ["rainmeter.exe"],
        }
        # Browsers and apps that need graceful close (no /f flag)
        graceful = {"chrome.exe", "msedge.exe", "opera.exe", "firefox.exe"}
        processes = process_map.get(name, [f"{name.replace(' ', '')}.exe", f"{name}.exe"])
        NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000
        killed = False
        for proc in processes:
            try:
                # Use graceful close for browsers, force kill for everything else
                flags = [] if proc in graceful else ["/f"]
                result = subprocess.run(
                    ["taskkill"] + flags + ["/im", proc],
                    capture_output=True, text=True, creationflags=NO_WINDOW
                )
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
            self.respond(random.choice([
                f"Could not find {name} running, {title}.",
                f"{name.title()} does not appear to be open, {title}.",
            ]))
            return ActionResult(False, f"Not running: {name}")

    def run_mode(self, mode_name):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        modes = self.config.get("modes", {})
        mode = modes.get(mode_name)
        # Try without "mode" suffix e.g. "gaming" → "gaming mode"
        if not mode:
            for key in modes:
                if self.normalize(key) == self.normalize(mode_name):
                    mode = modes[key]
                    mode_name = key
                    break
        if not mode:
            stripped = mode_name.replace(" mode", "").strip()
            for key in modes:
                if stripped in self.normalize(key):
                    mode = modes[key]
                    mode_name = key
                    break
        if not mode:
            self.respond(f"I don't have a routine called {mode_name}, {title}.")
            return ActionResult(False, "Mode not found")

        self.respond(random.choice([
            f"Activating {mode_name}, {title}.",
            f"On it, {title}. Starting {mode_name}.",
            f"Right away, {title}.",
        ]))

        def _run():
            for step in mode:
                delay = step.get("delay", 0.5)
                time.sleep(delay)
                m_type = step.get("type")
                m_name = step.get("name", "")
                if m_type == "app":
                    app = self.config.get("apps", {}).get(m_name)
                    if app:
                        self.launch(app.get("target", m_name))
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

    def chat(self, text):
        title = self.config.get("conversation", {}).get("user_title", "sir")
        style = self.config.get("conversation", {}).get("style", "sharp, calm, witty")
        norm = self.normalize(text)
        now = datetime.now()
        hour = now.hour

        # Local time/date (no API needed)
        if "time" in norm and "what" in norm:
            suffix = "morning" if hour < 12 else "afternoon" if hour < 18 else "evening"
            return self.respond(f"It is {now.strftime('%I:%M %p')}, {title}. Good {suffix}.")
        if ("date" in norm or "what day" in norm) and any(p in norm for p in ("what", "today", "is it")):
            return self.respond(f"Today is {now.strftime('%A, %B %d, %Y')}, {title}.")

        # Try OpenRouter API for everything else
        # Try Gemini API if key is set
        gemini_key = self.config.get("gemini_api_key", "").strip()
        if True:  # Always try AI
            def _ask_ai():
                import json as _json, urllib.request as _req
                system_prompt = (
                    f"You are JARVIS, a sharp, witty, loyal personal AI assistant running on a Windows PC. "
                    f"Personality: {style}. Address the user as '{title}'. "
                    f"You have knowledge of gaming, tech, streaming, and current trends. "
                    f"Be conversational, confident, never sycophantic. "
                    f"Keep responses to 2-4 sentences unless more detail is genuinely needed."
                )

                # Try Ollama first (local, no internet needed)
                try:
                    payload = _json.dumps({
                        "model": "phi3:mini",
                        "prompt": f"{system_prompt}\n\nUser: {text}\nJARVIS:",
                        "stream": False
                    }).encode("utf-8")
                    req = _req.Request(
                        "http://localhost:11434/api/generate",
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST"
                    )
                    with _req.urlopen(req, timeout=120) as resp:
                        data = _json.loads(resp.read().decode("utf-8"))
                        reply = data["response"].strip()
                        self.respond(reply)
                        return
                except Exception as e:
                    self.log(f"Ollama unavailable: {e} — trying Gemini")

                # Fallback to Gemini if Ollama isn't running
                if gemini_key:
                    try:
                        payload = _json.dumps({
                            "contents": [{"parts": [{"text": f"{system_prompt}\n\nUser: {text}"}]}],
                            "generationConfig": {"maxOutputTokens": 300}
                        }).encode("utf-8")
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                        req = _req.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                        with _req.urlopen(req, timeout=15) as resp:
                            data = _json.loads(resp.read().decode("utf-8"))
                            reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                            self.respond(reply)
                            return
                    except Exception as e:
                        self.log(f"Gemini error: {e}")

                self.respond(random.choice([
                    f"Both AI services are unavailable right now, {title}. Try again in a moment.",
                    f"No AI connection at the moment, {title}. Give me a second.",
                ]))

            threading.Thread(target=_ask_ai, daemon=True).start()
            return ActionResult(True, "chat")


        # Built-in replies
        if any(p in norm for p in ("how are you", "you good", "you okay", "you alright")):
            return self.respond(random.choice([f"Running clean, {title}. No complaints.", f"Operational and mildly entertained, {title}.", f"Perfectly calibrated, {title}."]))
        if any(p in norm for p in ("hello", "hi", "hey", "wassup", "sup", "yo")):
            return self.respond(random.choice([f"Hey {title}. What do you need?", f"Here and ready, {title}. What's the move?"]))
        if any(p in norm for p in ("thank you", "thanks", "good job", "cheers")):
            return self.respond(random.choice([f"Just doing my job, {title}.", f"Anytime, {title}.", f"Try not to make a habit of thanking the AI, {title}."]))
        if any(p in norm for p in ("good morning", "morning")):
            return self.respond(random.choice([f"Good morning, {title}.", f"Morning, {title}. What are we getting into?"]))
        if any(p in norm for p in ("good night", "night", "going to sleep")):
            return self.respond(random.choice([f"Rest well, {title}.", f"Goodnight, {title}."]))
        if any(p in norm for p in ("who are you", "what are you", "your name")):
            return self.respond(f"I am JARVIS — your personal PC assistant, {title}.")
        if any(p in norm for p in ("what can you do", "help", "commands")):
            return self.respond(f"I can open apps, websites, folders, and run your custom modes, {title}. Try 'open Discord', 'gaming mode', or 'search best GPU 2025'.")

        self.respond(random.choice([
            f"Did not quite catch that, {title}. Try 'open [app]', a mode name, or 'search [something]'.",
            f"Not sure what to do with that one, {title}. Give me an app, a mode, or a search.",
        ]))
        return ActionResult(True, "chat")

    def was_addressed_to_jarvis(self, text):
        norm = self.repair_wake_mishear(self.normalize(text))
        wake = self.normalize(self.config.get("wake_phrase", "hey jarvis"))
        # Exact match
        if wake in norm:
            return True
        # Fuzzy match — catches mishearings like "hay jarvis", "hey javis", "hazardous jarvis" etc
        words = norm.split()
        for i in range(len(words)):
            chunk = " ".join(words[i:i+2])
            if difflib.SequenceMatcher(None, chunk, wake).ratio() > 0.7:
                return True
        # Also catch just "jarvis" alone
        if "jarvis" in norm:
            return True
        return False

class JarvisUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("JARVIS Control Panel")
        try:
            if getattr(sys, 'frozen', False):
                # If running as EXE, look in the temp folder
                icon_path = os.path.join(sys._MEIPASS, "JARVIS.ico")
            else:
                # If running as .py, look in the current folder
                icon_path = "JARVIS.ico"

            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception:
            pass
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
        
        self.engine = JarvisEngine(log=self.enqueue_log)
        self.events = queue.Queue()
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
        self.root.after(700, self.startup_greeting)
        self.root.after(500, self.setup_tray)
        
        if self.engine.config.get("voice", {}).get("auto_start", True):
            self.root.after(1000, self.start_voice)

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
        
        Label(self.sidebar, text="JARVIS", font=("Consolas", 18, "bold"), fg=self.colors["accent"], bg=self.colors["panel"]).pack(anchor="w")
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
        
        header = Frame(self.main_panel, bg=self.colors["bg"])
        header.pack(fill="x")
        ttk.Button(header, text="Menu", width=8, command=self.toggle_sidebar).pack(side=LEFT)
        Label(header, textvariable=self.status_text, font=("Consolas", 10), fg=self.colors["muted"], bg=self.colors["bg"]).pack(side=LEFT, padx=15)
        ttk.Button(header, text="Shut Down", command=self.shutdown).pack(side=RIGHT)

        # X button minimizes to background, no confirm dialog
        self.root.protocol("WM_DELETE_WINDOW", self.minimize_to_background)

        self.home_modes = Frame(self.main_panel, bg=self.colors["panel"], padx=16, pady=12)
        self.home_modes.pack(fill="x", pady=(18, 0))
        mode_head = Frame(self.home_modes, bg=self.colors["panel"])
        mode_head.pack(fill="x")
        Label(
            mode_head,
            text="Your Modes",
            font=("Consolas", 12, "bold"),
            fg=self.colors["text"],
            bg=self.colors["panel"],
        ).pack(side=LEFT)
        ttk.Button(mode_head, text="+ New Mode", style="Primary.TButton", command=self.create_mode).pack(side=RIGHT)
        ttk.Button(mode_head, text="View Modes", command=self.open_modes_sidebar).pack(side=RIGHT, padx=(0, 8))
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
            "websites": ("Websites", "Saved links JARVIS can open."),
            "playlists": ("Playlists", "Spotify playlists JARVIS can play."),
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
                    pystray.MenuItem("Show JARVIS", lambda: self.root.after(0, self._show_window), default=True),
                    pystray.MenuItem("Shut Down", lambda: self.root.after(0, self.shutdown)),
                )
                self.tray_icon = pystray.Icon("JARVIS", img, "JARVIS", menu)
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

    def startup_greeting(self):
        greeting = "Good to see you, sir. What are we doing today?"
        self.engine.respond(greeting)
        self.conversation_active = True
        self.last_interaction_time = time.time()

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
            if self.engine.was_addressed_to_jarvis(candidate) or self.is_actionable_voice_command(candidate):
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
                            self.enqueue_log("Ignored voice while JARVIS was speaking.")
                            continue
                        text = self.recognize_best_text(recognizer, audio, sr)
                        if not text:
                            continue
                        self.enqueue_log(f"Heard: {text}")
                        
                        addressed = self.engine.was_addressed_to_jarvis(text)
                        actionable = self.is_actionable_voice_command(text)
                        if addressed or self.conversation_active or actionable:
                            self.conversation_active = True
                            self.last_interaction_time = time.time()
                            norm = text.lower()
                            if any(p in norm for p in ("shut down jarvis", "shutdown jarvis", "exit jarvis", "quit jarvis", "shut down", "power off", "turn off jarvis", "goodbye jarvis", "bye jarvis")):
                                self.engine.respond("Shutting down. Goodbye, sir.")
                                self.root.after(3500, self.shutdown)
                            elif any(p in norm for p in ("show jarvis", "open jarvis", "bring up jarvis", "show yourself", "come back", "jarvis show", "jarvis open", "wake up jarvis")):
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

    def send_command(self):
        cmd = self.command_text.get().strip()
        if not cmd:
            return
        self.command_text.set("")
        norm = cmd.lower().strip()
        if any(p in norm for p in ("shut down jarvis", "shutdown jarvis", "exit jarvis", "quit jarvis", "close jarvis", "shut down", "power off", "turn off jarvis", "goodbye jarvis", "bye jarvis")):
            self.engine.respond(f"Shutting down. Goodbye, sir.")
            self.root.after(3500, self.shutdown)
            return
        if any(p in norm for p in ("show jarvis", "open jarvis", "bring up jarvis", "show yourself", "come back", "jarvis show", "wake up jarvis")):
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
            os.startfile(str(CONFIG_PATH))
        except Exception:
            NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000
            subprocess.Popen(["notepad.exe", str(CONFIG_PATH)], creationflags=NO_WINDOW)

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
        Label(body, text="Pick apps, websites, playlists, or folders. JARVIS will run them all when you say the mode name.",
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
            data[name] = {"type": app_type, "target": target}
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


if __name__ == "__main__":
    JarvisUI().run()
