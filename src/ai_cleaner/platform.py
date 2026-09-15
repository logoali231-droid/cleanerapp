"""Cross-platform OS integration for AI File Cleaner."""

from __future__ import annotations

import ctypes
import os
import platform as _platform
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
IS_MACOS = sys.platform == "darwin"


def _windows_is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


IS_ADMIN = _windows_is_admin() if IS_WINDOWS else (os.geteuid() == 0)


def user_home() -> Path:
    if IS_WINDOWS:
        raw = os.environ.get("USERPROFILE")
        if raw:
            return Path(raw)
    return Path.home()


HOME = user_home()


def app_data_dir() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else HOME / "AppData" / "Local"
        return root / "AI File Cleaner"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else HOME / ".config"
    return root / "ai_file_cleaner"


APP_DATA_DIR = app_data_dir()


def normalize_path(path: str | os.PathLike[str]) -> str:
    try:
        p = Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        p = Path(path).expanduser()
    value = os.path.normcase(os.path.normpath(str(p)))
    return value.replace("\\", "/").rstrip("/")


def path_is_within(path, base) -> bool:
    p, b = normalize_path(path), normalize_path(base)
    return p == b or p.startswith(b + "/")


def user_folders() -> dict[str, Path]:
    return {name: HOME / folder for name, folder in {
        "home": ".", "desktop": "Desktop", "documents": "Documents",
        "downloads": "Downloads", "pictures": "Pictures", "videos": "Videos",
        "music": "Music"}.items()}


def whole_system_roots() -> list[Path]:
    if IS_WINDOWS:
        drive = os.environ.get("SystemDrive", "C:")
        return [Path(drive + "\\")]
    return [Path("/")]


def _windows_run_as_admin(args: list[str]) -> tuple[bool, str]:
    try:
        executable = Path(sys.executable)
        params = subprocess.list2cmdline(args if getattr(sys, "frozen", False)
                                         else ["-m", "ai_cleaner", *args])
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(executable), params, str(HOME), 1)
        if result <= 32:
            return False, f"Windows refused the elevation request (code {result})."
        return True, ""
    except Exception as exc:
        return False, f"Couldn't request Windows administrator rights:\n\n{exc}"


def relaunch_as_admin(folder=None, deep=False, signal_file=None):
    args = ["--admin"]
    if folder: args += ["--folder", folder]
    if deep: args += ["--deep"]
    if signal_file: args += ["--signal-file", signal_file]
    if IS_WINDOWS:
        return _windows_run_as_admin(args)
    from .admin import relaunch_as_admin as linux_relaunch
    return linux_relaunch(folder=folder, deep=deep, method="terminal", signal_file=signal_file)


def send_to_trash(path) -> None:
    try:
        from send2trash import send2trash
        send2trash(str(path))
        return
    except ImportError:
        if not IS_LINUX:
            raise RuntimeError("send2trash is required on Windows. Install requirements.txt")
    result = subprocess.run(["gio", "trash", "--", str(path)], check=False,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0:
        raise OSError(f"gio could not move the file to Trash (exit {result.returncode})")


def open_recycle_bin() -> None:
    if IS_WINDOWS:
        os.startfile("shell:RecycleBinFolder")
    elif IS_LINUX:
        subprocess.Popen(["gio", "open", "trash://"], close_fds=True)
    elif IS_MACOS:
        subprocess.Popen(["open", str(HOME / ".Trash")], close_fds=True)


def platform_name() -> str:
    return _platform.system()
