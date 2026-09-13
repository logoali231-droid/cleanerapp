"""Persistent user rules with default seeding."""
import os
import json
import fnmatch

from .config import (
    HOME, RULES_PATH, SETTINGS_PATH, DEFAULTS_SEEDED_FLAG,
)
from .protection import expand_user_path


class RulesManager:
    def __init__(self, path=RULES_PATH):
        self.path = path
        self.rules = []
        self.settings = {
            "skip_rule_confirmation": False,
            "screenshot_min_age_days": 30,
            "min_confidence": -1,   # -1 = AI-learned, >=0 = manual override
        }
        self.load()
        self._load_settings()

    # ---------------------------------------------------------- I/O
    def load(self):
        self.rules = []
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
            if isinstance(data, list):
                self.rules = [r for r in data if isinstance(r, dict)]
        except Exception:
            self.rules = []

    def save(self):
        try:
            with open(self.path, "w") as f:
                json.dump(self.rules, f, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_PATH):
                with open(SETTINGS_PATH, "r") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self.settings.update(data)
        except Exception:
            pass

    def save_settings(self):
        try:
            with open(SETTINGS_PATH, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    # ------------------------------------------------------- defaults
    def seed_defaults_once(self):
        if os.path.exists(DEFAULTS_SEEDED_FLAG):
            return 0
        added = 0
        existing = {(r.get("type"), r.get("value")) for r in self.rules}

        # (type, value, note, always_add)
        defaults = [
            # User folders
            ("folder", f"{HOME}/Documents",  "Your Documents — protect by default", False),
            ("folder", f"{HOME}/Pictures",   "Your Pictures — protect by default", False),
            ("folder", f"{HOME}/Videos",     "Your Videos — protect by default", False),
            ("folder", f"{HOME}/Music",      "Your Music — protect by default", False),
            ("folder", f"{HOME}/Desktop",    "Your Desktop — protect by default", False),
            ("folder", f"{HOME}/Projects",   "Your Projects — protect by default", False),
            ("folder", f"{HOME}/dev",        "Your dev folder — protect by default", False),
            ("folder", f"{HOME}/code",       "Your code folder — protect by default", False),
            ("folder", f"{HOME}/bin",        "Your scripts — protect by default", False),
            ("folder", f"{HOME}/.local/bin", "Your local scripts — protect by default", False),
            # User config & secrets
            ("folder", f"{HOME}/.ssh",         "SSH keys and config — critical", False),
            ("folder", f"{HOME}/.gnupg",       "GPG keys — critical", False),
            ("folder", f"{HOME}/.config",      "Application configuration", False),
            ("folder", f"{HOME}/.local/share", "Application data", False),
            ("folder", f"{HOME}/.mozilla",     "Firefox profile", False),
            ("folder", f"{HOME}/.thunderbird", "Thunderbird profile", False),
            ("folder", f"{HOME}/.var/app",     "Flatpak app data", False),
            # System (always added even if mount is offline)
            ("folder", "/usr",             "System programs and libraries", True),
            ("folder", "/etc",             "System configuration", True),
            ("folder", "/opt",             "Optional system applications", True),
            ("folder", "/boot",            "Kernel and bootloader", True),
            ("folder", "/bin",             "Essential binaries", True),
            ("folder", "/sbin",            "System binaries", True),
            ("folder", "/lib",             "System libraries", True),
            ("folder", "/lib64",           "64-bit libraries", True),
            ("folder", "/root",            "Root user's home directory", True),
            ("folder", "/srv",             "Server data", True),
            ("folder", "/var/lib",         "Application state (databases, containers)", True),
            ("folder", "/var/log",         "System logs", True),
            ("folder", "/var/spool",       "System spool (printers, mail)", True),
            ("folder", "/var/backups",     "System backups", True),
            ("folder", "/var/lib/flatpak", "Flatpak applications and runtimes", True),
            # Dev artefacts
            ("name_contains", "node_modules",  "JavaScript dependencies — never touch", False),
            ("name_contains", "__pycache__",   "Python bytecode cache — never touch", False),
            ("name_contains", ".venv",         "Python virtualenv — never touch", False),
            ("name_contains", "venv",          "Python virtualenv — never touch", False),
            ("name_contains", ".git",          "Git repository data — never touch", False),
            ("name_contains", "site-packages", "Installed Python packages — never touch", False),
        ]

        for rtype, value, note, always_add in defaults:
            if (rtype, value) in existing:
                continue
            if rtype == "folder" and not always_add and not os.path.isdir(value):
                continue
            self.rules.append({
                "type": rtype, "value": value, "action": "protect",
                "note": note, "enabled": True, "default": True,
            })
            added += 1

        if added:
            self.save()
        try:
            with open(DEFAULTS_SEEDED_FLAG, "w") as f:
                f.write("seeded\n")
        except Exception:
            pass
        return added

    # ---------------------------------------------------------- CRUD
    def add(self, rule):
        rule.setdefault("enabled", True)
        rule.setdefault("note", "")
        rule.setdefault("action", "protect")
        self.rules.append(rule)
        self.save()

    def remove(self, idx):
        if 0 <= idx < len(self.rules):
            del self.rules[idx]
            self.save()

    # --------------------------------------------------------- match
    def match(self, path):
        spath = str(path)
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            if self._matches(rule, spath):
                return rule.get("action", "protect"), rule
        return None, None

    @staticmethod
    def _matches(rule, spath):
        t = rule.get("type", "")
        v = rule.get("value", "")
        if not v:
            return False
        if t == "folder":
            v = expand_user_path(v).rstrip("/")
            sp = expand_user_path(spath).rstrip("/")
            return sp == v or sp.startswith(v + "/")
        if t == "extension":
            if not v.startswith("."):
                v = "." + v
            return spath.lower().endswith(v.lower())
        if t == "name_contains":
            return v.lower() in os.path.basename(spath).lower()
        if t == "glob":
            return (fnmatch.fnmatch(spath, v)
                    or fnmatch.fnmatch(os.path.basename(spath), v))
        return False

    @staticmethod
    def describe(rule):
        t = rule.get("type", "")
        v = rule.get("value", "")
        act = rule.get("action", "protect")
        word = "Keep" if act == "protect" else "Suggest deleting"
        if t == "folder":        return f"{word}: everything under {v}"
        if t == "extension":     return f"{word}: all {v} files"
        if t == "name_contains": return f'{word}: names containing "{v}"'
        if t == "glob":          return f"{word}: pattern {v}"
        return f"{word}: {v}"