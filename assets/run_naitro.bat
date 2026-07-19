@echo off
setlocal
cd /d "%~dp0"
python naitro_app.py
if errorlevel 1 (
  echo.
  echo NaiTRO could not start. Make sure Python is installed and dependencies are installed:
  echo python -m pip install -r requirements.txt
  pause
)
