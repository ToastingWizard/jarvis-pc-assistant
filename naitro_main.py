"""
NaiTRO 2.0 - Main Entry Point
Launches the HTTP server and opens the browser UI.
"""

import sys
import os
from pathlib import Path

# Add Python directory to path
if getattr(sys, 'frozen', False):
    # Running as frozen executable
    base_dir = Path(sys.executable).parent
    python_dir = base_dir / "Python"
    if python_dir.exists():
        sys.path.insert(0, str(python_dir))
else:
    # Running from source
    python_dir = Path(__file__).parent / "Python"
    sys.path.insert(0, str(python_dir))

# Import and launch
from http_server import launch_naitro

if __name__ == "__main__":
    launch_naitro()
