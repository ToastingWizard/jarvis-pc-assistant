#!/bin/bash
# Launches JARVIS from its project folder, using a venv if one exists.
cd "$(dirname "$0")"
if [ -f "venv/bin/python" ]; then
    exec venv/bin/python JARVIS_app.py
else
    exec python3 JARVIS_app.py
fi
