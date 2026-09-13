"""Hard-coded protection rules + content sniffing."""

import os
import re
from pathlib import Path
import glob

from .config import HOME

# ---------------------------------------------------------------- folders
GAME_DIRS = [
    f"{HOME}/.steam",
    f"{HOME}/.local/share/Steam",
    f"{HOME}/.local/share/lutris",
    f"{HOME}/.local/share/heroic",
    f"{HOME}/.config/heroic",
    f"{HOME}/.wine",
    f"{HOME}/.local/share/wineprefixes",
    f"{HOME}/.local/share/PrismLauncher",
    f"{HOME}/.config/PrismLauncher",
    f"{HOME}/PrismLauncher",
    f"{HOME}/.var/app/org.prismlauncher.PrismLauncher",
    f"{HOME}/.local/share/multimc",
    f"{HOME}/.local/share/PolyMC",
    f"{HOME}/.local/share/multimc5",
    f"{HOME}/.minecraft",
    f"{HOME}/.var/app/com.mojang.Minecraft",
    "/usr/share/steam",
    "/usr/games",
]

GAME_PATH_HINTS = [
    "prismlauncher",
    "multimc",
    "polymc",
    "minecraft",
    "steamapps",
    "lutris",
    "heroic",
    "wineprefix",
    "/steam/",
    "/games/",
    "/instances/",
    "/minecraft/mods/",
    "/minecraft/saves/",
]

GAME_EXTS = {
    ".jar",
    ".class",
    ".java",
    ".nbt",
    ".mca",
    ".mcr",
    ".dat_old",
    ".pak",
    ".vpk",
    ".bsa",
    ".esm",
    ".esp",
    ".bsl",
    ".sav",
    ".rom",
    ".iso",
    ".cue",
    ".gba",
    ".nds",
    ".3ds",
    ".wad",
    ".pk3",
    ".pk4",
    ".uasset",
    ".umap",
    ".unity3d",
    ".asset",
    ".bundle",
    ".resources",
}

# ------------------------------------------------------------------ paths
PSEUDO_FS = (
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/snap",
    "/lost+found",
    "/boot/efi",
    "/var/lib/docker",
    "/var/lib/snapd/snaps",
)

SYSTEM_PROTECTED = (
    "/usr",
    "/etc",
    "/opt",
    "/boot",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/var/lib",
    "/var/log",
    "/var/spool",
    "/var/backups",
    "/var/mail",
)


def in_pseudo_fs(p):
    p = str(p)
    for skip in PSEUDO_FS:
        if p == skip or p.startswith(skip + "/"):
            return True
    return False


def in_system_path(p):
    p = str(p)
    for skip in SYSTEM_PROTECTED:
        if p == skip or p.startswith(skip + "/"):
            return True
    return False


def expand_user_path(p):
    """Expand `~` using HOME (which is the *user's* home, not root's)."""
    if p.startswith("~"):
        rest = p[1:].lstrip("/\\")
        return os.path.join(HOME, rest) if rest else HOME
    return os.path.abspath(p)


# -------------------------------------------------------- content sniffing
SNIFF_BYTES = 4096

CRITICAL_EXTS = {
    ".kdbx",
    ".wallet",
    ".key",
    ".pem",
    ".crt",
    ".cer",
    ".p12",
    ".pfx",
    ".gpg",
    ".asc",
    ".pgp",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".sql",
    ".rdb",
    ".bak",
}

CRITICAL_NAMES = {
    "wallet.dat",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    "authorized_keys",
    ".env",
    ".pgpass",
    ".netrc",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Makefile",
    "CMakeLists.txt",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "composer.json",
}


def sniff_file_kind(path):
    """
    Read first SNIFF_BYTES and return (kind, preview).
    kinds:
      'unreadable', 'empty',
      'binary-exec', 'binary-archive', 'binary-magic', 'binary',
      'text-code', 'text-doc', 'text-config', 'text-log', 'text-data'
    """
    path = Path(path)  # defensive — accept str or Path

    if path.name.lower() in CRITICAL_NAMES or path.suffix.lower() in CRITICAL_EXTS:
        return ("text-data", "critical name/extension")

    try:
        with open(path, "rb") as f:
            head = f.read(SNIFF_BYTES)
    except (PermissionError, OSError):
        return ("unreadable", "")

    if not head:
        return ("empty", "")

    if b"\x00" in head[:512]:
        if head.startswith(b"\x7fELF"):
            return ("binary-exec", "ELF executable")
        if head.startswith(b"!<arch>"):
            return ("binary-archive", "deb/ar archive")
        if head.startswith(b"PK\x03\x04"):
            return ("binary-archive", "zip")
        if head.startswith(b"\x1f\x8b"):
            return ("binary-archive", "gzip")
        if head.startswith(b"BZh"):
            return ("binary-archive", "bzip2")
        if head.startswith(b"\xfd7zXZ"):
            return ("binary-archive", "xz")
        if head.startswith(b"\x89PNG"):
            return ("binary-magic", "png")
        if head.startswith(b"\xff\xd8\xff"):
            return ("binary-magic", "jpeg")
        if head.startswith(b"GIF8"):
            return ("binary-magic", "gif")
        if head.startswith(b"%PDF"):
            return ("binary-magic", "pdf")
        if head.startswith(b"\x1aE\xdf\xa3"):
            return ("binary-magic", "matroska")
        return ("binary", "")

    try:
        text = head.decode("utf-8", errors="replace")
    except Exception:
        return ("binary", "")

    s = text.lstrip()
    first_line = s.split("\n", 1)[0][:100]
    head_low = s[:1500].lower()

    if s.startswith("#!"):
        return ("text-code", first_line)
    if s.startswith("<?xml"):
        return ("text-config", first_line)
    if s.startswith("<"):
        if "<!doctype html" in head_low or "<html" in head_low:
            return ("text-doc", "HTML document")
        return ("text-config", first_line)
    if s.startswith("{") or s.startswith("["):
        return ("text-config", "JSON")
    if s.startswith("---"):
        return ("text-config", "YAML")

    code_markers = (
        "import ",
        "from ",
        "def ",
        "class ",
        "async def",
        "#include",
        "/* ",
        "*/",
        "// ",
        "package ",
        "using namespace",
        "function ",
        "const ",
        "let ",
        "var ",
    )
    if any(m in text[:2500] for m in code_markers):
        return ("text-code", first_line)

    if "copyright" in head_low or "spdx-" in head_low or "license" in head_low:
        return ("text-doc", "license/copyright header")

    if s.startswith("# ") or s.startswith("## "):
        return ("text-doc", "markdown")
    if s.startswith("[") and "]" in first_line:
        return ("text-config", first_line)
    if "=" in first_line and not first_line.startswith("="):
        return ("text-config", first_line)

    log_markers = ("error", "warn", "traceback", "exception", "info:")
    if any(m in head_low for m in log_markers):
        return ("text-log", first_line)

    return ("text-data", first_line)


# ======================================================================
# SCREENSHOT DETECTION
# ======================================================================
SCREENSHOT_NAME_PATTERNS = [
    # GNOME English:      "Screenshot from 2026-09-13 12-34-56.png"
    re.compile(r"^screenshot from \d{4}-\d{2}-\d{2}", re.IGNORECASE),
    # GNOME Portuguese:   "Captura de tela de 2026-09-13 12-34-56.png"
    re.compile(r"^captura de tela de \d{4}-\d{2}-\d{2}", re.IGNORECASE),
    # GNOME Spanish:      "Pantallazo-2026-09-13 12-34-56.png"
    re.compile(r"^pantallazo[\s_\-]*\d{4}", re.IGNORECASE),
    # GNOME German:       "Bildschirmfoto vom 2026-09-13 ..."
    re.compile(r"^bildschirmfoto[\s_\-]", re.IGNORECASE),
    # GNOME Italian:      "Schermata del 2026-09-13 ..."
    re.compile(r"^schermata[\s_\-]", re.IGNORECASE),
    # KDE / XFCE / Android:  "Screenshot_20260913_123456.png"
    re.compile(r"^screenshot_\d{8}_\d{6}", re.IGNORECASE),
    # GNOME generic dated:   "Screenshot_2026-09-13_12-34-56.png"
    re.compile(r"^screenshot[\s_\-]+\d{4}-\d{2}-\d{2}", re.IGNORECASE),
    # Windows-style (users import them): "Screenshot (1).png"
    re.compile(r"^screenshot[\s_]*\(\d+\)", re.IGNORECASE),
    # Bare "screenshot.png", "Screenshot-1.png"
    re.compile(r"^screenshot(\.|[\s_\-]\d)", re.IGNORECASE),
]

SCREENSHOT_LOCATIONS = (
    "/screenshots/",  # covers ~/Pictures/Screenshots, ~/Screenshots
    "/picture/screenshot",  # Portuguese Mint default ~/Imagens/Screenshots
    "/imagens/screenshot",
)

SCREENSHOT_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def is_screenshot(path):
    """Return True if this file looks like a screenshot based on name/folder."""
    p = Path(path)
    if p.suffix.lower() not in SCREENSHOT_EXTS:
        return False
    name = p.name.lower()
    for pat in SCREENSHOT_NAME_PATTERNS:
        if pat.match(name):
            return True
    # fallback: any image inside a known screenshots folder
    spath = str(path).lower()
    for loc in SCREENSHOT_LOCATIONS:
        if loc in spath:
            return True
    return False


# ======================================================================
# DPKG OWNERSHIP CHECK
# ======================================================================
_DPKG_CACHE = None


def _load_dpkg_owned():
    """
    Read every /var/lib/dpkg/info/*.list file into a set of paths.
    ~500K entries on a typical Mint install, ~2 s to load, ~50 MB RAM.
    Cached globally for the lifetime of the process.
    """
    global _DPKG_CACHE
    if _DPKG_CACHE is not None:
        return _DPKG_CACHE

    owned = set()
    try:
        for lst in glob.glob("/var/lib/dpkg/info/*.list"):
            try:
                with open(lst, "r", errors="replace") as f:
                    for line in f:
                        line = line.rstrip("\n")
                        if line:
                            owned.add(line)
            except (PermissionError, OSError):
                continue
    except Exception:
        pass

    _DPKG_CACHE = owned
    return owned


def is_dpkg_owned(path):
    """True if this file is owned by an installed Debian package."""
    owned = _load_dpkg_owned()
    if not owned:
        # Couldn't load the list (unusual) — fail open, don't skip
        return False
    return str(path) in owned
