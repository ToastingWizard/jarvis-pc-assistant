"""
fix_mic_autostart.py — one-time fix for NaiTRO launching with the mic off.

Run this once from your NaiTRO project folder:

    python fix_mic_autostart.py

It edits your real config.json (NOT config.example.json) and sets
voice.auto_start to true, leaving everything else in the file untouched.
Safe to run more than once.
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main():
    if not CONFIG_PATH.exists():
        print(f"Couldn't find {CONFIG_PATH}.")
        print("Make sure this script is in the same folder as your config.json,")
        print("or edit CONFIG_PATH at the top of this file to point at it.")
        return

    with CONFIG_PATH.open("r", encoding="utf-8-sig") as f:
        config = json.load(f)

    voice = config.setdefault("voice", {})
    before_auto_start = voice.get("auto_start")
    before_enabled = voice.get("enabled")
    voice["auto_start"] = True
    voice["enabled"] = True

    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    changed = []
    if before_auto_start is not True:
        changed.append(f"voice.auto_start: {before_auto_start!r} -> true")
    if before_enabled is not True:
        changed.append(f"voice.enabled: {before_enabled!r} -> true")

    if not changed:
        print("voice.auto_start and voice.enabled were already true — nothing to change.")
        print("If the mic is still off on launch, the cause is elsewhere")
        print("(most likely something in web/app.js turning it off after load).")
    else:
        for line in changed:
            print(line)
        print("Restart NaiTRO — the mic should now turn on automatically.")


if __name__ == "__main__":
    main()
