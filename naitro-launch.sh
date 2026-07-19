#!/bin/bash

PROJECT="/home/vishwamanava/NaiTRO/naitro-pc-assistant-main"

cd "$PROJECT" || exit 1

if [ -f "venv/bin/python" ]; then
    exec venv/bin/python Python/naitro_app.py
else
    exec python3 Python/naitro_app.py
fi
