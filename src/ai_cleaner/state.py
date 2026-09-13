"""Discretized state extraction for the RL agent."""
from .protection import GAME_DIRS, GAME_PATH_HINTS, GAME_EXTS


def size_bucket(b):
    mb = b / 1048576
    return 0 if mb < 0.1 else 1 if mb < 1 else 2 if mb < 10 else 3 if mb < 100 else 4


def age_bucket(d):
    return 0 if d < 7 else 1 if d < 30 else 2 if d < 90 else 3 if d < 365 else 4


def ext_bucket(e):
    e = e.lower()
    if e in (".deb", ".rpm", ".appimage", ".run", ".msi", ".exe", ".snap"): return 0
    if e in (".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"):          return 1
    if e in (".log", ".tmp", ".temp", ".cache", ".bak", ".old", ".swp", ".dump"): return 2
    if e in GAME_EXTS:                                                       return 3
    if e in (".py", ".c", ".cpp", ".h", ".js", ".ts", ".rs", ".go", ".sh"): return 4
    if e in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff",
             ".svg", ".ico", ".icns", ".heic", ".avif",
             ".mp4", ".mkv", ".mp3", ".pdf",
             ".doc", ".docx", ".odt", ".txt", ".md"):                        return 5
    return 6


def location_bucket(p):
    p = str(p).lower()
    if "/tmp/" in p or p.startswith("/tmp") or "/var/tmp" in p: return 0
    if "/downloads" in p:                                       return 1
    if "/.cache" in p or "/cache/" in p:                        return 2
    if any(g and g.lower() in p for g in GAME_DIRS):            return 3
    if any(h in p for h in GAME_PATH_HINTS):                    return 3
    if "/trash" in p:                                           return 4
    if p.startswith("/usr/") or p.startswith("/etc/") or p.startswith("/var/"): return 5
    return 6


def extract_state(path, size, age_days):
    return (ext_bucket(path.suffix), size_bucket(size),
            age_bucket(age_days), location_bucket(path))


def plain_reason(path, size, age):
    p = str(path).lower()
    e = path.suffix.lower()
    if e in (".deb", ".rpm", ".appimage", ".run", ".msi", ".exe"):
        return "An old installer you already ran"
    if e in (".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"):
        return "An old download you haven't opened in a long time"
    if e in (".log", ".tmp", ".temp", ".swp"):
        return "A temporary/log file left behind by a program"
    if e.endswith(".dump"):
        return "A crash dump — safe to remove"
    if "cache" in p:
        return "A cache file that can be regenerated"
    if e == ".iso":
        return "An ISO image — usually a disk image you already used"
    if size > 500 * 1048576 and age > 180:
        return "Large file you haven't touched in months"
    return "The AI thinks this file is unused"