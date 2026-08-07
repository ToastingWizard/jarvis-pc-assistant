"""
app_launcher.py — Windows app resolution, icon extraction, and robust launching.

Provides:
- resolve_app(target): resolve bare name or path to a launchable entry
- extract_icon_data_uri(source, size): extract icon as base64 data URI PNG
- finalize_app_entry(name, entry): enrich a config entry with resolved paths + icon
- validate_apps(config): mark unavailable entries, fill missing display_names
- launch_windows(target, entry): robust Windows launch with multiple fallbacks

On non-Windows, functions are safe no-ops or basic file-existence checks.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import diagnostics
import difflib
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

ICON_SIZE = 48
_ICON_LOG = None  # set by callers via set_icon_log()


def set_icon_log(func):
    """Set a logger function for icon extraction diagnostics."""
    global _ICON_LOG
    _ICON_LOG = func


def _icon_log(msg):
    if _ICON_LOG:
        _ICON_LOG(msg)


def is_windows():
    return os.name == "nt"


def _normalize(name):
    """Lowercase, strip, remove non-alphanumeric except spaces."""
    text = name.strip().lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
#  .lnk resolution (Windows only)
# ---------------------------------------------------------------------------

def _resolve_shortcut(lnk_path):
    """Resolve a .lnk shortcut via WScript.Shell (dynamic dispatch).
    Returns dict with target, args, icon_file, icon_index, workdir, or None."""
    if not is_windows():
        return None
    if not os.path.isfile(lnk_path):
        return None
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception as exc:
        diagnostics.log(f"[app-launch] pythoncom.CoInitialize failed: {exc!r}")
    try:
        import win32com.client
        shell = win32com.client.dynamic.Dispatch("WScript.Shell")
        sc = shell.CreateShortcut(lnk_path)
        icon_file = ""
        icon_index = 0
        icon_loc = sc.IconLocation or ""
        if icon_loc:
            parts = icon_loc.split(",", 1)
            icon_file = parts[0].strip()
            icon_index = int(parts[1].strip()) if len(parts) > 1 else 0
        return {
            "target": sc.Targetpath or "",
            "args": sc.Arguments or "",
            "workdir": sc.WorkingDirectory or "",
            "icon_file": icon_file,
            "icon_index": icon_index,
        }
    except Exception as exc:
        diagnostics.log(f"[app-launch] shortcut resolve failed for '{lnk_path}': {exc!r}")
        return None


# ---------------------------------------------------------------------------
#  App Paths registry
# ---------------------------------------------------------------------------

def _get_app_paths():
    """Read Windows App Paths (HKLM + HKCU). Returns {exe_name: full_path}."""
    if not is_windows():
        return {}
    import winreg
    result = {}
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths") as key:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, name) as sub:
                            try:
                                val, _ = winreg.QueryValueEx(sub, "")
                                if val:
                                    val = os.path.expandvars(str(val))
                                    if os.path.isfile(val):
                                        result[name.lower()] = val
                            except Exception:
                                pass
                        i += 1
                    except OSError:
                        break
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
#  Start Menu scanning
# ---------------------------------------------------------------------------

def _scan_start_menu():
    """Scan Start Menu directories for .lnk shortcuts.
    Returns list of dicts with display_name, lnk_path, target, args,
    exe_path, icon_source, kind, workdir."""
    if not is_windows():
        return []
    lnk_dirs = []
    for var in ("%APPDATA%", "%PROGRAMDATA%"):
        base = os.path.expandvars(var)
        sm = os.path.join(base, r"Microsoft\Windows\Start Menu\Programs")
        if os.path.isdir(sm):
            lnk_dirs.append(sm)
    entries = []
    for root_dir in lnk_dirs:
        for dirpath, _, filenames in os.walk(root_dir):
            for fname in filenames:
                if not fname.lower().endswith(".lnk"):
                    continue
                lnk_name = os.path.splitext(fname)[0]
                if "uninstall" in lnk_name.lower():
                    continue
                full = os.path.join(dirpath, fname)
                resolved = _resolve_shortcut(full)
                if not resolved:
                    continue
                target = resolved["target"]
                if not target:
                    # UWP / shell: apps — keep the .lnk as launch target
                    entries.append({
                        "display_name": lnk_name,
                        "lnk_path": full,
                        "target": full,
                        "args": resolved["args"],
                        "exe_path": "",
                        "icon_source": "",
                        "kind": "shortcut",
                        "workdir": resolved["workdir"],
                    })
                    continue
                target = os.path.expandvars(target)
                # If resolved target doesn't exist, fall back to .lnk
                if not os.path.isfile(target):
                    target = full
                icon_source = resolved["icon_file"]
                if icon_source:
                    icon_source = os.path.expandvars(icon_source)
                    if not os.path.isfile(icon_source):
                        icon_source = target if os.path.isfile(target) else ""
                else:
                    icon_source = target if os.path.isfile(target) else ""
                entries.append({
                    "display_name": lnk_name,
                    "lnk_path": full,
                    "target": target,
                    "args": resolved["args"],
                    "exe_path": os.path.expandvars(resolved["target"]),
                    "icon_source": icon_source,
                    "kind": "shortcut",
                    "workdir": resolved["workdir"],
                })
    return entries


# ---------------------------------------------------------------------------
#  AppX / UWP discovery (via Get-StartApps, cached to disk)
# ---------------------------------------------------------------------------

def _get_appx_cache_path():
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(local) / "NaiTRO"
    d.mkdir(parents=True, exist_ok=True)
    return d / "appx-cache.json"


_appx_cache = None


def _get_appx_discovered():
    """Lazy-load AppX/UWP apps.  Uses a 24-hour disk cache so the
    slow PowerShell call (~12 s) only runs once per day."""
    global _appx_cache
    if _appx_cache is not None:
        return _appx_cache

    if not is_windows():
        _appx_cache = {}
        return _appx_cache

    cache_path = _get_appx_cache_path()

    # Try disk cache first (skip if older than 24 h)
    try:
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < 86400:
                with open(cache_path, encoding="utf-8") as f:
                    _appx_cache = json.load(f)
                return _appx_cache
    except Exception:
        pass

    # Cache miss — run PowerShell
    try:
        import subprocess as _sp
        with diagnostics.timing("_get_appx_discovered (PowerShell Get-StartApps)"):
            r = _sp.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-StartApps | ForEach-Object { "
                 "Write-Output ($_.Name + '|' + $_.AppID) }"],
                capture_output=True, text=True, timeout=8,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        result = {}
        for line in r.stdout.strip().split("\n"):
            if "|" not in line:
                continue
            name, appid = line.split("|", 1)
            name, appid = name.strip(), appid.strip()
            if not name or not appid:
                continue
            if "uninstall" in name.lower():
                continue
            target = f"shell:AppsFolder\\{appid}"
            key = _normalize(name)
            if key not in result:
                result[key] = {
                    "display_name": name,
                    "lnk_path": "",
                    "target": target,
                    "args": "",
                    "exe_path": "",
                    "icon_source": target,
                    "kind": "appx",
                    "workdir": "",
                }
        _appx_cache = result
        try:
            cache_path.write_text(json.dumps(result), encoding="utf-8")
        except Exception:
            pass
    except Exception:
        _appx_cache = {}

    return _appx_cache


# ---------------------------------------------------------------------------
#  Discovered apps cache + resolution
# ---------------------------------------------------------------------------

_discovered_cache = None


def _get_discovered():
    """Lazy-build normalized-name -> discovery entry map. Cached per process."""
    global _discovered_cache
    if _discovered_cache is not None:
        return _discovered_cache
    discovered = {}
    if is_windows():
        # Start Menu first (richer: has display name, lnk path, args)
        for entry in _scan_start_menu():
            key = _normalize(entry["display_name"])
            if key not in discovered:
                discovered[key] = entry
        # App Paths: fill gaps
        app_paths = _get_app_paths()
        for exe_name, exe_path in app_paths.items():
            key = _normalize(os.path.splitext(exe_name)[0])
            if key not in discovered:
                discovered[key] = {
                    "display_name": os.path.splitext(exe_name)[0],
                    "lnk_path": "",
                    "target": exe_path,
                    "args": "",
                    "exe_path": exe_path,
                    "icon_source": exe_path,
                    "kind": "exe",
                    "workdir": "",
                }
    _discovered_cache = discovered
    return discovered


def discover_installed_apps():
    """Public: returns the full discovered apps dict (normalized_name -> entry)."""
    return _get_discovered()


def resolve_app(target):
    """Resolve a bare app name or path to a launchable entry.
    Returns dict with: display_name, launch, exe_path, icon_source, kind,
    available, args, lnk_path. None if nothing found."""
    if not target:
        return None
    target = target.strip()

    # 1. Full path that exists
    expanded = os.path.expandvars(os.path.expanduser(target))
    if os.path.isfile(expanded):
        return {
            "display_name": Path(target).stem,
            "launch": expanded,
            "exe_path": expanded,
            "icon_source": expanded,
            "kind": "shortcut" if target.lower().endswith(".lnk") else "exe",
            "available": True,
            "args": "",
            "lnk_path": expanded if target.lower().endswith(".lnk") else "",
        }

    # 1b. shell: URIs (AppX / UWP) — e.g. shell:AppsFolder\AppID.
    #     These aren't filesystem paths; the shell resolves them.
    if target.lower().startswith("shell:"):
        return {
            "display_name": Path(target).stem or target,
            "launch": target,
            "exe_path": "",
            "icon_source": target,
            "kind": "appx",
            "available": True,
            "args": "",
            "lnk_path": "",
        }

    if not is_windows():
        return None

    # 2. Search Start Menu + App Paths
    key = _normalize(target)
    discovered = _get_discovered()

    def _to_result(entry):
        launch = entry.get("lnk_path") or entry.get("target", "")
        return {
            "display_name": entry.get("display_name", target),
            "launch": launch,
            "exe_path": entry.get("exe_path", ""),
            "icon_source": entry.get("icon_source", entry.get("exe_path", "")),
            "kind": entry.get("kind", "exe"),
            "available": bool(launch),
            "args": entry.get("args", ""),
            "lnk_path": entry.get("lnk_path", ""),
        }

    # 2a. Exact match
    if key in discovered:
        return _to_result(discovered[key])

    # 2b. Prefix / substring match
    # Handles: "obs" -> "obs studio 64bit", "zoom" -> "zoom workplace",
    #          "google chrome" -> "google chrome" (exact), etc.
    best = None
    best_score = 0
    for disc_key, entry in discovered.items():
        if disc_key.startswith(key):
            # Query is a prefix of discovered name (e.g. "obs" in "obs studio")
            # High confidence even for short queries
            if len(key) >= 3 or key == disc_key:
                score = 0.8 + 0.2 * (len(key) / max(len(disc_key), 1))
            else:
                continue
        elif key.startswith(disc_key):
            # Discovered name is a prefix of query (e.g. "steam" in "steam deck")
            score = 0.6 + 0.3 * (len(disc_key) / max(len(key), 1))
        elif disc_key in key:
            # Discovered key is a substring of query
            score = len(disc_key) / max(len(key), 1)
        elif key in disc_key:
            # Query is a substring of discovered key
            score = len(key) / max(len(disc_key), 1) * 0.5
        else:
            continue
        if score > best_score:
            best_score = score
            best = entry
    if best and best_score >= 0.5:
        return _to_result(best)

    # 2c. Fuzzy match (difflib) — high cutoff so we only match real typos,
    # never weakly-related multi-word phrases (e.g. "gaming mode" must not
    # match "M724 Gaming Mouse").
    matches = difflib.get_close_matches(
        key, discovered.keys(), n=1, cutoff=0.75
    )
    if matches:
        return _to_result(discovered[matches[0]])

    # 3. shutil.which (checks PATH)
    which_result = shutil.which(target)
    if which_result:
        return {
            "display_name": Path(target).stem,
            "launch": which_result,
            "exe_path": which_result,
            "icon_source": which_result,
            "kind": "exe",
            "available": True,
            "args": "",
            "lnk_path": "",
        }

    # 4. AppX / UWP apps (Get-StartApps, cached to disk — first call is
    #    slow ~12 s, subsequent calls load from JSON in <10 ms)
    appx = _get_appx_discovered()

    def _to_appx(entry):
        launch = entry.get("lnk_path") or entry.get("target", "")
        return {
            "display_name": entry.get("display_name", target),
            "launch": launch,
            "exe_path": entry.get("exe_path", ""),
            "icon_source": entry.get("icon_source", launch),
            "kind": entry.get("kind", "appx"),
            "available": bool(launch),
            "args": entry.get("args", ""),
            "lnk_path": entry.get("lnk_path", ""),
        }

    # 4a. Exact
    if key in appx:
        return _to_appx(appx[key])

    # 4b. Substring / prefix (same logic as step 2b)
    best_ax = None
    best_ax_score = 0
    for disc_key, entry in appx.items():
        if disc_key.startswith(key) and len(key) >= 3:
            score = 0.8 + 0.2 * (len(key) / max(len(disc_key), 1))
        elif key.startswith(disc_key):
            score = 0.6 + 0.3 * (len(disc_key) / max(len(key), 1))
        elif disc_key in key:
            score = len(disc_key) / max(len(key), 1)
        elif key in disc_key:
            score = len(key) / max(len(disc_key), 1) * 0.5
        else:
            continue
        if score > best_ax_score:
            best_ax_score = score
            best_ax = entry
    if best_ax and best_ax_score >= 0.5:
        return _to_appx(best_ax)

    # 4c. Fuzzy
    matches_ax = difflib.get_close_matches(
        key, appx.keys(), n=1, cutoff=0.75
    )
    if matches_ax:
        return _to_appx(appx[matches_ax[0]])

    return None


# ---------------------------------------------------------------------------
#  Icon extraction + caching (Windows, pure ctypes + Pillow)
# ---------------------------------------------------------------------------

def _get_icon_cache_dir():
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(local) / "NaiTRO" / "icon-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _hash_path(path):
    return hashlib.md5(path.lower().encode("utf-8")).hexdigest()[:12]


def extract_icon_data_uri(icon_source, size=None):
    """Extract icon as base64 data URI PNG. Returns None on failure.

    For shell: URIs (AppX/UWP apps), SHGetFileInfoW returns a generic
    white document icon.  When that happens we fall back to locating the
    package's actual logo PNG on disk via PowerShell (cached per session
    and to a JSON file so repeated launches are instant).
    """
    size = size or ICON_SIZE
    if not is_windows() or not icon_source:
        return None
    diagnostics.lookup("icon", "icon source", str(icon_source))
    cache_dir = _get_icon_cache_dir()
    cache_key = _hash_path(icon_source) + f"_{size}"
    cache_file = cache_dir / f"{cache_key}.png"
    if cache_file.exists() and cache_file.stat().st_size > 0:
        diagnostics.log(f"[icon] cache hit: {cache_file.name} for '{icon_source}'")
        return _file_to_data_uri(cache_file)
    diagnostics.log(f"[icon] cache miss: extracting '{icon_source}'")
    try:
        hIcon = _extract_hicon(icon_source)
        if not hIcon:
            _icon_log(f"Icon extraction failed: SHGetFileInfoW returned no HICON for '{icon_source}'")
            # Try AppX logo fallback for shell: URIs
            if icon_source.lower().startswith("shell:"):
                img = _find_appx_logo(icon_source, size)
                if img:
                    img.save(str(cache_file), "PNG")
                    return _file_to_data_uri(cache_file)
            return None
        img = _hicon_to_pil(hIcon, size)
        ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(hIcon))
        if img is None:
            _icon_log(f"Icon extraction failed: HICON-to-PIL conversion returned None for '{icon_source}'")
            return None
        # Detect generic white document icon (AppX fallback from SHGFI):
        # it has very few distinct colours (~7) and the center pixel is
        # near-white.  Real app icons have far more variety.
        if _is_generic_icon(img):
            _icon_log(f"SHGFI returned generic placeholder icon for '{icon_source}', trying AppX logo fallback")
            img.close()
            if icon_source.lower().startswith("shell:"):
                img = _find_appx_logo(icon_source, size)
                if img:
                    img.save(str(cache_file), "PNG")
                    return _file_to_data_uri(cache_file)
            # Non-AppX path that still produced a generic icon — log it
            _icon_log(f"No AppX logo fallback available for '{icon_source}'")
            return None
        img.save(str(cache_file), "PNG")
        return _file_to_data_uri(cache_file)
    except Exception as exc:
        _icon_log(f"Icon extraction exception for '{icon_source}': {exc}")
        return None


# ---------------------------------------------------------------------------
#  Generic (placeholder) icon detection
# ---------------------------------------------------------------------------

# Threshold: the generic white-document icon extracted by SHGFI for
# unknown / AppX paths compresses to ~300-400 bytes as a 48x48 PNG.
# Real app icons are typically 1-5 KB.  If the stored icon's raw PNG
# is under this threshold, treat it as a stale placeholder and
# re-extract.
_STALE_ICON_RAW_BYTES = 500


def _is_stale_icon(data_uri: str) -> bool:
    """Return True if *data_uri* looks like the tiny generic placeholder.

    Decodes the base64 payload and checks its byte length.  This avoids
    re-extracting icons for every app on every startup — only the tiny
    placeholders (< 500 bytes) trigger re-extraction.
    """
    try:
        import base64 as _b64
        b64 = data_uri.split(",", 1)[1] if "," in data_uri else ""
        raw = _b64.b64decode(b64)
        return len(raw) < _STALE_ICON_RAW_BYTES
    except Exception:
        return False


def _is_generic_icon(img):
    """Return True if *img* looks like the generic white document icon
    that SHGFI returns for unknown/unsupported paths.

    The placeholder is 48×48 RGBA with:
      - ≤ 20 unique visible colours (real icons have 50-400+)
      - center pixel in the near-white range (R,G,B all > 200)
    """
    try:
        px = img.load()
        w, h = img.size
        cx, cy = w // 2, h // 2
        r, g, b, a = px[cx, cy]
        if a < 50 or not (r > 200 and g > 200 and b > 200):
            return False
        # Count distinct visible colours — cheap sampling
        colours = set()
        step = max(1, w // 12)
        for x in range(0, w, step):
            for y in range(0, h, step):
                pr, pg, pb, pa = px[x, y]
                if pa > 50:
                    colours.add((pr, pg, pb))
        return len(colours) <= 20
    except Exception:
        return False


# ---------------------------------------------------------------------------
#  AppX / UWP logo extraction (PowerShell + cached JSON)
# ---------------------------------------------------------------------------

_appx_logo_cache = None  # {app_id_lower: logo_path_or_None}


def _get_appx_logo_cache_path():
    local = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = Path(local) / "NaiTRO"
    d.mkdir(parents=True, exist_ok=True)
    return d / "appx-logo-cache.json"


def _load_appx_logo_cache():
    global _appx_logo_cache
    if _appx_logo_cache is not None:
        return _appx_logo_cache
    _appx_logo_cache = {}
    try:
        cache_path = _get_appx_logo_cache_path()
        if cache_path.exists():
            age = time.time() - cache_path.stat().st_mtime
            if age < 86400:  # 24-hour TTL
                _appx_logo_cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return _appx_logo_cache


def _save_appx_logo_cache():
    try:
        cache_path = _get_appx_logo_cache_path()
        cache_path.write_text(json.dumps(_appx_logo_cache), encoding="utf-8")
    except Exception:
        pass


def _find_appx_logo(shell_uri, size=ICON_SIZE):
    """Locate the real logo for an AppX/UWP app given its shell: URI.

    1. Extract the AppID from the URI (e.g.
       ``shell:AppsFolder\\PkgId!App`` → ``PkgId``).
    2. Use ``Get-AppxPackage`` (PowerShell) to find the package's
       ``InstallLocation``.
    3. Scan that directory for ``Logo.png`` / ``SmallLogo.png``.
    4. Resize to *size* and return a PIL Image, or ``None``.
    """
    from PIL import Image as _PilImage

    app_id = _parse_appx_id(shell_uri)
    if not app_id:
        _icon_log(f"AppX logo: could not parse AppID from '{shell_uri}'")
        return None

    cache = _load_appx_logo_cache()
    cache_key = app_id.lower()
    if cache_key in cache:
        cached_path = cache[cache_key]
        if cached_path and os.path.isfile(cached_path):
            try:
                return _PilImage.open(cached_path).convert("RGBA").resize(
                    (size, size), _PilImage.LANCZOS
                )
            except Exception:
                pass
        # Cached as None or file missing → retry lookup
    try:
        import subprocess as _sp
        # Get-AppxPackage needs the package family name or partial name.
        # We have the full AppID (e.g. Microsoft.MinecraftUWP_…!Game);
        # extract the package name before the underscore.
        pkg_name = app_id.split("_")[0] if "_" in app_id else app_id
        with diagnostics.timing(f"_find_appx_logo PowerShell for '{pkg_name}'"):
            r = _sp.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    (
                        f"Get-AppxPackage -Name '*{pkg_name}*' "
                        "| Select-Object -ExpandProperty InstallLocation "
                        "| Select-Object -First 1"
                    ),
                ],
                capture_output=True, text=True, timeout=15,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
        install_dir = (r.stdout or "").strip()
        if not install_dir or not os.path.isdir(install_dir):
            _icon_log(
                f"AppX logo: PowerShell returned no install dir for "
                f"'{app_id}' (pkg='{pkg_name}'): {r.stdout.strip()!r}"
            )
            cache[cache_key] = None
            _save_appx_logo_cache()
            return None
        # Search for logo files — prefer Logo.png > SmallLogo.png > StoreLogo.png
        # UWP packages store icons in root OR in Assets\ subdirectory.
        logo_names = ("Logo.png", "SmallLogo.png", "StoreLogo.png",
                      "Wide310x150Logo.png", "Square44x44Logo.png",
                      "Square150x150Logo.png")
        logo_path = None
        # Check root first, then common subdirectories (Assets/, Images/)
        search_dirs = [install_dir,
                       os.path.join(install_dir, "Assets"),
                       os.path.join(install_dir, "Images")]
        for sdir in search_dirs:
            if logo_path:
                break
            for name in logo_names:
                candidate = os.path.join(sdir, name)
                if os.path.isfile(candidate) and os.path.getsize(candidate) > 100:
                    logo_path = candidate
                    break
        if not logo_path:
            # Broaden search: recursively find small-ish logo PNGs
            # (avoid splash screens and huge tile images)
            import glob as _glob
            for pattern in ("*ogo*.png", "*quare44*Logo*.png", "*StoreLogo*"):
                for sdir in search_dirs:
                    matches = _glob.glob(os.path.join(sdir, pattern))
                    matches = [m for m in matches if 500 < os.path.getsize(m) < 50000]
                    if matches:
                        logo_path = min(matches, key=lambda p: os.path.getsize(p))
                        break
                if logo_path:
                    break
        if logo_path:
            cache[cache_key] = logo_path
            _save_appx_logo_cache()
            _icon_log(f"AppX logo: found '{logo_path}' for app '{app_id}'")
            return _PilImage.open(logo_path).convert("RGBA").resize(
                (size, size), _PilImage.LANCZOS
            )
        _icon_log(f"AppX logo: no logo PNG found in '{install_dir}' for app '{app_id}'")
        cache[cache_key] = None
        _save_appx_logo_cache()
    except Exception as exc:
        _icon_log(f"AppX logo: PowerShell lookup failed for '{app_id}': {exc}")
    return None


def _parse_appx_id(shell_uri):
    """Extract the AppID from a shell:AppsFolder URI.

    ``shell:AppsFolder\\Microsoft.MinecraftUWP_8wekyb3d8bbwe!Game``
    → ``Microsoft.MinecraftUWP_8wekyb3d8bbwe!Game``
    """
    uri = shell_uri.strip()
    # Accept both "shell:AppsFolder\..." and "shell:AppsFolder\\..."
    marker = "AppsFolder\\"
    idx = uri.lower().find(marker.lower())
    if idx == -1:
        marker = "AppsFolder\\\\"
        idx = uri.lower().find(marker.lower())
    if idx == -1:
        return None
    return uri[idx + len(marker):]


def _file_to_data_uri(path):
    import base64
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


class _SHFILEINFO(ctypes.Structure):
    _fields_ = [
        ("hIcon", ctypes.c_void_p),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wt.DWORD),
        ("szDisplayName", wt.WCHAR * 260),
        ("szTypeName", wt.WCHAR * 80),
    ]


# ------------------------------------------------------------------
#  GDI / Shell restype fixes for 64-bit Python
#
#  ctypes defaults all return types to c_int (32-bit).  On 64-bit
#  Windows, handles (HDC, HBITMAP, HICON, HGDIOBJ) are pointer-
#  sized — 64 bits.  Without restype = c_void_p the high bits are
#  silently truncated, producing invalid handles that can cause
#  access violations in later GDI calls (especially string_at when
#  reading from a garbage DIB pointer).
# ------------------------------------------------------------------

def _ensure_gdi_restypes():
    """Set proper return types for Windows GDI / Shell functions.

    Safe to call multiple times — idempotent.  Called lazily from
    _extract_hicon / _hicon_to_pil on first use.
    """
    u32 = ctypes.windll.user32
    g32 = ctypes.windll.gdi32
    s32 = ctypes.windll.shell32
    _c = ctypes.c_void_p
    _i = ctypes.c_int

    # Shell
    s32.SHGetFileInfoW.restype = _c
    # User32
    u32.GetDC.restype = _c
    u32.DrawIconEx.restype = _i
    u32.ReleaseDC.restype = _i
    u32.DestroyIcon.restype = _i
    # Gdi32
    g32.CreateCompatibleDC.restype = _c
    g32.CreateDIBSection.restype = _c
    g32.SelectObject.restype = _c
    g32.DeleteObject.restype = _i
    g32.DeleteDC.restype = _i
    g32.PatBlt.restype = _i
    g32.GdiFlush.restype = _i


_gdi_restypes_set = False


def _extract_hicon(path):
    global _gdi_restypes_set
    if not _gdi_restypes_set:
        _ensure_gdi_restypes()
        _gdi_restypes_set = True
    shfi = _SHFILEINFO()
    exists = os.path.exists(path)
    flags = 0x100 | 0x0  # SHGFI_ICON | SHGFI_LARGEICON
    if not exists:
        flags |= 0x10  # SHGFI_USEFILEATTRIBUTES
    res = ctypes.windll.shell32.SHGetFileInfoW(
        path, 0, ctypes.byref(shfi), ctypes.sizeof(shfi), flags
    )
    if not res or not shfi.hIcon:
        return None
    return shfi.hIcon


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", ctypes.c_byte * 12),
    ]


def _hicon_to_pil(hIcon, size=48):
    """Draw HICON into 32bpp DIB section -> read pixels -> PIL RGBA Image."""
    from PIL import Image

    _vp = ctypes.c_void_p  # shorthand for pointer cast
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    hdc = _vp(user32.GetDC(0))
    try:
        hdcMem = _vp(gdi32.CreateCompatibleDC(hdc))
        if not hdcMem:
            return None
        try:
            bmi = _BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = size
            bmi.bmiHeader.biHeight = -size  # top-down
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bmi.bmiHeader.biCompression = 0  # BI_RGB
            bits = ctypes.c_void_p()
            hbmp = _vp(gdi32.CreateDIBSection(
                hdcMem, ctypes.byref(bmi), 0, ctypes.byref(bits), 0, 0
            ))
            if not hbmp or not bits:
                return None
            try:
                old = _vp(gdi32.SelectObject(hdcMem, hbmp))
                gdi32.PatBlt(hdcMem, 0, 0, size, size, 0x00000042)  # clear
                user32.DrawIconEx(hdcMem, 0, 0, _vp(hIcon), size, size, 0, 0, 0x0003)  # DI_NORMAL
                gdi32.GdiFlush()
                gdi32.SelectObject(hdcMem, old)
                raw = ctypes.string_at(bits, size * size * 4)
                img = Image.frombuffer("RGBA", (size, size), raw, "raw", "BGRA", 0, 1)
                return img
            finally:
                gdi32.DeleteObject(hbmp)
        finally:
            gdi32.DeleteDC(hdcMem)
    finally:
        user32.ReleaseDC(0, hdc)


# ---------------------------------------------------------------------------
#  Robust Windows launch
# ---------------------------------------------------------------------------

def launch_windows(target, entry=None, log=None):
    """Launch app on Windows. Returns (ok, message).
    entry: optional resolved dict from resolve_app() with 'launch', 'args'.
    If entry doesn't have 'launch', the target is resolved on the fly."""
    log = log or (lambda m: None)
    target = os.path.expandvars(os.path.expanduser(str(target)))

    if entry:
        launch_path = entry.get("launch", "")
        args = entry.get("args", "")
        if not launch_path:
            # Entry from config may lack 'launch' (old format) — resolve
            resolved = resolve_app(entry.get("target", target))
            if resolved:
                launch_path = resolved.get("launch", target)
                args = resolved.get("args", "")
            else:
                launch_path = target
    else:
        launch_path = target
        args = ""

    # .lnk / .url — shell handles them natively (carries args)
    if launch_path.lower().endswith((".lnk", ".url", ".msc")):
        return _shell_open(launch_path, log)

    # URL / protocol
    if (re.match(r"^[a-z][a-z0-9+.-]*://", launch_path, re.IGNORECASE)
            or launch_path.startswith(("shell:", "ms-", "spotify:", "ms-settings:"))):
        return _shell_open(launch_path, log)

    # Existing file
    if os.path.isfile(launch_path):
        if args:
            return _shell_execute_with_args(launch_path, args, log)
        return _shell_open(launch_path, log)

    # Bare command: try resolving
    if not entry:
        resolved = resolve_app(launch_path)
        if resolved:
            return launch_windows(target, entry=resolved, log=log)
        log(f"App launcher: '{target}' not in Start Menu/App Paths")

    # Last resort: ShellExecute / cmd start
    return _shell_open(launch_path, log, args=args)


def _shell_open(path, log, args=""):
    """Open via Windows shell. Returns (ok, message)."""
    try:
        os.startfile(path)
        return True, path
    except OSError as e:
        # WinError 1223 = ERROR_OPERATION_ABORTED — the system started
        # the launch (e.g. showed a UAC prompt) but the user cancelled it
        # in the interactive dialog.  In real use the user clicks Yes,
        # so we treat this as success rather than a missing-app error.
        if getattr(e, "winerror", None) == 1223:
            log(f"App launcher: '{path}' launched (UAC / confirmation prompt shown)")
            return True, path
        log(f"App launcher: startfile failed for '{path}': {e}")
    except Exception as e1:
        log(f"App launcher: startfile failed for '{path}': {e1}")
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "open", path, args or None, None, 1
        )
        if ret > 32:
            return True, path
        # ShellExecuteW error codes: 2 = FILE_NOT_FOUND, 3 = PATH_NOT_FOUND,
        # 5 = ACCESS_DENIED, 31 = NO_ASSOCIATION
        reason = {
            2: "file not found", 3: "path not found", 5: "access denied",
            31: "no file association",
        }.get(ret, f"error code {ret}")
        log(f"App launcher: ShellExecuteW failed ({reason}) for '{path}'")
    except Exception as e2:
        log(f"App launcher: ShellExecuteW failed: {e2}")
    return False, f"Could not open: {path}"


def _shell_execute_with_args(exe, args, log):
    """Launch an exe with arguments via ShellExecuteW."""
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "open", exe, args, None, 1
        )
        if ret > 32:
            return True, exe
        log(f"App launcher: ShellExecuteW with args returned {ret}")
    except Exception as e:
        log(f"App launcher: ShellExecuteW with args failed: {e}")
    return _shell_open(exe, log)


# ---------------------------------------------------------------------------
#  Entry normalization / validation
# ---------------------------------------------------------------------------

def finalize_app_entry(name, entry, log=None):
    """Enrich a config app entry with resolved paths + icon.
    Mutates entry in-place. Returns the entry."""
    log = log or (lambda m: None)
    target = entry.get("target", "")

    if not target:
        entry["display_name"] = entry.get("display_name") or name.title()
        entry["available"] = False
        return entry

    if is_windows():
        resolved = resolve_app(target)
        if resolved:
            entry["display_name"] = resolved.get("display_name", name.title())
            # Use the "launch" field — it's always the correct path
            # (.lnk, exe, shell:AppsFolder, etc.)
            new_target = resolved.get("launch") or target
            entry["target"] = new_target
            kind = resolved.get("kind", "")
            if kind == "shortcut":
                entry["type"] = "shortcut"
            elif kind == "exe":
                entry["type"] = "exe"
            elif kind == "appx":
                entry["type"] = "appx"
            exe = resolved.get("exe_path", "")
            if exe:
                entry["exe_path"] = exe
            entry["available"] = True
            # Extract icon only if not already cached in entry
            if not entry.get("icon"):
                icon_source = resolved.get("icon_source", entry.get("exe_path", ""))
                if icon_source:
                    data_uri = extract_icon_data_uri(icon_source)
                    if data_uri:
                        entry["icon"] = data_uri
        else:
            expanded = os.path.expandvars(os.path.expanduser(target))
            entry["display_name"] = entry.get("display_name") or name.title()
            # Bare commands may resolve via ShellExecute (App Paths, PATH,
            # AppX). Check file existence, shutil.which, then resolve_app.
            first_word = target.split()[0]
            entry["available"] = (
                os.path.isfile(expanded)
                or bool(shutil.which(first_word))
            )
            if not entry["available"]:
                resolved2 = resolve_app(target)
                entry["available"] = (
                    resolved2 is not None
                    and resolved2.get("available", False)
                )
    else:
        expanded = os.path.expandvars(os.path.expanduser(target))
        entry["display_name"] = entry.get("display_name") or name.title()
        first_word = target.split()[0]
        entry["available"] = (
            os.path.isfile(expanded) or bool(shutil.which(first_word))
        )

    return entry


def validate_apps(config, log=None):
    """Validate app entries: fill missing display_names, mark unavailable,
    extract icons for available apps that don't have one yet.
    Returns True if any entry was modified."""
    log = log or (lambda m: None)
    apps = config.get("apps", {})
    modified = False
    for name, entry in list(apps.items()):
        if not isinstance(entry, dict):
            apps[name] = {"type": "command", "target": str(entry)}
            entry = apps[name]
            modified = True
        if not entry.get("display_name"):
            entry["display_name"] = name.title()
            modified = True
        target = entry.get("target", "")
        if target:
            was_avail = entry.get("available")
            expanded = os.path.expandvars(os.path.expanduser(target))
            resolved = None
            if is_windows():
                if entry.get("type") in ("exe", "shortcut"):
                    # Real filesystem paths — .lnk / .exe must exist
                    entry["available"] = os.path.isfile(expanded)
                elif entry.get("type") == "appx":
                    # shell:AppsFolder URIs — resolve via AppX cache
                    resolved = resolve_app(target)
                    entry["available"] = (
                        resolved is not None
                        and resolved.get("available", False)
                    )
                else:
                    # For commands: check file, shutil.which, then Start Menu
                    first_word = target.split()[0]
                    entry["available"] = (
                        os.path.isfile(expanded)
                        or bool(shutil.which(first_word))
                    )
                    if not entry["available"]:
                        resolved = resolve_app(target)
                        entry["available"] = (
                            resolved is not None
                            and resolved.get("available", False)
                        )
            else:
                entry["available"] = (
                    os.path.isfile(expanded) or bool(shutil.which(target))
                )
            # Upgrade bare-command entries to their resolved launch path so
            # the config is self-contained (no re-resolution on each launch).
            if (entry["available"] and is_windows()
                    and entry.get("type") in ("command", "path")):
                resolved_up = resolved or resolve_app(target)
                if resolved_up:
                    launch = resolved_up.get("launch", "")
                    kind = resolved_up.get("kind", "")
                    if (launch and launch != target
                            and not os.path.isabs(target)):
                        entry["target"] = launch
                        if kind == "shortcut":
                            entry["type"] = "shortcut"
                        elif kind == "exe":
                            entry["type"] = "exe"
                        elif kind == "appx":
                            entry["type"] = "appx"
                        exe = resolved_up.get("exe_path", "")
                        if exe:
                            entry["exe_path"] = exe
                        modified = True
            if was_avail is not None and was_avail != entry.get("available"):
                if not entry.get("available"):
                    log(f"App '{name}' marked unavailable (target not found)")
                modified = True

            # Extract icon for available apps that don't have one yet,
            # OR re-extract if the existing icon is the tiny generic
            # white-document placeholder (typically < 500 bytes raw PNG).
            need_icon = entry.get("available") and is_windows() and (
                not entry.get("icon") or _is_stale_icon(entry.get("icon", ""))
            )
            if need_icon:
                icon_source = entry.get("exe_path", "")
                if not icon_source:
                    if resolved is None:
                        resolved = resolve_app(target)
                    if resolved:
                        icon_source = resolved.get("icon_source", "")
                if not icon_source and os.path.isfile(expanded):
                    icon_source = expanded
                if icon_source:
                    try:
                        data_uri = extract_icon_data_uri(icon_source)
                        if data_uri:
                            entry["icon"] = data_uri
                            modified = True
                    except Exception as exc:
                        _icon_log(f"validate_apps: icon extraction failed for '{name}' ({icon_source}): {exc}")
        else:
            if entry.get("available") is not False:
                entry["available"] = False
                modified = True
    available = sum(
        1 for e in apps.values()
        if isinstance(e, dict) and e.get("available")
    )
    diagnostics.log(
        f"[app-launch] validate_apps: {len(apps)} app(s) — "
        f"{available} available, {len(apps) - available} unavailable, "
        f"modified={modified}"
    )
    return modified
