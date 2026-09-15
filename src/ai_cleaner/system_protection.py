"""Hard safety boundaries for filesystem scanning.

This module is deliberately independent from the AI, user rules, and UI.
A protected path can never become a deletion candidate just because a rule or
model says otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

from .platform import IS_WINDOWS, normalize_path


if IS_WINDOWS:
    _system_drive = normalize_path(os.environ.get("SystemDrive", r"C:"))
    if not _system_drive.endswith(":"):
        _system_drive = _system_drive.split(":", 1)[0] + ":"

    SYSTEM_ROOTS = tuple(
        normalize_path(Path(f"{_system_drive}/") / name)
        for name in (
            "Windows",
            "Program Files",
            "Program Files (x86)",
            "ProgramData",
            "Recovery",
            "System Volume Information",
            "$Recycle.Bin",
            "Config.Msi",
            "Boot",
            "EFI",
        )
    )
else:
    SYSTEM_ROOTS = tuple(
        normalize_path(p)
        for p in (
            "/usr",
            "/etc",
            "/opt",
            "/boot",
            "/bin",
            "/sbin",
            "/lib",
            "/lib64",
            "/root",
            "/srv",
            "/var/lib",
            "/var/log",
            "/var/spool",
            "/var/backups",
            "/var/mail",
        )
    )


def is_system_protected(path: str | os.PathLike[str]) -> bool:
    """Return True for a system-owned boundary or anything below it."""
    value = normalize_path(path)
    return any(value == root or value.startswith(root + "/") for root in SYSTEM_ROOTS)


def is_root_drive(path: str | os.PathLike[str]) -> bool:
    """True for a bare Windows drive root such as C:/, not a child path."""
    if not IS_WINDOWS:
        return normalize_path(path) == "/"
    value = normalize_path(path)
    return len(value) == 2 and value[1] == ":"
