#!/bin/bash
# setup_linux.sh — one-shot setup for JARVIS on Ubuntu/Debian.
#
# Handles everything that pip alone can't:
#   - system audio/mic libraries (PortAudio, Tk, ffmpeg)
#   - the GTK + WebKit stack the web UI needs (pywebview has no UI of its
#     own on Linux -- it just embeds one of these)
#   - a Python 3.13 venv (3.14 breaks SpeechRecognition)
#
# Run this once from the project folder:
#   chmod +x setup_linux.sh && ./setup_linux.sh

set -e

echo "== Installing system packages (you'll be asked for your password) =="
sudo apt update
sudo apt install -y \
    python3.13 python3.13-venv python3.13-dev \
    portaudio19-dev python3-tk ffmpeg \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    libgirepository-2.0-dev gir1.2-girepository-2.0 \
    libcairo2-dev pkg-config gcc

# The WebKit GObject-introspection package's name varies by Ubuntu release.
# Try the modern name first, fall back to the older one.
sudo apt install -y gir1.2-webkit2-4.1 2>/dev/null \
    || sudo apt install -y gir1.2-webkit2gtk-4.0 2>/dev/null \
    || echo "!! Could not find a WebKit GObject package automatically."\
            " JARVIS will still run using its classic interface, but the"\
            " newer web UI needs one of: gir1.2-webkit2-4.1 or"\
            " gir1.2-webkit2gtk-4.0 -- search 'apt-cache search webkit2'"\
            " for the name on your release if you want the web UI too."

echo ""
echo "== Creating a Python 3.13 virtual environment (venv/) =="
rm -rf venv
python3.13 -m venv venv
source venv/bin/activate

echo ""
echo "== Installing Python packages =="
pip install --upgrade pip
pip install -r requirements.txt
pip install pycairo PyGObject

echo ""
echo "== Done =="
echo "Run JARVIS with:"
echo "    source venv/bin/activate"
echo "    python JARVIS_app.py"
echo ""
echo "If it prints 'Web UI unavailable (...)', the classic interface will"
echo "still open and JARVIS will still work -- just without the newer"
echo "sidebar look. Re-run this script after checking the WebKit package"
echo "name for your specific Ubuntu version if you want to fix that."
