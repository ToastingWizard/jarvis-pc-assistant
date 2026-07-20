#!/bin/bash
# install.sh — one-time Linux setup for NaiTRO.
#
# Run this ONCE after downloading/cloning the project:
#     ./install.sh
#
# What it does (all the stuff that took hours to figure out by hand):
#   1. Detects your package manager and installs the system libraries
#      NaiTRO's web UI (GTK/WebKit) and voice engine (PortAudio/espeak)
#      actually need -- these can't come from pip, they're OS packages.
#   2. Creates a Python venv WITH access to those system packages
#      (--system-site-packages), in the project's own folder.
#   3. Installs all Python dependencies, including Playwright + a real
#      Chromium build for it.
#   4. Writes a working desktop launcher (icon you can click), pointing
#      at THIS exact install location.
#
# Safe to re-run any time -- e.g. after moving the project folder,
# since venvs break when moved (they bake in absolute paths). Re-running
# this script rebuilds everything cleanly for wherever it now lives.
#
# Supports: Debian/Ubuntu (apt), Fedora (dnf), Arch (pacman).
# Other distros: the script will tell you exactly what's missing so you
# can install it by hand with your own package manager.

set -uo pipefail

# ---------------------------------------------------------------------------
# Resolve paths relative to THIS script, wherever it's actually run from.
# ---------------------------------------------------------------------------
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON_ENTRY="$PROJECT_DIR/Python/naitro_app.py"
REQUIREMENTS="$PROJECT_DIR/requirements.txt"
ICON_PATH="$PROJECT_DIR/assets/naitro-icon.png"
LAUNCH_SCRIPT="$PROJECT_DIR/naitro-launch.sh"
DESKTOP_FILE="$HOME/.local/share/applications/naitro.desktop"

# ---------------------------------------------------------------------------
# Pretty output helpers
# ---------------------------------------------------------------------------
c_reset="\033[0m"; c_bold="\033[1m"; c_green="\033[32m"; c_yellow="\033[33m"; c_red="\033[31m"; c_blue="\033[34m"
step()  { echo -e "\n${c_bold}${c_blue}==>${c_reset} ${c_bold}$1${c_reset}"; }
ok()    { echo -e "  ${c_green}✓${c_reset} $1"; }
warn()  { echo -e "  ${c_yellow}!${c_reset} $1"; }
fail()  { echo -e "  ${c_red}✗${c_reset} $1"; }

FAILED_STEPS=()

# ---------------------------------------------------------------------------
# 1. Detect package manager + install system dependencies
# ---------------------------------------------------------------------------
step "Detecting your Linux distro"

install_system_deps() {
    if command -v apt-get >/dev/null 2>&1; then
        ok "Detected apt (Debian/Ubuntu)"
        sudo apt-get update -qq
        # Python 3.13 specifically -- NOT whatever python3 defaults to.
        # Python 3.14 (the default on very recent Ubuntu) reportedly
        # breaks SpeechRecognition; pinning 3.13 avoids that entirely
        # rather than working around it after the fact.
        sudo apt-get install -y \
            python3.13 python3.13-venv python3.13-dev \
            python3-pip python3-gi python3-gi-cairo \
            gir1.2-gtk-3.0 portaudio19-dev espeak-ng \
            python3-tk ffmpeg \
            libgirepository-2.0-dev gir1.2-girepository-2.0 \
            libcairo2-dev pkg-config gcc \
            gir1.2-webkit2-4.1 2>/dev/null \
        || sudo apt-get install -y \
            python3.13 python3.13-venv python3.13-dev \
            python3-pip python3-gi python3-gi-cairo \
            gir1.2-gtk-3.0 portaudio19-dev espeak-ng \
            python3-tk ffmpeg \
            libgirepository-2.0-dev gir1.2-girepository-2.0 \
            libcairo2-dev pkg-config gcc \
            gir1.2-webkit2-4.0

    elif command -v dnf >/dev/null 2>&1; then
        ok "Detected dnf (Fedora)"
        sudo dnf install -y \
            python3.13 python3-pip python3-gobject \
            gtk3 webkit2gtk4.1 portaudio-devel espeak-ng \
            python3-tkinter ffmpeg cairo-devel gcc pkgconf-pkg-config 2>/dev/null \
        || sudo dnf install -y \
            python3.13 python3-pip python3-gobject \
            gtk3 webkit2gtk3 portaudio-devel espeak-ng \
            python3-tkinter ffmpeg cairo-devel gcc pkgconf-pkg-config

    elif command -v pacman >/dev/null 2>&1; then
        ok "Detected pacman (Arch)"
        sudo pacman -Sy --needed --noconfirm \
            python313 python-pip python-gobject gtk3 webkit2gtk-4.1 \
            portaudio espeak-ng tk ffmpeg cairo pkgconf gcc 2>/dev/null \
        || sudo pacman -Sy --needed --noconfirm \
            python313 python-pip python-gobject gtk3 webkit2gtk portaudio espeak-ng tk ffmpeg cairo pkgconf gcc

    else
        fail "Unrecognized package manager."
        warn "Install these manually before continuing, then re-run this script:"
        warn "  - Python 3.13 specifically + venv + pip (NOT 3.14 -- reportedly breaks SpeechRecognition)"
        warn "  - PyGObject (python3-gi / python-gobject) + build tools (gcc, pkg-config, libcairo/libgirepository dev headers)"
        warn "  - GTK3 + WebKit2GTK (for the app window)"
        warn "  - PortAudio dev headers (for microphone input)"
        warn "  - espeak-ng (offline text-to-speech fallback), ffmpeg, and Tkinter (python3-tk) for the classic UI fallback"
        FAILED_STEPS+=("system packages")
        return 1
    fi
}

if install_system_deps; then
    ok "System packages installed"
else
    warn "Continuing anyway -- some features may not work until these are installed."
fi

# ---------------------------------------------------------------------------
# 2. Create (or rebuild) the venv, WITH system packages visible
# ---------------------------------------------------------------------------
step "Setting up the Python environment"

if [ -d "$VENV_DIR" ]; then
    warn "Existing venv found at $VENV_DIR -- rebuilding it fresh."
    warn "(venvs break when the project folder is moved; this guarantees it's correct for THIS location.)"
    rm -rf "$VENV_DIR"
fi

# Python 3.13 specifically, NOT --system-site-packages -- see the note
# above install_system_deps() for why. Falls back to plain python3 only
# if 3.13 genuinely isn't available (with a clear warning, since that's
# the untested/possibly-broken path).
if command -v python3.13 >/dev/null 2>&1; then
    PYTHON_BIN="python3.13"
else
    warn "python3.13 not found -- falling back to python3, which may be a version"
    warn "SpeechRecognition doesn't support yet. Consider installing python3.13 by hand."
    PYTHON_BIN="python3"
fi

if "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    ok "Created venv at $VENV_DIR using $PYTHON_BIN"
else
    fail "Could not create the venv. Is ${PYTHON_BIN}-venv installed?"
    FAILED_STEPS+=("venv creation")
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -x "$VENV_PY" ]; then
    fail "venv Python not found at $VENV_PY -- cannot continue with Python package installs."
    FAILED_STEPS+=("venv python")
else
    # ---------------------------------------------------------------------
    # 3. Python dependencies + Playwright's browser
    # ---------------------------------------------------------------------
    step "Installing Python packages"

    "$VENV_PIP" install --upgrade pip -q

    if [ -f "$REQUIREMENTS" ]; then
        if "$VENV_PIP" install -r "$REQUIREMENTS" -q; then
            ok "Installed packages from requirements.txt"
        else
            fail "Some packages in requirements.txt failed to install -- see output above."
            FAILED_STEPS+=("requirements.txt")
        fi
    else
        warn "No requirements.txt found at $REQUIREMENTS -- skipping."
    fi

    if "$VENV_PIP" install pywebview -q; then
        ok "Installed pywebview"
    else
        fail "pywebview failed to install."
        FAILED_STEPS+=("pywebview")
    fi

    # No longer using --system-site-packages (see note above), so the
    # GTK bindings pywebview needs on Linux have to be built directly
    # into the venv instead -- this is what the build tools/dev headers
    # installed above (gcc, pkg-config, libcairo/libgirepository-dev)
    # are for.
    if "$VENV_PIP" install pycairo PyGObject -q; then
        ok "Installed pycairo + PyGObject (GTK bindings, built for this venv)"
    else
        fail "pycairo/PyGObject failed to build -- the web UI won't be able to open a window."
        warn "Common cause: missing dev headers. Check gcc/pkg-config/libcairo2-dev/libgirepository-2.0-dev installed above."
        FAILED_STEPS+=("pycairo/PyGObject")
    fi

    if "$VENV_PIP" install playwright -q; then
        ok "Installed playwright"
        step "Downloading Chromium for Playwright (this part takes a minute)"
        if "$VENV_DIR/bin/playwright" install chromium; then
            ok "Chromium ready"
        else
            fail "Chromium download failed -- reservation booking won't work until this succeeds."
            FAILED_STEPS+=("playwright chromium")
        fi
    else
        fail "playwright failed to install."
        FAILED_STEPS+=("playwright")
    fi
fi

# ---------------------------------------------------------------------------
# 4. Desktop launcher -- a real, clickable icon that points HERE
# ---------------------------------------------------------------------------
step "Setting up the app launcher"

mkdir -p "$(dirname "$DESKTOP_FILE")"
mkdir -p "$(dirname "$LAUNCH_SCRIPT")"

cat > "$LAUNCH_SCRIPT" << EOF
#!/bin/bash
# Auto-generated by install.sh -- launches NaiTRO using its own venv.
cd "$PROJECT_DIR"
exec "$VENV_PY" "$PYTHON_ENTRY"
EOF
chmod +x "$LAUNCH_SCRIPT"
ok "Wrote launch script: $LAUNCH_SCRIPT"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=NaiTRO
Comment=Local PC voice assistant
Exec=$LAUNCH_SCRIPT
Icon=$ICON_PATH
Terminal=false
Categories=Utility;
EOF
chmod +x "$DESKTOP_FILE"
ok "Wrote desktop entry: $DESKTOP_FILE"

# Some desktop environments need this to pick up new .desktop files right away.
command -v update-desktop-database >/dev/null 2>&1 \
    && update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
step "Done"

if [ ${#FAILED_STEPS[@]} -eq 0 ]; then
    ok "Everything installed cleanly."
    echo -e "\n  NaiTRO should now show up in your applications menu."
    echo -e "  Or launch it directly with: ${c_bold}$LAUNCH_SCRIPT${c_reset}\n"
else
    warn "Finished, but these steps had problems: ${FAILED_STEPS[*]}"
    warn "Fix those and re-run ./install.sh -- it's safe to run again."
fi
