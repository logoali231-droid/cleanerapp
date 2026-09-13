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
    """
    Seconds → friendly, rounded string.

    Examples:
        3     → 'a few seconds'
        45    → '45 seconds'
        90    → '1 min 30 sec'
        125   → '2 min'
        1500  → '25 min'
        3600  → '1 h'
        5400  → '1 h 30 min'
    """
    sec = int(max(0, sec))
    if sec <= 3:
        return "a few seconds"
    if sec < 60:
        return f"{sec} seconds"
    m, s = divmod(sec, 60)
    if m < 60:
        # Round to nearest 5 seconds within the first minute, then nearest 15
        if m == 1:
            rounded = int(round(s / 5.0) * 5)
            if rounded == 60:
                return "2 min"
            return f"1 min {rounded} sec" if rounded else "1 min"
        return f"{m} min"
    h, m = divmod(m, 60)
    if m == 0:
        return f"{h} h"
    return f"{h} h {m} min"
def short_path(p, maxlen=80):
    """Truncate a long path from the left."""
    p = str(p)
    return p if len(p) <= maxlen else "…" + p[-(maxlen - 1):]