"""Paths, constants, and per-user config directory."""
import os


def _user_home():
    """Resolve the real user's home even when we're running as root."""
    if os.geteuid() == 0:
        env_home = os.environ.get("AI_CLEANER_USER_HOME")
        if env_home and os.path.isdir(env_home):
            return env_home
        for var in ("SUDO_USER", "PKEXEC_USER", "USER"):
            u = os.environ.get(var)
            if u and u != "root":
                for home in (f"/home/{u}", f"/Users/{u}"):
                    if os.path.isdir(home):
                        return home
    return os.path.expanduser("~")


HOME = _user_home()
IS_ROOT = (os.geteuid() == 0)

CONFIG_DIR = os.path.join(HOME, ".config", "ai_file_cleaner")
QTABLE_PATH = os.path.join(CONFIG_DIR, "qtable.pkl")
RULES_PATH = os.path.join(CONFIG_DIR, "rules.json")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
DEFAULTS_SEEDED_FLAG = os.path.join(CONFIG_DIR, ".defaults_seeded")

try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
except Exception:
    pass