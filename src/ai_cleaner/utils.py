"""Small formatting and display helpers."""


def human(b):
    """Bytes → human readable."""
    b = float(b)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


def age(days):
    """Days → 'today' / '3d old' / '2mo old' / '1y old'."""
    if days < 1:
        return "today"
    if days < 30:
        return f"{days}d old"
    if days < 365:
        return f"{days // 30}mo old"
    return f"{days // 365}y old"


def duration(sec):
    """Seconds → '45 seconds' / '3 min' / '1h 20m'."""
    sec = int(sec)
    if sec < 60:
        return f"{sec} seconds"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m} min"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def short_path(p, maxlen=80):
    """Truncate a long path from the left."""
    p = str(p)
    return p if len(p) <= maxlen else "…" + p[-(maxlen - 1):]