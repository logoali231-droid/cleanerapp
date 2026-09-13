"""Background scanner thread."""

import os
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from .protection import (
    GAME_DIRS,
    GAME_EXTS,
    GAME_PATH_HINTS,
    in_pseudo_fs,
    in_system_path,
    is_dpkg_owned,
    is_screenshot,
    sniff_file_kind,
)
from .state import extract_state, plain_reason

# Screenshots older than this many days get flagged automatically.
# Change to taste. 30 is a good balance — recent ones stay safe.
SCREENSHOT_MIN_AGE_DAYS = 30


class ScannerThread(QThread):
    progress = pyqtSignal(
        int, int, str, float, bool
    )  # scanned, total, cur, eta, counting
    file_found = pyqtSignal(dict)
    finished_scan = pyqtSignal(list)
    status = pyqtSignal(str)

    def __init__(self, root_path, agent, rules, deep_mode=False):
        super().__init__()
        self.root_path = root_path
        self.agent = agent
        self.rules = rules
        self.deep_mode = deep_mode
        self._running = True

    def stop(self):
        self._running = False

    @staticmethod
    def _is_protected(path):
        p = str(path).lower()
        if any(g and g.lower() in p for g in GAME_DIRS):
            return True
        if any(h in p for h in GAME_PATH_HINTS):
            return True
        return path.suffix.lower() in GAME_EXTS

    def _should_prune_dir(self, dirpath, dirname):
        full = os.path.join(dirpath, dirname)
        if in_pseudo_fs(full):
            return True
        if in_system_path(full):
            return True
        if not self.deep_mode and dirname.startswith("."):  # noqa: SIM102
            if dirname not in (".local", ".cache"):
                return True
        low = full.lower()
        if any(g and g.lower() in low for g in GAME_DIRS):
            return True
        return bool(any(h in low for h in GAME_PATH_HINTS))

    def _count_files(self, root):
        n = 0
        t_last = time.time()
        for dp, dns, fns in os.walk(root, onerror=lambda e: None):
            if not self._running:
                break
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
            self.finished_scan.emit([])
            return
        self.status.emit(f"Analyzing {total:,} files…")

        # Read the user's screenshot-age preference once at scan start.
        # 0 means "don't flag screenshots at all".

        screenshot_age_days = int(
            self.rules.settings.get("screenshot_min_age_days", SCREENSHOT_MIN_AGE_DAYS)
        )

        # Confidence threshold: -1 = let the AI decide from its calibration;
        # any other value = manual override. Log both so you can see it.
        manual = float(self.rules.settings.get("min_confidence", -1))
        if manual < 0:
            min_confidence = self.agent.dynamic_threshold()
            self.status.emit(
                f"AI-derived confidence threshold: {min_confidence:.2f} "
                f"({self.agent.calibration_summary()})"
            )
        else:
            min_confidence = manual
            self.status.emit(f"Manual confidence threshold: {min_confidence:.2f}")

        results = []
        scanned = 0
        t0 = time.time()
        last_emit = 0.0

        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            if not self._running:
                break
            dirnames[:] = [
                d for d in dirnames if not self._should_prune_dir(dirpath, d)
            ]

            for fname in filenames:
                if not self._running:
                    break
                scanned += 1
                fpath = Path(dirpath) / fname

                # 1. rules first
                rule_action, rule = self.rules.match(fpath)
                if rule_action == "protect":
                    continue
                if rule_action == "flag":
                    try:
                        st = fpath.stat()
                        info = {
                            "path": str(fpath),
                            "name": fpath.name,
                            "size": st.st_size,
                            "age": int((time.time() - st.st_mtime) / 86400.0),
                            "state": None,
                            "confidence": 999.0,
                            "reason": rule.get("note")
                            or f"Your rule: {rule.get('value', '')}",
                        }
                        results.append(info)
                        self.file_found.emit(info)
                    except (PermissionError, OSError):
                        pass
                    continue

                # 2. hardcoded protection + sniffing
                try:
                    if not fpath.is_file():
                        continue
                    if self._is_protected(fpath):
                        continue
                    if in_system_path(fpath):
                        continue
                    if is_dpkg_owned(fpath):
                        continue

                    kind, _preview = sniff_file_kind(fpath)
                    if kind in ("text-code", "binary-exec", "unreadable"):
                        continue

                    st = fpath.stat()
                    size = st.st_size
                    age = (time.time() - st.st_mtime) / 86400.0
                    state = extract_state(fpath, size, age)

                    # -- Screenshot shortcut: heuristic, not AI --
                    if (
                        screenshot_age_days > 0
                        and is_screenshot(fpath)
                        and age > screenshot_age_days
                    ):
                        info = {
                            "path": str(fpath),
                            "name": fpath.name,
                            "size": size,
                            "age": int(age),
                            "state": state,
                            "confidence": 999.0,
                            "reason": (
                                f"An old screenshot "
                                f"({int(age)} days) — probably no longer needed"
                            ),
                        }
                        results.append(info)
                        self.file_found.emit(info)
                        continue

                    if self.agent.act(state, explore=False) == 1:
                        conf = self.agent.confidence(state)
                        if min_confidence > 0 and conf < min_confidence:
                            continue
                        info = {
                            "path": str(fpath),
                            "name": fpath.name,
                            "size": size,
                            "age": int(age),
                            "state": state,
                            "confidence": conf,
                            "reason": plain_reason(fpath, size, int(age)),
                        }
                        results.append(info)
                        self.file_found.emit(info)
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
