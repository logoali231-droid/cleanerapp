#!/usr/bin/env python3
"""
AI File Cleaner — Wizard Edition (v7)
RL-powered file cleaner for Linux Mint.
"""

import sys, os, time, random, pickle, json, fnmatch, argparse, shutil, shlex, tempfile
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QCheckBox,
    QProgressBar, QFileDialog, QMessageBox, QHeaderView,
    QTextEdit, QAbstractItemView, QStackedWidget, QFrame, QMenu,
    QDialog, QComboBox, QLineEdit, QRadioButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QEventLoop
from PyQt5.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush
import numpy as np

# ======================================================================
# CONFIG PATHS
# ======================================================================
def _user_home():
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
RULES_PATH  = os.path.join(CONFIG_DIR, "rules.json")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "settings.json")
DEFAULTS_SEEDED_FLAG = os.path.join(CONFIG_DIR, ".defaults_seeded")
try:
    os.makedirs(CONFIG_DIR, exist_ok=True)
except Exception:
    pass

def _admin_log(msg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(os.path.join(CONFIG_DIR, "admin-launch.log"), "a") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}\n")
    except Exception:
        pass

# ======================================================================
# PROTECTION RULES
# ======================================================================
GAME_DIRS = [
    f"{HOME}/.steam", f"{HOME}/.local/share/Steam",
    f"{HOME}/.local/share/lutris", f"{HOME}/.local/share/heroic",
    f"{HOME}/.config/heroic", f"{HOME}/.wine",
    f"{HOME}/.local/share/wineprefixes",
    f"{HOME}/.local/share/PrismLauncher", f"{HOME}/.config/PrismLauncher",
    f"{HOME}/PrismLauncher",
    f"{HOME}/.var/app/org.prismlauncher.PrismLauncher",
    f"{HOME}/.local/share/multimc", f"{HOME}/.local/share/PolyMC",
    f"{HOME}/.local/share/multimc5",
    f"{HOME}/.minecraft", f"{HOME}/.var/app/com.mojang.Minecraft",
    "/usr/share/steam", "/usr/games",
]
GAME_PATH_HINTS = [
    "prismlauncher", "multimc", "polymc", "minecraft",
    "steamapps", "lutris", "heroic", "wineprefix",
    "/steam/", "/games/", "/instances/",
    "/minecraft/mods/", "/minecraft/saves/",
]
GAME_EXTS = {
    ".jar", ".class", ".java", ".nbt", ".mca", ".mcr", ".dat_old",
    ".pak", ".vpk", ".bsa", ".esm", ".esp", ".bsl", ".sav",
    ".rom", ".iso", ".cue", ".gba", ".nds", ".3ds",
    ".wad", ".pk3", ".pk4", ".uasset", ".umap", ".unity3d",
    ".asset", ".bundle", ".resources",
}
PSEUDO_FS = (
    "/proc", "/sys", "/dev", "/run", "/snap",
    "/lost+found", "/boot/efi", "/var/lib/docker",
    "/var/lib/snapd/snaps",
)

def _in_pseudo_fs(p):
    p = str(p)
    for skip in PSEUDO_FS:
        if p == skip or p.startswith(skip + "/"):
            return True
    return False

def _expand_user_path(p):
    if p.startswith("~"):
        rest = p[1:].lstrip("/\\")
        return os.path.join(HOME, rest) if rest else HOME
    return os.path.abspath(p)

# ======================================================================
# RULES MANAGER
# ======================================================================
class RulesManager:
    def __init__(self, path=RULES_PATH):
        self.path = path
        self.rules = []
        self.settings = {"skip_rule_confirmation": False}
        self.load()
        self._load_settings()

    def load(self):
        self.rules = []
        if not os.path.exists(self.path): return
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

    def seed_defaults_once(self):
        if os.path.exists(DEFAULTS_SEEDED_FLAG):
            return 0
        added = 0
        existing = {(r.get("type"), r.get("value")) for r in self.rules}
        defaults = [
            ("folder", f"{HOME}/Downloads", "Your Downloads folder — protect by default"),
            ("folder", f"{HOME}/Documents", "Your Documents folder — protect by default"),
            ("folder", f"{HOME}/Pictures",  "Your Pictures folder — protect by default"),
            ("folder", f"{HOME}/Videos",    "Your Videos folder — protect by default"),
            ("folder", f"{HOME}/Music",     "Your Music folder — protect by default"),
            ("folder", f"{HOME}/Desktop",   "Your Desktop folder — protect by default"),
            ("folder", f"{HOME}/Projects",  "Your Projects folder — protect by default"),
            ("folder", f"{HOME}/dev",       "Your dev folder — protect by default"),
            ("folder", f"{HOME}/code",      "Your code folder — protect by default"),
            ("name_contains", "node_modules", "JavaScript dependencies — never touch"),
            ("name_contains", "__pycache__",  "Python bytecode cache — never touch"),
            ("name_contains", ".venv",        "Python virtualenv — never touch"),
            ("name_contains", "venv",         "Python virtualenv — never touch"),
            ("name_contains", ".git",         "Git repository data — never touch"),
            ("name_contains", "site-packages","Installed Python packages — never touch"),
        ]
        for rtype, value, note in defaults:
            if (rtype, value) in existing: continue
            if rtype == "folder" and not os.path.isdir(value): continue
            self.rules.append({
                "type": rtype, "value": value, "action": "protect",
                "note": note, "enabled": True, "default": True,
            })
            added += 1
        if added: self.save()
        try:
            with open(DEFAULTS_SEEDED_FLAG, "w") as f: f.write("seeded\n")
        except Exception: pass
        return added

    def add(self, rule):
        rule.setdefault("enabled", True)
        rule.setdefault("note", "")
        rule.setdefault("action", "protect")
        self.rules.append(rule)
        self.save()

    def remove(self, idx):
        if 0 <= idx < len(self.rules):
            del self.rules[idx]; self.save()

    def match(self, path):
        spath = str(path)
        for rule in self.rules:
            if not rule.get("enabled", True): continue
            if self._matches(rule, spath):
                return rule.get("action", "protect"), rule
        return None, None

    @staticmethod
    def _matches(rule, spath):
        t = rule.get("type", ""); v = rule.get("value", "")
        if not v: return False
        if t == "folder":
            v = _expand_user_path(v).rstrip("/")
            sp = _expand_user_path(spath).rstrip("/")
            return sp == v or sp.startswith(v + "/")
        if t == "extension":
            if not v.startswith("."): v = "." + v
            return spath.lower().endswith(v.lower())
        if t == "name_contains":
            return v.lower() in os.path.basename(spath).lower()
        if t == "glob":
            return (fnmatch.fnmatch(spath, v)
                    or fnmatch.fnmatch(os.path.basename(spath), v))
        return False

    @staticmethod
    def describe(rule):
        t = rule.get("type", ""); v = rule.get("value", "")
        act = rule.get("action", "protect")
        word = "Keep" if act == "protect" else "Suggest deleting"
        if t == "folder":        return f"{word}: everything under {v}"
        if t == "extension":     return f"{word}: all {v} files"
        if t == "name_contains": return f'{word}: names containing "{v}"'
        if t == "glob":          return f"{word}: pattern {v}"
        return f"{word}: {v}"

# ======================================================================
# STATE + AGENT
# ======================================================================
def size_bucket(b):
    mb_ = b / 1048576
    return 0 if mb_ < 0.1 else 1 if mb_ < 1 else 2 if mb_ < 10 else 3 if mb_ < 100 else 4
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
    p = str(path).lower(); e = path.suffix.lower()
    if e in (".deb", ".rpm", ".appimage", ".run", ".msi", ".exe"):
        return "An old installer you already ran"
    if e in (".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar"):
        return "An old download you haven't opened in a long time"
    if e in (".log", ".tmp", ".temp", ".swp"):
        return "A temporary/log file left behind by a program"
    if e.endswith(".dump"): return "A crash dump — safe to remove"
    if "cache" in p:        return "A cache file that can be regenerated"
    if e == ".iso":         return "An ISO image — usually a disk image you already used"
    if size > 500 * 1048576 and age > 180:
        return "Large file you haven't touched in months"
    return "The AI thinks this file is unused"

class SyntheticFileEnv:
    def __init__(self, seed=None): self.rng = random.Random(seed)
    def sample(self):
        loc = self.rng.choices([0,1,2,3,4,5,6], weights=[15,20,15,8,10,5,27])[0]
        if loc == 3:   ext = 3
        elif loc == 5: ext = self.rng.choice([4,5,6])
        else:          ext = self.rng.choices([0,1,2,3,4,5,6], weights=[15,15,15,3,10,15,27])[0]
        size = self.rng.choices([0,1,2,3,4], weights=[15,25,30,20,10])[0]
        age  = self.rng.choices([0,1,2,3,4], weights=[15,20,20,25,20])[0]
        d = 0
        if   ext == 0 and loc in (0,1) and age >= 2: d = 1
        elif ext == 2 and loc in (0,2) and age >= 1: d = 1
        elif ext == 1 and loc == 1 and age >= 3:     d = 1
        elif loc == 4:                                d = 1
        elif loc == 5:                                d = 0
        elif ext == 3 or loc == 3:                    d = 0
        if self.rng.random() < 0.05: d = 1 - d
        return (ext, size, age, loc), d
    @staticmethod
    def reward(s, a, t):
        ext, _, _, loc = s
        if ext == 3 or loc == 3: return +1.0 if a == 0 else -1000.0
        if a == 1: return +10.0 if t == 1 else -100.0
        return -1.0 if t == 1 else +1.0

class QLearningAgent:
    SHAPE = (7, 5, 5, 7, 2)
    def __init__(self, alpha=0.15, epsilon=0.15):
        self.alpha, self.epsilon = alpha, epsilon
        self.Q = np.zeros(self.SHAPE)
        self.counts = np.zeros(self.SHAPE[:-1], dtype=np.int64)
    def act(self, s, explore=False):
        if explore and random.random() < self.epsilon: return random.randint(0, 1)
        q = self.Q[s]
        return 0 if q[0] == q[1] else int(np.argmax(q))
    def learn(self, s, a, r):
        self.Q[s][a] += self.alpha * (r - self.Q[s][a]); self.counts[s] += 1
    def confidence(self, s): return float(abs(self.Q[s][1] - self.Q[s][0]))
    def visited_states(self): return int(np.count_nonzero(self.counts))
    def save(self, path=QTABLE_PATH):
        try:
            with open(path, "wb") as f:
                pickle.dump({"Q": self.Q, "counts": self.counts}, f)
        except Exception: pass
    def load(self, path=QTABLE_PATH):
        if not os.path.exists(path): return False
        try:
            with open(path, "rb") as f: d = pickle.load(f)
            self.Q = d["Q"]; self.counts = d["counts"]; return True
        except Exception:
            return False
    def reset(self):
        self.Q.fill(0.0); self.counts.fill(0)

def train_agent(agent, episodes=20000, seed=None):
    env = SyntheticFileEnv(seed=seed)
    for _ in range(episodes):
        s, t = env.sample()
        a = agent.act(s, explore=True)
        agent.learn(s, a, env.reward(s, a, t))

def reinforce_agent_from_rule(agent, rule):
    if rule.get("type") != "extension": return
    v = rule.get("value", "")
    if not v: return
    if not v.startswith("."): v = "." + v
    eb = ext_bucket(v)
    action = 0 if rule.get("action") == "protect" else 1
    other = 1 - action
    reward = 40.0 if action == 0 else 20.0
    for s in range(5):
        for a in range(5):
            for l in range(7):
                st = (eb, s, a, l)
                for _ in range(30):
                    agent.learn(st, action, +reward)
                    agent.learn(st, other, -reward)

# ======================================================================
# DEMO FILES
# ======================================================================
def create_demo_files(root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    def mk(rel, days, size):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as f:
            chunk = b"\x42" * 8192; w = 0
            while w < size:
                n = min(len(chunk), size - w); f.write(chunk[:n]); w += n
        ts = (datetime.now() - timedelta(days=days)).timestamp()
        os.utime(p, (ts, ts))
    junk = [
        ("tmp/setup_legacy_tool.deb", 220, 15*1048576),
        ("tmp/old_package_manager.rpm", 310, 8*1048576),
        ("tmp/NodeApp-3.2.1.AppImage", 160, 45*1048576),
        ("tmp/gpu_driver_installer.run", 400, 120*1048576),
        ("tmp/build_debug.log", 65, 800*1024),
        ("tmp/core.dump", 75, 300*1048576),
        ("var/tmp/cache_build.tar.gz", 180, 20*1048576),
        ("Downloads/ubuntu_iso_2022.iso", 500, 700*1048576),
        ("Downloads/photos_backup.zip", 240, 80*1048576),
        ("Downloads/random_article.tar.xz", 190, 12*1048576),
        ("Downloads/video_rip_old.mp4", 380, 250*1048576),
        ("cache/thumbs_cache.dat", 95, 30*1048576),
        ("cache/browser_cache.bin", 130, 60*1048576),
        ("cache/stale_index.tmp", 400, 400*1024),
    ]
    keepers = [
        ("Documents/thesis_final.pdf", 5, 2*1048576),
        ("Documents/notes.txt", 2, 30*1024),
        ("Pictures/vacation_2024.jpg", 8, 4*1048576),
        ("Projects/myscript.py", 1, 15*1024),
        ("Projects/main.c", 3, 8*1024),
    ]
    protected = [
        ("games/MyGame/assets.pak", 300, 120*1048576),
        ("mods/jei_1.20.1.jar", 30, 2*1048576),
        (".local/share/PrismLauncher/instances/1.20.1-forge/minecraft/mods/sodium.jar", 400, 1048576),
        (".minecraft/mods/legacy_mod.jar", 600, 2*1048576),
    ]
    for rel, d, s in junk + keepers + protected: mk(rel, d, s)
    return {"junk": len(junk), "keepers": len(keepers), "protected": len(protected),
            "path": str(root),
            "total_mb": sum(s for _, _, s in junk + keepers + protected) / 1048576}

# ======================================================================
# SCANNER
# ======================================================================
class ScannerThread(QThread):
    progress       = pyqtSignal(int, int, str, float, bool)
    file_found     = pyqtSignal(dict)
    finished_scan  = pyqtSignal(list)
    status         = pyqtSignal(str)

    def __init__(self, root_path, agent, rules, deep_mode=False):
        super().__init__()
        self.root_path = root_path; self.agent = agent; self.rules = rules
        self.deep_mode = deep_mode; self._running = True

    def stop(self): self._running = False

    @staticmethod
    def _is_protected(path):
        p = str(path).lower()
        if any(g and g.lower() in p for g in GAME_DIRS): return True
        if any(h in p for h in GAME_PATH_HINTS):         return True
        if path.suffix.lower() in GAME_EXTS:              return True
        return False

    def _should_prune_dir(self, dirpath, dirname):
        full = os.path.join(dirpath, dirname)
        if _in_pseudo_fs(full): return True
        if not self.deep_mode and dirname.startswith("."):
            if dirname not in (".local", ".cache"): return True
        low = full.lower()
        if any(g and g.lower() in low for g in GAME_DIRS): return True
        if any(h in low for h in GAME_PATH_HINTS):         return True
        return False

    def _count_files(self, root):
        n = 0; t_last = time.time()
        for dp, dns, fns in os.walk(root, onerror=lambda e: None):
            if not self._running: break
            dns[:] = [d for d in dns if not self._should_prune_dir(dp, d)]
            n += len(fns)
            now = time.time()
            if now - t_last > 0.2:
                self.progress.emit(n, 0, dp, 0.0, True)
                t_last = now
        return n

    def run(self):
        root = Path(self.root_path).expanduser().resolve()
        self.status.emit("Counting files…")
        total = self._count_files(root)
        if not self._running:
            self.finished_scan.emit([]); return
        self.status.emit(f"Analyzing {total:,} files…")
        results = []; scanned = 0; t0 = time.time(); last_emit = 0.0
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            if not self._running: break
            dirnames[:] = [d for d in dirnames if not self._should_prune_dir(dirpath, d)]
            for fname in filenames:
                if not self._running: break
                scanned += 1
                fpath = Path(dirpath) / fname
                rule_action, rule = self.rules.match(fpath)
                if rule_action == "protect": continue
                if rule_action == "flag":
                    try:
                        st = fpath.stat()
                        info = {"path": str(fpath), "name": fpath.name,
                                "size": st.st_size,
                                "age": int((time.time() - st.st_mtime) / 86400.0),
                                "state": None, "confidence": 999.0,
                                "reason": rule.get("note") or f"Your rule: {rule.get('value','')}"}
                        results.append(info); self.file_found.emit(info)
                    except (PermissionError, OSError): pass
                    continue
                try:
                    if not fpath.is_file(): continue
                    if self._is_protected(fpath): continue
                    st = fpath.stat()
                    size = st.st_size
                    age = (time.time() - st.st_mtime) / 86400.0
                    state = extract_state(fpath, size, age)
                    if self.agent.act(state, explore=False) == 1:
                        info = {"path": str(fpath), "name": fpath.name,
                                "size": size, "age": int(age), "state": state,
                                "confidence": self.agent.confidence(state),
                                "reason": plain_reason(fpath, size, int(age))}
                        results.append(info); self.file_found.emit(info)
                except (PermissionError, OSError, FileNotFoundError):
                    continue
                now = time.time()
                if now - last_emit > 0.15:
                    elapsed = now - t0
                    eta = 0.0
                    if scanned > 0 and elapsed > 0:
                        rate = scanned / elapsed
                        eta = max(0, total - scanned) / rate if rate > 0 else 0.0
                    self.progress.emit(scanned, total, dirpath, eta, False)
                    last_emit = now
        self.progress.emit(scanned, total, "", 0.0, False)
        self.finished_scan.emit(results)

# ======================================================================
# STYLESHEET
# ======================================================================
QSS = """
QMainWindow, QWidget { background: #f7f8fb; color: #1e2430;
    font-family: 'Ubuntu','Segoe UI',sans-serif; font-size: 14px; }
QLabel#Hero   { font-size: 34px; font-weight: 800; color: #1e2430; }
QLabel#SubHero{ font-size: 16px; color: #5a6478; }
QLabel#Section{ font-size: 20px; font-weight: 700; color: #1e2430; }
QLabel#Hint   { color: #5a6478; font-size: 13px; }
QLabel#Mono   { color: #3a4358; font-size: 12px; font-family: 'Ubuntu Mono',monospace; }
QLabel#BigStat{ font-size: 40px; font-weight: 800; color: #2f7ad6; }
QLabel#StatLbl{ color: #5a6478; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; }
QLabel#Admin  { color: #b37400; font-weight: 700; }
QPushButton { background: #2f7ad6; color: white; border: none; padding: 12px 24px;
    border-radius: 8px; font-size: 15px; font-weight: 700; min-height: 22px; }
QPushButton:hover   { background: #2868b8; }
QPushButton:pressed { background: #1f528f; }
QPushButton:disabled{ background: #c8cdd6; color: #eef0f4; }
QPushButton#Ghost { background: #e8ecf3; color: #1e2430; }
QPushButton#Ghost:hover { background: #d8dee8; }
QPushButton#Danger { background: #e04b4b; }
QPushButton#Big { font-size: 17px; padding: 16px 32px; }
QPushButton#Browse { padding: 8px 14px; font-size: 13px; }
QFrame#Card { background: white; border-radius: 12px; border: 1px solid #e6e9f0; }
QFrame#Warn { background: #fff6e0; border-radius: 10px; border: 1px solid #f0d79e; }
QTableWidget { background: white; border: 1px solid #e6e9f0; border-radius: 8px;
    gridline-color: #eef0f4; }
QHeaderView::section { background: #eef1f7; color: #1e2430; padding: 10px;
    border: none; font-weight: 700; }
QProgressBar { border: none; background: #e8ecf3; border-radius: 8px; height: 16px;
    text-align: center; color: #1e2430; font-weight: 600; }
QProgressBar::chunk { background: #2f7ad6; border-radius: 8px; }
QTextEdit { background: white; border: 1px solid #e6e9f0; border-radius: 8px;
    padding: 8px; color: #1e2430; }
QLineEdit, QComboBox { background: white; border: 1px solid #d8dee8; border-radius: 6px;
    padding: 8px 10px; font-size: 14px; }
QLineEdit:focus, QComboBox:focus { border-color: #2f7ad6; }
QRadioButton { padding: 4px; }
"""

def card():
    f = QFrame(); f.setObjectName("Card"); return f

def make_stat(value, label):
    w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0,0,0,0); v.setSpacing(2)
    vl = QLabel(value); vl.setObjectName("BigStat"); vl.setAlignment(Qt.AlignCenter)
    ll = QLabel(label);  ll.setObjectName("StatLbl"); ll.setAlignment(Qt.AlignCenter)
    v.addWidget(vl); v.addWidget(ll)
    return w

def set_bigstat(widget, text):
    for w in widget.findChildren(QLabel):
        if w.objectName() == "BigStat":
            w.setText(text); return

# ======================================================================
# RULE EDITOR
# ======================================================================
class RuleEditor(QDialog):
    def __init__(self, parent=None, preset=None):
        super().__init__(parent)
        self.setWindowTitle("Add a rule")
        self.resize(620, 460)
        self.result_rule = None
        self._build(preset or {})

    def _build(self, preset):
        v = QVBoxLayout(self); v.setSpacing(12); v.setContentsMargins(24, 24, 24, 20)
        t = QLabel("New rule"); t.setObjectName("Section"); v.addWidget(t)

        v.addWidget(QLabel("1.  What should I do?"))
        self.rb_protect = QRadioButton("🛡  Always keep these files — never touch them")
        self.rb_flag    = QRadioButton("🗑  Always suggest deleting these files")
        self.rb_protect.setChecked(True)
        v.addWidget(self.rb_protect); v.addWidget(self.rb_flag)

        v.addWidget(QLabel("2.  How do I recognize them?"))
        self.cmb_type = QComboBox()
        self.cmb_type.addItems([
            "Files inside a folder…",
            "Files with a file extension…",
            "Files whose name contains…",
            "Files matching a wildcard…",
        ])
        self.cmb_type.currentIndexChanged.connect(self._on_type_change)
        v.addWidget(self.cmb_type)

        val_row = QHBoxLayout()
        self.inp_value = QLineEdit()
        self.inp_value.setPlaceholderText("Type here, or click Browse for a folder…")
        self.btn_browse = QPushButton("📁  Browse…")
        self.btn_browse.setObjectName("Browse")
        self.btn_browse.setVisible(False)
        self.btn_browse.clicked.connect(self._browse)
        val_row.addWidget(self.inp_value, 1)
        val_row.addWidget(self.btn_browse)
        v.addLayout(val_row)

        self.hint = QLabel(""); self.hint.setObjectName("Hint"); self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        v.addWidget(QLabel("3.  (Optional) A short note for yourself:"))
        self.inp_note = QLineEdit()
        self.inp_note.setPlaceholderText("e.g. Icon theme files — do not delete")
        v.addWidget(self.inp_note)

        if preset:
            if preset.get("action") == "flag":
                self.rb_flag.setChecked(True)
            m = {"folder":0, "extension":1, "name_contains":2, "glob":3}
            if preset.get("type") in m:
                self.cmb_type.setCurrentIndex(m[preset["type"]])
            self.inp_value.setText(preset.get("value",""))
            self.inp_note.setText(preset.get("note",""))

        self._on_type_change()
        v.addStretch(1)

        row = QHBoxLayout(); row.addStretch(1)
        bc = QPushButton("Cancel"); bc.setObjectName("Ghost"); bc.clicked.connect(self.reject)
        bo = QPushButton("Save rule"); bo.clicked.connect(self._ok)
        row.addWidget(bc); row.addWidget(bo)
        v.addLayout(row)

    def _on_type_change(self):
        idx = self.cmb_type.currentIndex()
        hints = [
            "Example:  /home/you/Downloads/installers   — protects everything inside that folder",
            "Example:  .svg    .log    .bak   — matches by file extension",
            "Example:  trashcan_   or   backup_   — any file whose name contains this text",
            "Example:  *.bak   or   *backup*   — wildcard patterns",
        ]
        self.hint.setText(hints[idx])
        self.btn_browse.setVisible(idx == 0)
        if idx == 0:   self.inp_value.setPlaceholderText("Path to folder… (or Browse)")
        elif idx == 1: self.inp_value.setPlaceholderText(".deb")
        elif idx == 2: self.inp_value.setPlaceholderText("backup_")
        else:          self.inp_value.setPlaceholderText("*.bak")

    def _browse(self):
        start = self.inp_value.text().strip() or HOME
        if start.startswith("~"):
            start = _expand_user_path(start)
        if not os.path.isdir(start):
            start = HOME
        d = QFileDialog.getExistingDirectory(self, "Pick a folder to protect",
                                             start, QFileDialog.ShowDirsOnly)
        if d: self.inp_value.setText(d)

    def _ok(self):
        types = ["folder", "extension", "name_contains", "glob"]
        val = self.inp_value.text().strip()
        if not val:
            QMessageBox.warning(self, "Missing value",
                                "Please enter a value so I know what to match.")
            return
        self.result_rule = {
            "type": types[self.cmb_type.currentIndex()],
            "value": val,
            "action": "protect" if self.rb_protect.isChecked() else "flag",
            "note": self.inp_note.text().strip(),
            "enabled": True,
        }
        self.accept()

# ======================================================================
# RULES DIALOG
# ======================================================================
class RulesDialog(QDialog):
    rules_changed = pyqtSignal()

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Teach the AI — rules")
        self.resize(860, 540)
        self._build()
        self._refresh()

    def _build(self):
        v = QVBoxLayout(self); v.setSpacing(12); v.setContentsMargins(24, 24, 24, 20)
        t = QLabel("Your rules"); t.setObjectName("Section"); v.addWidget(t)
        intro = QLabel(
            "Rules take priority over the AI. You can also right-click any file in the "
            "Review list to create a rule on the spot.")
        intro.setObjectName("Hint"); intro.setWordWrap(True); v.addWidget(intro)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Rule", "Action", "Note", ""])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 36); self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 220); self.table.setColumnWidth(4, 100)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)

        self.empty = QLabel("You haven't added any rules yet.")
        self.empty.setObjectName("Hint"); self.empty.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty)

        srow = QHBoxLayout()
        self.cb_skip = QCheckBox("Add new rules without asking for confirmation")
        self.cb_skip.setChecked(bool(self.manager.settings.get("skip_rule_confirmation")))
        self.cb_skip.stateChanged.connect(self._toggle_skip)
        srow.addWidget(self.cb_skip); srow.addStretch(1)
        v.addLayout(srow)

        row = QHBoxLayout()
        b_add = QPushButton("＋  Add a rule…")
        b_add.clicked.connect(self._add_rule)
        b_close = QPushButton("Done"); b_close.setObjectName("Ghost")
        b_close.clicked.connect(self.accept)
        row.addWidget(b_add); row.addStretch(1); row.addWidget(b_close)
        v.addLayout(row)

    def _toggle_skip(self, state):
        self.manager.settings["skip_rule_confirmation"] = bool(state)
        self.manager.save_settings()

    def _refresh(self):
        self.table.setRowCount(0)
        if not self.manager.rules:
            self.empty.setVisible(True); return
        self.empty.setVisible(False)
        for i, rule in enumerate(self.manager.rules):
            r = self.table.rowCount(); self.table.insertRow(r)
            cb = QCheckBox(); cb.setChecked(rule.get("enabled", True))
            cb.stateChanged.connect(lambda st, idx=i: self._toggle(idx, st))
            cw = QWidget(); cl = QHBoxLayout(cw)
            cl.addWidget(cb); cl.setAlignment(Qt.AlignCenter); cl.setContentsMargins(0,0,0,0)
            self.table.setCellWidget(r, 0, cw)
            desc = self.manager.describe(rule)
            if rule.get("default"): desc = "★  " + desc
            item = QTableWidgetItem(desc)
            if rule.get("default"): item.setForeground(QColor("#7a5a10"))
            self.table.setItem(r, 1, item)
            act = "Keep" if rule.get("action") == "protect" else "Suggest delete"
            ai = QTableWidgetItem(act)
            ai.setForeground(QColor("#2f7ad6" if act == "Keep" else "#e04b4b"))
            self.table.setItem(r, 2, ai)
            self.table.setItem(r, 3, QTableWidgetItem(rule.get("note","")))
            b_del = QPushButton("Remove"); b_del.setObjectName("Ghost")
            b_del.clicked.connect(lambda _, idx=i: self._delete(idx))
            self.table.setCellWidget(r, 4, b_del)

    def _toggle(self, idx, state):
        if 0 <= idx < len(self.manager.rules):
            self.manager.rules[idx]["enabled"] = bool(state)
            self.manager.save(); self.rules_changed.emit()

    def _delete(self, idx):
        self.manager.remove(idx); self._refresh(); self.rules_changed.emit()

    def _add_rule(self):
        dlg = RuleEditor(self)
        if dlg.exec_() == QDialog.Accepted and dlg.result_rule:
            self.manager.add(dlg.result_rule)
            self._refresh(); self.rules_changed.emit()

# ======================================================================
# ADMIN RELAUNCH HELPERS
# ======================================================================
def _find_terminal():
    for t in ("mate-terminal", "x-terminal-emulator", "gnome-terminal",
              "xfce4-terminal", "konsole", "kitty", "alacritty", "xterm"):
        p = shutil.which(t)
        if p: return p
    return None

def _find_askpass():
    for tool in ("zenity", "yad", "ssh-askpass", "ssh-askpass-gnome",
                 "ksshaskpass", "lxqt-openssh-askpass"):
        p = shutil.which(tool)
        if p: return p
    return None

def _build_script_launcher(tmp_script, python, script, folder, deep):
    lines = [
        "#!/bin/bash",
        "echo '=== AI File Cleaner — admin launch ==='",
        "echo 'The system will now ask for your password.'",
        "echo",
    ]
    cmd = f"sudo -E {shlex.quote(python)} {shlex.quote(script)} --admin"
    if folder: cmd += f" --folder {shlex.quote(folder)}"
    if deep:   cmd += " --deep"
    lines.append(cmd)
    lines += [
        "rc=$?",
        "echo",
        "if [ $rc -ne 0 ]; then echo \"=== Launch failed (exit $rc) ===\"; fi",
        "echo 'Press Enter to close this window…'",
        "read _",
        f"rm -f {shlex.quote(tmp_script)}",
    ]
    return "\n".join(lines) + "\n"

def _terminal_argv(term, script_path):
    name = os.path.basename(term)
    if name in ("gnome-terminal", "mate-terminal"):
        return [term, "--", "bash", script_path]
    if name == "xfce4-terminal":
        return [term, "--command", f"bash {shlex.quote(script_path)}"]
    if name == "konsole":
        return [term, "-e", "bash", script_path]
    return [term, "-e", "bash", script_path]

def relaunch_as_admin(folder=None, deep=False, method="terminal",
                      signal_file=None, parent=None):
    python = sys.executable or "python3"
    script = os.path.abspath(__file__)
    inner = [python, script, "--admin"]
    if folder:      inner += ["--folder", folder]
    if deep:        inner += ["--deep"]
    if signal_file: inner += ["--signal-file", signal_file]

    _admin_log(f"method={method}  folder={folder}  deep={deep}")
    _admin_log(f"python={python}")
    _admin_log(f"script={script}")
    _admin_log(f"signal={signal_file}")

    if method == "terminal":
        term = _find_terminal()
        if not term:
            return False, ("Couldn't find a terminal emulator.\n\n"
                           "Install one with:  sudo apt install mate-terminal")
        fd, tmp = tempfile.mkstemp(prefix="ai-cleaner-launch-", suffix=".sh")
        os.close(fd)
        try:
            with open(tmp, "w") as f:
                f.write(_build_script_launcher(tmp, python, script, folder, deep))
            os.chmod(tmp, 0o755)
            argv = _terminal_argv(term, tmp)
            _admin_log(f"exec: {argv}")
            subprocess.Popen(argv, close_fds=True)
            return True, ""
        except Exception as e:
            _admin_log(f"terminal Popen failed: {e}")
            return False, f"Couldn't launch {term}:\n\n{e}"

    if method == "askpass":
        askpass = _find_askpass()
        if not askpass:
            return False, ("No graphical password tool found.\n\n"
                           "Install one with:  sudo apt install zenity\n"
                           "Or switch to Terminal.")
        env = os.environ.copy()
        env["SUDO_ASKPASS"] = askpass
        env["AI_CLEANER_USER_HOME"] = HOME
        try:
            _admin_log(f"askpass={askpass}")
            subprocess.Popen(["sudo", "-A", "-E"] + inner, env=env, close_fds=True)
            return True, ""
        except Exception as e:
            _admin_log(f"askpass failed: {e}")
            return False, f"Couldn't launch sudo with {askpass}:\n\n{e}"

    if method == "pkexec":
        pkexec = shutil.which("pkexec")
        if not pkexec:
            return False, ("pkexec isn't installed.\n\n"
                           "Switch the method to 'Terminal' and try again.")
        env_pairs = [
            f"HOME={os.environ.get('HOME','')}",
            f"DISPLAY={os.environ.get('DISPLAY', ':0')}",
            f"XAUTHORITY={os.environ.get('XAUTHORITY', os.path.expanduser('~/.Xauthority'))}",
            f"XDG_RUNTIME_DIR={os.environ.get('XDG_RUNTIME_DIR','')}",
            f"AI_CLEANER_USER_HOME={HOME}",
            "QT_QPA_PLATFORM=xcb",
        ]
        argv = [pkexec, "env"] + env_pairs + inner
        try:
            _admin_log(f"exec: {argv}")
            subprocess.Popen(argv, close_fds=True)
            return True, ""
        except Exception as e:
            _admin_log(f"pkexec failed: {e}")
            return False, f"Couldn't launch pkexec:\n\n{e}"

    return False, f"Unknown method: {method}"

# ======================================================================
# MAIN WINDOW
# ======================================================================
class Wizard(QMainWindow):
    STEPS = ["Welcome", "Choose folder", "Scan", "Review", "Clean up", "Done"]

    def __init__(self, admin_mode=False, start_folder=None, start_deep=False):
        super().__init__()
        self.setWindowTitle("AI File Cleaner" + ("  —  Administrator" if IS_ROOT else ""))
        self.setWindowIcon(self._app_icon())
        self.setGeometry(120, 80, 1100, 760)
        self.setMinimumSize(940, 620)

        self.agent = QLearningAgent()
        loaded = self.agent.load()
        self.rules = RulesManager()
        seeded = self.rules.seed_defaults_once()
        if seeded: print(f"[defaults] Seeded {seeded} protection rule(s).")

        self.scanner = None
        self.scan_results = []
        self.folder = None
        self.deep_mode = False
        self._last_trashed = []

        self._build_menu()
        self._build_ui()

        if not loaded:
            QTimer.singleShot(150, lambda: self._train_agent(12000, silent=True))

        if admin_mode and start_folder:
            self._set_folder(start_folder)
            if start_deep: self.deep_check.setChecked(True)
            QTimer.singleShot(400, self._start_scan)

    def _app_icon(self):
        pm = QPixmap(64, 64); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor("#2f7ad6"))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(2, 2, 60, 60, 14, 14)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRoundedRect(20, 16, 24, 32, 3, 3)
        p.end()
        return QIcon(pm)

    def _current_admin_method(self):
        if not self.admin_method: return "terminal"
        return ["terminal", "pkexec", "askpass"][self.admin_method.currentIndex()]

    # ---------------- menu ----------------
    def _build_menu(self):
        m = self.menuBar()
        f = m.addMenu("&File")
        f.addAction("Choose folder…", self._pick_folder, "Ctrl+O")
        f.addAction("Quit", self.close, "Ctrl+Q")
        t = m.addMenu("&Tools")
        t.addAction("Teach the AI — manage rules…", self._manage_rules, "Ctrl+R")
        t.addSeparator()
        t.addAction("Create demo files…", self._make_demo)
        t.addSeparator()
        t.addAction("Retrain AI from scratch", lambda: self._train_agent(20000))
        t.addAction("Reset AI learning", self._reset_agent)
        t.addSeparator()
        if not IS_ROOT:
            t.addAction("Relaunch as administrator…", self._relaunch_admin)
        t.addAction("Scan entire system…", self._preset_whole_system)
        h = m.addMenu("&Help")
        h.addAction("How it works", self._show_help)
        h.addAction("Teach the AI (quick guide)", self._show_teach_guide)
        h.addAction("About", self._show_about)

    # ---------------- UI ----------------
    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setStyleSheet("background: white; border-right: 1px solid #e6e9f0;")
        sidebar.setFixedWidth(240)
        sv = QVBoxLayout(sidebar); sv.setContentsMargins(20, 24, 20, 20); sv.setSpacing(6)
        logo = QLabel("🧹  AI Cleaner")
        logo.setStyleSheet("font-size:18px; font-weight:800; color:#1e2430; padding:4px 0 18px 0;")
        sv.addWidget(logo)
        self.step_labels = []
        for i, name in enumerate(self.STEPS):
            lbl = QLabel(f"{i+1}.  {name}")
            lbl.setStyleSheet("color:#5a6478; padding:8px 12px; border-radius:6px;")
            sv.addWidget(lbl); self.step_labels.append(lbl)
        sv.addStretch(1)
        if IS_ROOT:
            badge = QLabel("🔓  Running as administrator")
            badge.setObjectName("Admin"); badge.setWordWrap(True)
            sv.addWidget(badge)
        self.agent_info = QLabel("AI is ready.")
        self.agent_info.setObjectName("Hint"); self.agent_info.setWordWrap(True)
        sv.addWidget(self.agent_info)
        self.rules_info = QLabel("")
        self.rules_info.setObjectName("Hint"); self.rules_info.setWordWrap(True)
        sv.addWidget(self.rules_info)
        root.addWidget(sidebar)

        right = QWidget(); rv = QVBoxLayout(right)
        rv.setContentsMargins(32, 24, 32, 20); rv.setSpacing(14)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_pick())
        self.stack.addWidget(self._page_scan())
        self.stack.addWidget(self._page_review())
        self.stack.addWidget(self._page_cleanup())
        self.stack.addWidget(self._page_done())
        rv.addWidget(self.stack, 1)

        nav = QHBoxLayout()
        self.btn_back = QPushButton("←  Back"); self.btn_back.setObjectName("Ghost")
        self.btn_back.clicked.connect(self._go_back); self.btn_back.setVisible(False)
        self.btn_next = QPushButton("Get Started  →"); self.btn_next.setObjectName("Big")
        self.btn_next.clicked.connect(self._go_next)
        nav.addWidget(self.btn_back); nav.addStretch(1); nav.addWidget(self.btn_next)
        rv.addLayout(nav)

        root.addWidget(right, 1)
        self._refresh_agent_info()
        self._set_step(0)

    # ---------------- pages ----------------
    def _page_welcome(self):
        p = QWidget(); v = QVBoxLayout(p); v.setSpacing(20); v.addStretch(1)
        t = QLabel("Hi there 👋"); t.setObjectName("Hero")
        sub = QLabel(
            "I find files you probably don't need — old installers, forgotten "
            "downloads, cache leftovers — and remove them safely.\n\n"
            "You can teach me what to keep or flag anytime:  right-click any file, "
            "or use  Tools → Teach the AI.")
        sub.setObjectName("SubHero"); sub.setWordWrap(True)
        v.addWidget(t); v.addWidget(sub)
        info = card(); iv = QVBoxLayout(info); iv.setContentsMargins(20,20,20,20); iv.setSpacing(8)
        h = QLabel("How it works"); h.setObjectName("Section"); iv.addWidget(h)
        for s in [
            "1.  Pick a folder (Home is a good start).",
            "2.  I scan and show you what I found.",
            "3.  Right-click anything to teach me a rule.",
            "4.  One click frees up space.",
        ]:
            l = QLabel(s); l.setObjectName("Hint"); iv.addWidget(l)
        v.addWidget(info)
        tip = QLabel("💡  First time?  Tools → Create demo files  to try me safely.")
        tip.setObjectName("Hint"); tip.setWordWrap(True); v.addWidget(tip)
        v.addStretch(1)
        return p

    def _page_pick(self):
        p = QWidget(); v = QVBoxLayout(p); v.setSpacing(14)
        t = QLabel("Which folder should I look through?"); t.setObjectName("Section")
        v.addWidget(t)
        h = QLabel("Pick a folder. Nothing happens until you click 'Scan'.")
        h.setObjectName("Hint"); h.setWordWrap(True); v.addWidget(h)
        c = card(); cv = QVBoxLayout(c); cv.setContentsMargins(24,24,24,24); cv.setSpacing(14)
        self.folder_label = QLabel("No folder selected yet")
        self.folder_label.setStyleSheet("font-size:16px; font-weight:600; color:#1e2430;")
        self.folder_label.setWordWrap(True)
        cv.addWidget(self.folder_label)
        row = QHBoxLayout()
        b1 = QPushButton("📁  Choose folder…"); b1.clicked.connect(self._pick_folder)
        b2 = QPushButton("🏠  Home"); b2.setObjectName("Ghost")
        b2.clicked.connect(lambda: self._set_folder(HOME))
        b3 = QPushButton("📥  Downloads"); b3.setObjectName("Ghost")
        b3.clicked.connect(lambda: self._set_folder(os.path.join(HOME, "Downloads")))
        b4 = QPushButton("🌍  Entire system"); b4.setObjectName("Ghost")
        b4.clicked.connect(self._preset_whole_system)
        row.addWidget(b1); row.addWidget(b2); row.addWidget(b3); row.addWidget(b4); row.addStretch(1)
        cv.addLayout(row)
        self.deep_check = QCheckBox("Deep scan — include hidden files and system folders")
        self.deep_check.stateChanged.connect(self._on_deep_toggle)
        cv.addWidget(self.deep_check)

        if IS_ROOT:
            al = QLabel("🔓  Already running as administrator.")
            al.setObjectName("Admin"); cv.addWidget(al)
            self.admin_check = None
            self.admin_method = None
        else:
            self.admin_check = QCheckBox(
                "🔓  Run with admin rights  (needed for /var, /usr, /etc)")
            self.admin_check.setToolTip(
                "When enabled, the app relaunches as root. You'll be asked for "
                "your password once.")
            self.admin_check.stateChanged.connect(self._update_pick_warning)
            cv.addWidget(self.admin_check)

            mrow = QHBoxLayout(); mrow.addSpacing(28)
            lbl = QLabel("Method:"); lbl.setObjectName("Hint"); mrow.addWidget(lbl)
            self.admin_method = QComboBox()
            self.admin_method.addItems([
                "Terminal  — most reliable, works on every Linux Mint setup",
                "System dialog (pkexec)  — small system window",
                "Graphical sudo (zenity/ssh-askpass)",
            ])
            self.admin_method.setVisible(False)
            self.admin_method.currentIndexChanged.connect(self._update_pick_warning)
            mrow.addWidget(self.admin_method, 1)
            cv.addLayout(mrow)

            test_row = QHBoxLayout(); test_row.addSpacing(28)
            b_test = QPushButton("🧪  Test elevation"); b_test.setObjectName("Browse")
            b_test.clicked.connect(self._test_admin_method)
            test_row.addWidget(b_test); test_row.addStretch(1)
            cv.addLayout(test_row)

            self.admin_check.stateChanged.connect(
                lambda s: self.admin_method.setVisible(bool(s)))

        self.warn_frame = QFrame(); self.warn_frame.setObjectName("Warn")
        self.warn_frame.setVisible(False)
        wv = QVBoxLayout(self.warn_frame); wv.setContentsMargins(16,12,16,12)
        self.warn_label = QLabel(""); self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet("color:#7a5a10; font-weight:600;")
        wv.addWidget(self.warn_label); cv.addWidget(self.warn_frame)

        v.addWidget(c)
        hint2 = QLabel("🔒  Games, PrismLauncher instances, Minecraft saves, and .jar "
                       "files are always skipped — even in deep mode.")
        hint2.setObjectName("Hint"); hint2.setWordWrap(True); v.addWidget(hint2)
        v.addStretch(1)
        return p

    def _on_deep_toggle(self, state):
        self.deep_mode = bool(state)
        self._update_pick_warning()

    def _update_pick_warning(self):
        msgs = []
        if self.deep_mode:
            msgs.append("⚠  Deep scan is on — hidden folders and system paths are walked. "
                        "This can take 5–30 minutes.")
        if self.admin_check is not None and self.admin_check.isChecked():
            idx = self.admin_method.currentIndex() if self.admin_method else 0
            if idx == 0:
                msgs.append("🔓  Admin mode: Terminal. A terminal window will open "
                            "and sudo will ask for your password there.")
            elif idx == 1:
                msgs.append("🔓  Admin mode: system dialog (pkexec). Type password once.")
            else:
                msgs.append("🔓  Admin mode: graphical sudo. Needs zenity installed.")
        if msgs:
            self.warn_label.setText("\n\n".join(msgs))
            self.warn_frame.setVisible(True)
        else:
            self.warn_frame.setVisible(False)

    def _page_scan(self):
        p = QWidget(); v = QVBoxLayout(p); v.setSpacing(14); v.addStretch(1)
        t = QLabel("Scanning…"); t.setObjectName("Section"); t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        self.scan_status = QLabel("Getting ready"); self.scan_status.setObjectName("Hint")
        self.scan_status.setAlignment(Qt.AlignCenter); v.addWidget(self.scan_status)
        self.scan_bar = QProgressBar(); self.scan_bar.setRange(0, 100)
        self.scan_bar.setMaximumWidth(640); self.scan_bar.setMinimumHeight(20)
        bw = QHBoxLayout(); bw.addStretch(1); bw.addWidget(self.scan_bar); bw.addStretch(1)
        v.addLayout(bw)
        self.scan_counter = QLabel("Counting files…"); self.scan_counter.setObjectName("Hint")
        self.scan_counter.setAlignment(Qt.AlignCenter); v.addWidget(self.scan_counter)
        self.scan_curdir = QLabel(""); self.scan_curdir.setObjectName("Mono")
        self.scan_curdir.setAlignment(Qt.AlignCenter); v.addWidget(self.scan_curdir)
        self.scan_eta = QLabel(""); self.scan_eta.setObjectName("Hint")
        self.scan_eta.setAlignment(Qt.AlignCenter); v.addWidget(self.scan_eta)
        live = card(); lv = QHBoxLayout(live); lv.setContentsMargins(24,20,24,20)
        self.live_files = make_stat("0", "Suspicious files")
        self.live_size  = make_stat("0 MB", "Reclaimable")
        lv.addWidget(self.live_files); lv.addWidget(self.live_size)
        lw = QHBoxLayout(); lw.addStretch(1); lw.addWidget(live); lw.addStretch(1)
        v.addLayout(lw); v.addStretch(1)
        row = QHBoxLayout(); row.addStretch(1)
        self.btn_cancel = QPushButton("Cancel"); self.btn_cancel.setObjectName("Ghost")
        self.btn_cancel.clicked.connect(self._cancel_scan); row.addWidget(self.btn_cancel)
        v.addLayout(row)
        return p

    def _page_review(self):
        p = QWidget(); v = QVBoxLayout(p); v.setSpacing(12)
        t = QLabel("Here's what I found 🔍"); t.setObjectName("Section"); v.addWidget(t)
        h = QLabel("Uncheck anything you want to keep.  Right-click a row to teach me a rule.")
        h.setObjectName("Hint"); h.setWordWrap(True); v.addWidget(h)
        s = card(); sv = QHBoxLayout(s); sv.setContentsMargins(24,20,24,20)
        self.rev_count = make_stat("0", "Files flagged")
        self.rev_size  = make_stat("0 MB", "You can free up")
        self.rev_prot  = make_stat("Auto", "Games protected")
        sv.addWidget(self.rev_count); sv.addWidget(self.rev_size); sv.addWidget(self.rev_prot)
        v.addWidget(s)
        bar = QHBoxLayout()
        b_all  = QPushButton("Select all");  b_all.setObjectName("Ghost")
        b_none = QPushButton("Deselect all"); b_none.setObjectName("Ghost")
        b_rules = QPushButton("🛡  Manage rules…"); b_rules.setObjectName("Ghost")
        b_all.clicked.connect(lambda: self._toggle_all(True))
        b_none.clicked.connect(lambda: self._toggle_all(False))
        b_rules.clicked.connect(self._manage_rules)
        self.live_total = QLabel(""); self.live_total.setObjectName("Hint")
        bar.addWidget(b_all); bar.addWidget(b_none); bar.addWidget(b_rules)
        bar.addStretch(1); bar.addWidget(self.live_total)
        v.addLayout(bar)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["✔", "File", "Location", "Count", "Size", "Age", "Why"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40); self.table.setColumnWidth(2, 240)
        self.table.setColumnWidth(3, 60); self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 90); self.table.setColumnWidth(6, 240)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        v.addWidget(self.table, 1)
        return p

    def _page_cleanup(self):
        p = QWidget(); v = QVBoxLayout(p); v.setSpacing(16); v.addStretch(1)
        t = QLabel("Ready to clean up"); t.setObjectName("Section"); t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        self.clean_msg = QLabel(""); self.clean_msg.setObjectName("Hint")
        self.clean_msg.setAlignment(Qt.AlignCenter); self.clean_msg.setWordWrap(True)
        v.addWidget(self.clean_msg)
        self.clean_bar = QProgressBar(); self.clean_bar.setRange(0, 100)
        self.clean_bar.setMaximumWidth(600); self.clean_bar.setMinimumHeight(20)
        bw = QHBoxLayout(); bw.addStretch(1); bw.addWidget(self.clean_bar); bw.addStretch(1)
        v.addLayout(bw); v.addStretch(1)
        return p

    def _page_done(self):
        p = QWidget(); v = QVBoxLayout(p); v.setSpacing(18); v.addStretch(1)
        t = QLabel("All done! ✨"); t.setObjectName("Hero"); t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        self.done_msg = QLabel(""); self.done_msg.setObjectName("SubHero")
        self.done_msg.setAlignment(Qt.AlignCenter); self.done_msg.setWordWrap(True)
        v.addWidget(self.done_msg)
        c = card(); cv = QHBoxLayout(c); cv.setContentsMargins(24,20,24,20)
        self.done_freed = make_stat("0 MB", "Space freed")
        self.done_files = make_stat("0", "Files removed")
        self.done_kept  = make_stat("0", "Files kept")
        cv.addWidget(self.done_freed); cv.addWidget(self.done_files); cv.addWidget(self.done_kept)
        cw = QHBoxLayout(); cw.addStretch(1); cw.addWidget(c); cw.addStretch(1)
        v.addLayout(cw)
        note = QLabel("Deleted files are moved to Trash — you can restore them "
                      "from Nemo if you change your mind.")
        note.setObjectName("Hint"); note.setAlignment(Qt.AlignCenter)
        v.addWidget(note)

        restore_row = QHBoxLayout(); restore_row.addStretch(1)
        self.btn_restore = QPushButton("↩  Restore last batch from Trash")
        self.btn_restore.setObjectName("Ghost")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._restore_last_batch)
        restore_row.addWidget(self.btn_restore); restore_row.addStretch(1)
        v.addLayout(restore_row)
        v.addStretch(1)
        return p

    # ---------------- navigation ----------------
    def _set_step(self, i):
        self.step = i
        self.stack.setCurrentIndex(i)
        for j, lbl in enumerate(self.step_labels):
            if j == i:
                lbl.setStyleSheet("color:white; background:#2f7ad6; font-weight:700;"
                                  "padding:8px 12px; border-radius:6px;")
            else:
                lbl.setStyleSheet("color:#5a6478; padding:8px 12px; border-radius:6px;")
        self.btn_back.setVisible(i not in (0, 2, 4, 5))
        self._update_next_button()

    def _update_next_button(self):
        i = self.step
        if i == 0:
            self.btn_next.setText("Get Started  →"); self.btn_next.setEnabled(True)
        elif i == 1:
            self.btn_next.setText("Scan now  →"); self.btn_next.setEnabled(bool(self.folder))
        elif i == 3:
            n, sz = self._checked_summary()
            self.btn_next.setText(f"Free up {self._human(sz)}  →")
            self.btn_next.setEnabled(n > 0)
        elif i == 5:
            self.btn_next.setText("Scan another folder"); self.btn_next.setEnabled(True)
        else:
            self.btn_next.setEnabled(False)

    def _go_next(self):
        i = self.step
        if i == 0: self._go_to(1)
        elif i == 1: self._start_scan()
        elif i == 3: self._confirm_and_delete()
        elif i == 5:
            self.folder = None; self.folder_label.setText("No folder selected yet")
            self._go_to(1)

    def _go_back(self):
        if self.step == 3: self._go_to(1)
        elif self.step == 1: self._go_to(0)

    def _go_to(self, i): self._set_step(i)

    # ---------------- folder ----------------
    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose a folder", HOME)
        if d: self._set_folder(d)

    def _set_folder(self, path):
        self.folder = path
        self.folder_label.setText(f"📂  {path}")
        self._update_next_button()

    def _preset_whole_system(self):
        self._set_folder("/")
        self.deep_check.setChecked(True)
        if self.admin_check is not None and not IS_ROOT:
            self.admin_check.setChecked(True)
        self._go_to(1); self._update_pick_warning()

    def _relaunch_admin(self):
        folder = self.folder or HOME
        deep = self.deep_mode
        method = self._current_admin_method()
        if QMessageBox.question(
            self, "Relaunch as administrator?",
            f"Method: {method}\nFolder: {folder}\n"
            f"Deep scan: {'on' if deep else 'off'}\n\n"
            "The app will try to open a root instance.",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._do_admin_relaunch(folder, deep, method)

    def _test_admin_method(self):
        method = self._current_admin_method()
        fd, out = tempfile.mkstemp(prefix="ai-cleaner-test-", suffix=".log")
        os.close(fd)
        if method == "terminal":
            term = _find_terminal()
            if not term:
                QMessageBox.critical(self, "No terminal",
                    "Couldn't find a terminal emulator.")
                return
            fd2, tmp = tempfile.mkstemp(prefix="ai-cleaner-testterm-", suffix=".sh")
            os.close(fd2)
            with open(tmp, "w") as f:
                f.write("#!/bin/bash\n")
                f.write("echo 'Testing sudo…'\n")
                f.write(f"sudo -E id 2>&1 | tee {shlex.quote(out)}\n")
                f.write("echo '=== done. Press Enter. ==='\n")
                f.write("read _\n")
                f.write(f"rm -f {shlex.quote(tmp)}\n")
            os.chmod(tmp, 0o755)
            try:
                subprocess.Popen(_terminal_argv(term, tmp), close_fds=True)
            except Exception as e:
                QMessageBox.critical(self, "Launch failed", str(e)); return
            QMessageBox.information(self, "Terminal opened",
                "A terminal window just opened.\n\n"
                "Type your password there. If you see  uid=0(root)…, "
                "the terminal method works.")
        else:
            QMessageBox.information(self, "Test",
                "For pkexec / askpass, testing opens the real dialog. "
                "Use the scan itself — log at:\n"
                f"{os.path.join(CONFIG_DIR, 'admin-launch.log')}")

    # ---------------- demo ----------------
    def _make_demo(self):
        d = QFileDialog.getExistingDirectory(self, "Where to create the demo?", HOME)
        if not d: return
        target = Path(d) / "ai_cleaner_demo"
        try:
            info = create_demo_files(target)
        except Exception as e:
            QMessageBox.critical(self, "Oops", f"Couldn't create demo files:\n{e}")
            return
        QMessageBox.information(self, "Demo files created 🎉",
            f"Created {info['junk']} junk, {info['keepers']} keepers, "
            f"{info['protected']} protected.\n\nLocation:\n{info['path']}")
        self._set_folder(info["path"]); self._go_to(1)

    # ---------------- rules ----------------
    def _manage_rules(self):
        if not hasattr(self.rules, "settings") or self.rules.settings is None:
            self.rules.settings = {"skip_rule_confirmation": False}
        try:
            dlg = RulesDialog(self.rules, self)
            dlg.rules_changed.connect(self._on_rules_changed)
            dlg.exec_()
        except Exception as e:
            import traceback; traceback.print_exc()
            QMessageBox.critical(self, "Rules manager failed",
                f"{type(e).__name__}: {e}")
            return
        for rule in self.rules.rules:
            reinforce_agent_from_rule(self.agent, rule)
        self.agent.save()
        self._on_rules_changed()
        self._refresh_agent_info()

    def _on_rules_changed(self):
        if self.table.rowCount() > 0:
            self._apply_rules_to_table()
        self._refresh_agent_info()

    def _add_rule_and_train(self, rule):
        try:
            self.rules.add(rule)
            reinforce_agent_from_rule(self.agent, rule)
            self.agent.save()
            self._log(f"Rule added: {RulesManager.describe(rule)}")
            self._apply_rules_to_table()
            self._refresh_agent_info()
        except Exception as e:
            import traceback; traceback.print_exc()
            QMessageBox.critical(self, "Couldn't add rule",
                f"{type(e).__name__}: {e}")

    def _apply_rules_to_table(self):
        removed = 0
        for r in reversed(range(self.table.rowCount())):
            item = self.table.item(r, 1)
            if item is None: continue
            group = item.data(Qt.UserRole)
            if not group: continue
            action, _ = self.rules.match(Path(group[0]["path"]))
            if action == "protect":
                self.table.removeRow(r); removed += 1
        if removed:
            self._log(f"{removed} row(s) hidden by your rules.")
            self._refresh_review_summary()

    def _table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is None: return
        row = item.row()
        name_item = self.table.item(row, 1)
        if name_item is None: return
        group = name_item.data(Qt.UserRole)
        if not group: return
        info = group[0]
        path = Path(info["path"])
        parent = str(path.parent)
        ext = path.suffix.lower()
        stem = path.stem
        menu = QMenu(self)
        keep = menu.addMenu("🛡  Always keep…")
        keep.addAction("This exact file",
                       lambda: self._quick_rule("glob", str(path), "protect"))
        keep.addAction("Every file in this folder",
                       lambda: self._quick_rule("folder", parent, "protect"))
        if ext:
            keep.addAction(f"Every {ext} file on the system",
                           lambda: self._quick_rule("extension", ext, "protect"))
        if len(stem) >= 4:
            keep.addAction(f"Names containing “{stem[:12]}”",
                           lambda: self._quick_rule("name_contains", stem, "protect"))
        flag = menu.addMenu("🗑  Always suggest deleting…")
        flag.addAction("This exact file",
                       lambda: self._quick_rule("glob", str(path), "flag"))
        flag.addAction("Every file in this folder",
                       lambda: self._quick_rule("folder", parent, "flag"))
        if ext:
            flag.addAction(f"Every {ext} file on the system",
                           lambda: self._quick_rule("extension", ext, "flag"))
        if len(stem) >= 4:
            flag.addAction(f"Names containing “{stem[:12]}”",
                           lambda: self._quick_rule("name_contains", stem, "flag"))
        menu.addSeparator()
        menu.addAction("Open rules manager…", self._manage_rules)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _quick_rule(self, rtype, value, action):
        rule = {"type": rtype, "value": value, "action": action,
                "note": "", "enabled": True}
        verb = "always keep" if action == "protect" else "always suggest deleting"
        if not hasattr(self.rules, "settings") or self.rules.settings is None:
            self.rules.settings = {"skip_rule_confirmation": False}
        if self.rules.settings.get("skip_rule_confirmation"):
            self._add_rule_and_train(rule); return
        box = QMessageBox(self)
        box.setWindowTitle("Add rule")
        box.setIcon(QMessageBox.Question)
        box.setText(
            f"Add a rule to {verb}:\n\n"
            f"    {RulesManager.describe(rule)}\n\n"
            "The AI will learn from this too.")
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.Yes)
        cb = QCheckBox("Don't ask me this again — add future rules automatically")
        box.setCheckBox(cb)
        if box.exec_() != QMessageBox.Yes: return
        if cb.isChecked():
            self.rules.settings["skip_rule_confirmation"] = True
            if hasattr(self.rules, "save_settings"):
                self.rules.save_settings()
        self._add_rule_and_train(rule)

    # ---------------- scan ----------------
    def _start_scan(self):
        if not self.folder: return
        if self.admin_check is not None and self.admin_check.isChecked() and not IS_ROOT:
            method = self._current_admin_method()
            if QMessageBox.question(
                self, "Restart as administrator?",
                f"Method: {method}\n\n"
                "The app will try to open a root instance.",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
            self._do_admin_relaunch(self.folder, self.deep_mode, method)
            return
        self.scan_results.clear()
        self.table.setRowCount(0)
        self.scan_bar.setRange(0, 0)
        self.scan_counter.setText("Counting files…")
        self.scan_curdir.setText(""); self.scan_eta.setText("")
        self.scan_status.setText("Preparing…")
        set_bigstat(self.live_files, "0")
        set_bigstat(self.live_size, "0 MB")
        self._go_to(2)
        self.scanner = ScannerThread(self.folder, self.agent, self.rules,
                                     deep_mode=self.deep_mode)
        self.scanner.progress.connect(self._on_progress)
        self.scanner.file_found.connect(self._on_file_found)
        self.scanner.finished_scan.connect(self._on_scan_done)
        self.scanner.status.connect(self.scan_status.setText)
        self.scanner.start()

    def _do_admin_relaunch(self, folder, deep, method):
        sig = os.path.join(tempfile.gettempdir(),
                           f"ai-cleaner-started-{os.getpid()}-{int(time.time())}")
        try:
            if os.path.exists(sig): os.remove(sig)
        except Exception: pass
        _admin_log(f"--- new launch, method={method}, signal={sig} ---")
        ok, err = relaunch_as_admin(folder=folder, deep=deep, method=method,
                                    signal_file=sig, parent=self)
        if not ok:
            _admin_log(f"launch returned False: {err}")
            QMessageBox.critical(self, "Couldn't start admin instance", err)
            return
        wait = QMessageBox(self)
        wait.setWindowTitle("Waiting for admin instance")
        wait.setIcon(QMessageBox.Information)
        wait.setText("A root window should appear shortly.\n\n"
                     "Complete the password prompt there.\n\n"
                     "This window closes automatically once it starts.")
        wait.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        deadline = time.time() + 25.0
        started = False
        loop = QEventLoop()
        timer = QTimer(); timer.setInterval(250)
        def _poll():
            nonlocal started
            if os.path.exists(sig):
                started = True; loop.quit(); return
            if time.time() > deadline:
                loop.quit(); return
        timer.timeout.connect(_poll)
        wait.button(QMessageBox.Cancel).clicked.connect(loop.quit)
        timer.start(); QTimer.singleShot(200, _poll)
        loop.exec_(); timer.stop(); wait.close()
        if started:
            _admin_log("child confirmed — closing launcher")
            self.close()
        else:
            _admin_log("child did NOT confirm within 25s")
            QMessageBox.warning(self, "Admin instance didn't start",
                "The root window didn't appear.\n\n"
                "This window stays open. Try a different method.\n\n"
                f"Log: {os.path.join(CONFIG_DIR, 'admin-launch.log')}")

    def _on_progress(self, scanned, total, cur_dir, eta, is_counting):
        if is_counting:
            self.scan_bar.setRange(0, 0)
            self.scan_counter.setText(f"Counting…  {scanned:,} files so far")
            if cur_dir: self.scan_curdir.setText(self._short_path(cur_dir))
            return
        if total > 0:
            self.scan_bar.setRange(0, 100)
            self.scan_bar.setValue(int(100 * scanned / total))
        else:
            self.scan_bar.setRange(0, 0)
        self.scan_counter.setText(f"{scanned:,} / {total:,} files checked")
        if cur_dir: self.scan_curdir.setText(self._short_path(cur_dir))
        self.scan_eta.setText(f"About {self._duration(eta)} remaining"
                              if eta > 0 else "Estimating…")

    def _on_file_found(self, info):
        self.scan_results.append(info)
        n = len(self.scan_results)
        total = sum(f["size"] for f in self.scan_results)
        set_bigstat(self.live_files, f"{n:,}")
        set_bigstat(self.live_size, self._human(total))

    def _cancel_scan(self):
        if self.scanner:
            self.scanner.stop(); self.scanner.wait(1500)
        self.scan_status.setText("Cancelled."); self._go_to(1)

    def _on_scan_done(self, files):
        self.scan_results = files
        self._fill_review_table()
        if not files:
            QMessageBox.information(self, "Nothing to clean! 🎉",
                "I didn't find anything worth removing here.")
            self._show_done(0, 0, 0); self._go_to(5)
        else:
            self._go_to(3)

    # ---------------- review ----------------
    def _fill_review_table(self):
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(
            ["✔", "File", "Location", "Count", "Size", "Age", "Why"])
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 240)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 90)
        self.table.setColumnWidth(6, 240)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        groups = {}
        for info in self.scan_results:
            key = (info["name"], round(info["size"] / 1024), info["age"])
            groups.setdefault(key, []).append(info)

        ordered = sorted(groups.values(),
                         key=lambda g: -sum(f["size"] for f in g))

        for group in ordered:
            r = self.table.rowCount(); self.table.insertRow(r)
            first = group[0]
            total_size = sum(f["size"] for f in group)
            count = len(group)

            cb = QCheckBox(); cb.setChecked(True)
            cb.stateChanged.connect(self._update_next_button)
            cw = QWidget(); cl = QHBoxLayout(cw)
            cl.addWidget(cb); cl.setAlignment(Qt.AlignCenter); cl.setContentsMargins(0,0,0,0)
            self.table.setCellWidget(r, 0, cw)

            label = "📄  " + first["name"]
            if count > 1:
                label = f"📄  {first['name']}   ×{count}"
            name_item = QTableWidgetItem(label)
            name_item.setData(Qt.UserRole, group)
            name_item.setToolTip("\n".join(f["path"] for f in group[:20])
                                 + ("\n…" if count > 20 else ""))
            self.table.setItem(r, 1, name_item)

            parents = sorted(set(str(Path(f["path"]).parent) for f in group))
            if len(parents) == 1:
                loc_text = self._short_path(parents[0], 55)
            else:
                loc_text = f"{self._short_path(parents[0], 35)}  (+{len(parents)-1} more)"
            loc = QTableWidgetItem(loc_text)
            loc.setForeground(QColor("#5a6478"))
            loc.setToolTip("\n".join(parents))
            self.table.setItem(r, 2, loc)

            cnt = QTableWidgetItem(f"×{count}" if count > 1 else "1")
            cnt.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 3, cnt)

            size_item = QTableWidgetItem(self._human(total_size))
            size_item.setData(Qt.UserRole, total_size)
            self.table.setItem(r, 4, size_item)

            self.table.setItem(r, 5, QTableWidgetItem(self._age(first["age"])))
            why = QTableWidgetItem(first["reason"]); why.setForeground(QColor("#5a6478"))
            self.table.setItem(r, 6, why)

        self._refresh_review_summary()

    def _refresh_review_summary(self):
        n, total = self._checked_summary()
        set_bigstat(self.rev_count, f"{n:,}")
        set_bigstat(self.rev_size, self._human(total))
        self.live_total.setText(f"{n:,} of {len(self.scan_results):,} selected")
        self._update_next_button()

    def _checked_summary(self):
        n = 0; sz = 0
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if not w: continue
            cb = w.findChild(QCheckBox)
            if cb and cb.isChecked():
                group = self.table.item(r, 1).data(Qt.UserRole) or []
                n += len(group)
                sz += sum(f["size"] for f in group)
        return n, sz

    def _toggle_all(self, state):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w:
                cb = w.findChild(QCheckBox)
                if cb: cb.setChecked(state)
        self._refresh_review_summary()

    # ---------------- delete ----------------
    def _confirm_and_delete(self):
        n, sz = self._checked_summary()
        if n == 0: return
        if QMessageBox.question(
            self, "Ready to clean up?",
            f"I'll move {n:,} file(s) to Trash, freeing about {self._human(sz)}.\n\n"
            "You can restore them from Nemo if you change your mind.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        to_delete, to_keep = [], []
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            cb = w.findChild(QCheckBox) if w else None
            group = self.table.item(r, 1).data(Qt.UserRole) or []
            target = to_delete if (cb and cb.isChecked()) else to_keep
            for info in group:
                target.append(info)
        R = 3.0
        for f in to_delete:
            if f.get("state") is not None:
                self.agent.learn(f["state"], 1, +R); self.agent.learn(f["state"], 0, -R)
        for f in to_keep:
            if f.get("state") is not None:
                self.agent.learn(f["state"], 0, +R); self.agent.learn(f["state"], 1, -R)
        self._go_to(4)
        self.clean_msg.setText(f"Trashing {len(to_delete)} file(s)…")
        self.clean_bar.setValue(0); QApplication.processEvents()
        freed = deleted = failed = skipped = 0
        self._last_trashed = []
        for i, f in enumerate(to_delete, 1):
            try:
                p = Path(f["path"]); pl = str(p).lower()
                if any(g and g.lower() in pl for g in GAME_DIRS) \
                   or any(h in pl for h in GAME_PATH_HINTS) \
                   or p.suffix.lower() in GAME_EXTS:
                    skipped += 1; continue
                if p.exists() and p.is_file():
                    rc = subprocess.run(
                        ["gio", "trash", "--", str(p)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ).returncode
                    if rc == 0:
                        self._last_trashed.append(str(p))
                        deleted += 1; freed += f["size"]
                    else:
                        p.unlink()
                        deleted += 1; freed += f["size"]
                else:
                    skipped += 1
            except Exception:
                failed += 1
            if i % 10 == 0 or i == len(to_delete):
                self.clean_bar.setValue(int(100 * i / max(1, len(to_delete))))
                self.clean_msg.setText(f"Trashing {i} of {len(to_delete)}…")
                QApplication.processEvents()
        self.agent.save()
        train_agent(self.agent, episodes=1500)
        self.agent.save()
        self._refresh_agent_info()
        self._show_done(freed, deleted, len(to_keep))
        self._go_to(5)

    def _show_done(self, freed, deleted, kept):
        self.done_msg.setText(
            f"You just freed up {self._human(freed)} by removing {deleted} file(s).")
        set_bigstat(self.done_freed, self._human(freed))
        set_bigstat(self.done_files, f"{deleted:,}")
        set_bigstat(self.done_kept,  f"{kept:,}")
        if getattr(self, "_last_trashed", None):
            self.btn_restore.setEnabled(True)

    def _restore_last_batch(self):
        batch = getattr(self, "_last_trashed", [])
        if not batch:
            QMessageBox.information(self, "Nothing to restore",
                                    "No files were trashed in this session.")
            return
        if QMessageBox.question(
            self, "Restore files?",
            f"Restore {len(batch)} file(s) from Trash back to their original locations?",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        restored = 0; failed = 0
        for path in batch:
            try:
                rc = subprocess.run(
                    ["gio", "trash", "--restore", "--", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                if rc == 0: restored += 1
                else: failed += 1
            except Exception:
                failed += 1
        QMessageBox.information(self, "Done",
            f"Restored {restored} file(s). {failed} failed.")
        self.btn_restore.setEnabled(False)
        self._last_trashed = []

    # ---------------- AI helpers ----------------
    def _train_agent(self, episodes, silent=False):
        if not silent: QApplication.setOverrideCursor(Qt.WaitCursor)
        t0 = time.time()
        train_agent(self.agent, episodes=episodes)
        self.agent.save()
        if not silent:
            QApplication.restoreOverrideCursor()
            QMessageBox.information(self, "AI retrained",
                f"Trained on {episodes:,} examples in {time.time()-t0:.1f}s.")
        self._refresh_agent_info()

    def _reset_agent(self):
        if QMessageBox.question(self, "Reset AI",
            "Forget everything the AI has learned?  (Your rules stay.)",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes: return
        self.agent.reset(); self._train_agent(20000)
        for rule in self.rules.rules:
            reinforce_agent_from_rule(self.agent, rule)
        self.agent.save(); self._refresh_agent_info()

    def _refresh_agent_info(self):
        self.agent_info.setText(
            f"AI has seen {self.agent.visited_states():,} situations.")
        n = len(self.rules.rules)
        if n == 0:
            self.rules_info.setText("No rules yet — right-click a file to add one.")
        else:
            enabled = sum(1 for r in self.rules.rules if r.get("enabled", True))
            self.rules_info.setText(
                f"📋 {enabled} of {n} rule(s) active.\nManage in Tools → Teach the AI.")

    def _log(self, m):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}")

    # ---------------- help ----------------
    def _show_help(self):
        QMessageBox.information(self, "How it works",
            "The cleaner uses reinforcement learning to decide, for each file, "
            "whether to KEEP it or DELETE it.\n\n"
            "🛡  Protected forever: Steam, Lutris, Heroic, Wine, "
            "PrismLauncher / MultiMC instances, .minecraft, all .jar files, "
            "and game data (.pak, .sav, .vpk, .bsa…).\n\n"
            "Teach me anytime: right-click a file in the Review list, or use "
            "Tools → Teach the AI.")

    def _show_teach_guide(self):
        QMessageBox.information(self, "Teach the AI",
            "Two ways to teach me:\n\n"
            "  1.  Right-click any file in the Review list.\n"
            "  2.  Tools → Teach the AI — manage rules…\n\n"
            "For folder rules, click  📁 Browse…  instead of typing the path.\n\n"
            "Rules take priority over the AI. Extension rules also nudge the AI.")

    def _show_about(self):
        admin = "  (administrator)" if IS_ROOT else ""
        QMessageBox.about(self, "About AI File Cleaner",
            f"<h3>AI File Cleaner — Wizard Edition v7{admin}</h3>"
            "<p>RL-powered cleaner with in-app rule training and admin mode.</p>"
            "<p>Runs entirely on your machine. No network, no cloud.</p>")

    # ---------------- formatters ----------------
    @staticmethod
    def _human(b):
        b = float(b)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if b < 1024: return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} PB"

    @staticmethod
    def _age(days):
        if days < 1:   return "today"
        if days < 30:  return f"{days}d old"
        if days < 365: return f"{days//30}mo old"
        return f"{days//365}y old"

    @staticmethod
    def _duration(sec):
        sec = int(sec)
        if sec < 60: return f"{sec} seconds"
        m, s = divmod(sec, 60)
        if m < 60: return f"{m} min"
        h, m = divmod(m, 60)
        return f"{h}h {m}m"

    @staticmethod
    def _short_path(p, maxlen=80):
        p = str(p)
        return p if len(p) <= maxlen else "…" + p[-(maxlen - 1):]

    def closeEvent(self, e):
        if self.scanner and self.scanner.isRunning():
            self.scanner.stop(); self.scanner.wait(1500)
        try: self.agent.save()
        except Exception: pass
        try: self.rules.save()
        except Exception: pass
        e.accept()

# ======================================================================
def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--admin", action="store_true")
    ap.add_argument("--folder", default=None)
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--signal-file", default=None)
    ap.add_argument("--help", action="help")
    args, _ = ap.parse_known_args()

    if args.signal_file:
        try:
            with open(args.signal_file, "w") as f:
                f.write(str(os.getpid()))
            _admin_log(f"child booted, pid={os.getpid()}, signal written")
        except Exception as e:
            _admin_log(f"child could not write signal: {e}")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("AI File Cleaner")
    app.setDesktopFileName("ai-file-cleaner")
    app.setStyleSheet(QSS)
    w = Wizard(admin_mode=args.admin,
               start_folder=args.folder,
               start_deep=args.deep)
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()