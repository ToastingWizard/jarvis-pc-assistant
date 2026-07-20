"""
discover_apps.py — auto-populate NaiTRO's config.json "apps" section from
every app already installed on this Linux machine.

Linux apps that show up in your applications menu each have a .desktop
file describing their name and launch command -- this script reads all
of those (system-wide, user-installed, Flatpak, and Snap) and merges
them into config/config.json, so "hey naitro, open <app>" works for
everything already on your machine without typing each one in by hand.

Safe to re-run any time: it only ADDS apps that aren't already in your
config (by normalized name) -- it never touches or removes anything
you've already set up, and never touches any other part of config.json
(your API key, voice settings, etc. are left completely alone).

Usage:
    python scripts/discover_apps.py            # merge discovered apps into config.json
    python scripts/discover_apps.py --dry-run  # show what WOULD be added, change nothing
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.json"

# Standard locations Linux apps register their .desktop files -- covers
# system packages (apt/dnf/pacman), user-local installs, Flatpak, and Snap.
DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path("/var/lib/snapd/desktop/applications"),
]

# Desktop Entry Specification field codes (%f, %U, etc.) -- these get
# substituted with real filenames/URLs when a real launcher invokes the
# app; meaningless (and would break) if left in as literal text here.
_FIELD_CODE_RE = re.compile(r"%[fFuUdDnNickvm]")


def _parse_desktop_file(path: Path) -> Optional[tuple[str, str]]:
    """Return (name, exec_command) for a .desktop file, or None if it's
    not a real launchable app (a helper entry, hidden, or missing an Exec
    line)."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    # Only look at the [Desktop Entry] section, not [Desktop Action ...]
    # sub-sections some apps also define.
    section = text.split("[Desktop Entry]", 1)
    if len(section) < 2:
        return None
    body = section[1].split("\n[", 1)[0]

    fields = {}
    for line in body.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, _, value = line.partition("=")
            fields.setdefault(key.strip(), value.strip())

    if fields.get("Type", "Application") != "Application":
        return None
    if fields.get("NoDisplay", "").lower() == "true":
        return None
    if fields.get("Hidden", "").lower() == "true":
        return None
    if fields.get("Terminal", "").lower() == "true":
        # Skip terminal apps (htop, vim, etc.) -- launching these without
        # an actual terminal window attached wouldn't do anything useful,
        # and guessing a working terminal-emulator wrapper reliably
        # across different desktop setups isn't safe to assume.
        return None

    name = fields.get("Name", "").strip()
    exec_line = fields.get("Exec", "").strip()
    if not name or not exec_line:
        return None

    exec_clean = _FIELD_CODE_RE.sub("", exec_line).strip()
    return name, exec_clean


def discover_installed_apps() -> dict[str, str]:
    """Scan all known .desktop locations. Returns {app_name: command}."""
    found: dict[str, str] = {}
    for directory in DESKTOP_DIRS:
        if not directory.is_dir():
            continue
        for desktop_file in directory.glob("*.desktop"):
            parsed = _parse_desktop_file(desktop_file)
            if not parsed:
                continue
            name, command = parsed
            # First one wins if the same app name shows up in multiple
            # locations (e.g. both a .deb and a Flatpak build of it).
            found.setdefault(name, command)
    return found


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"No config.json found at {CONFIG_PATH}.")
        print("Launch NaiTRO once first (it creates config.json with defaults on first run),")
        print("then re-run this script.")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def main():
    dry_run = "--dry-run" in sys.argv

    config = load_config()
    existing_apps = config.setdefault("apps", {})
    existing_keys = {k.strip().lower() for k in existing_apps}

    discovered = discover_installed_apps()

    to_add = {}
    for name, command in discovered.items():
        key = name.strip().lower()
        if key in existing_keys:
            continue  # already configured -- never overwrite what's there
        to_add[key] = {"type": "command", "target": command}

    if not to_add:
        print("Nothing new to add -- every discovered app is already in your config.")
        return

    print(f"Found {len(discovered)} installed apps, {len(to_add)} of them new:\n")
    for key, entry in sorted(to_add.items()):
        print(f"  {key:30s} -> {entry['target']}")

    if dry_run:
        print(f"\n(dry run -- config.json was not changed. {len(to_add)} apps would be added.)")
        return

    existing_apps.update(to_add)
    save_config(config)
    print(f"\nAdded {len(to_add)} apps to {CONFIG_PATH}.")
    print('Try it: "hey naitro, open <app name>"')


if __name__ == "__main__":
    main()
