"""Paths, constants, and per-user config directory."""
from .platform import APP_DATA_DIR, HOME, IS_ADMIN

# Backwards-compatible name used by the current UI.
IS_ROOT = IS_ADMIN

CONFIG_DIR = str(APP_DATA_DIR)
QTABLE_PATH = str(APP_DATA_DIR / "qtable.pkl")
RULES_PATH = str(APP_DATA_DIR / "rules.json")
SETTINGS_PATH = str(APP_DATA_DIR / "settings.json")
DEFAULTS_SEEDED_FLAG = str(APP_DATA_DIR / ".defaults_seeded")

try:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass
