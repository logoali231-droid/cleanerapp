"""Small Windows compatibility layer for the existing Qt wizard.

The main wizard remains shared with Linux. This module only replaces the
platform-specific UI/elevation/trash operations when running on Windows.
"""

import os
import time
from collections import Counter
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QCheckBox, QMessageBox

from ..platform import IS_WINDOWS, open_recycle_bin, relaunch_as_admin, send_to_trash
from ..protection import GAME_DIRS, GAME_EXTS, GAME_PATH_HINTS
from ..agent import train_agent
from ..utils import human


def install_windows_compat(Wizard):
    """Patch the shared Wizard class with Windows-native behavior."""
    if not IS_WINDOWS:
        return

    original_init = Wizard.__init__

    def windows_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        if getattr(self, "admin_check", None) is not None:
            self.admin_check.setText("🔓  Run as administrator  (Windows UAC)")
            self.admin_check.setToolTip(
                "Windows will show a UAC confirmation dialog when elevated access is needed."
            )
        if getattr(self, "admin_method", None) is not None:
            self.admin_method.setVisible(False)
            self.admin_method.setEnabled(False)
        for box in self.findChildren(QCheckBox):
            if "test elevation" in box.text().lower():
                box.setText("🧪  Test Windows UAC")

    def windows_current_admin_method(self):
        return "Windows UAC"

    def windows_preset_whole_system(self):
        from ..platform import whole_system_roots
        roots = whole_system_roots()
        if roots:
            self._set_folder(str(roots[0]))
        self.deep_check.setChecked(True)
        if getattr(self, "admin_check", None) is not None:
            self.admin_check.setChecked(True)
        self._go_to(1)
        self._update_pick_warning()

    def windows_do_admin_relaunch(self, folder, deep, _method=None):
        sig = os.path.join(
            __import__("tempfile").gettempdir(),
            f"ai-cleaner-started-{os.getpid()}-{int(time.time())}",
        )
        try:
            if os.path.exists(sig):
                os.remove(sig)
        except OSError:
            pass
        try:
            ok, err = relaunch_as_admin(folder=folder, deep=deep, signal_file=sig)
        except Exception as exc:
            ok, err = False, str(exc)
        if not ok:
            QMessageBox.critical(self, "Couldn't start administrator mode", err)
            return
        QMessageBox.information(
            self,
            "Windows UAC",
            "Windows will open an elevated AI File Cleaner window.\n\n"
            "Approve the UAC prompt and continue there.",
        )

    def windows_confirm_and_delete(self):
        n, sz = self._checked_summary()
        if n == 0:
            return
        if QMessageBox.question(
            self,
            "Ready to clean up?",
            f"I'll move {n:,} file(s) to the Recycle Bin, freeing about {human(sz)}.\n\n"
            "You can restore them later from the Windows Recycle Bin.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        to_delete, to_keep = [], []
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            cb = w.findChild(QCheckBox) if w else None
            group = self.table.item(r, 1).data(Qt.UserRole) or []
            (to_delete if (cb and cb.isChecked()) else to_keep).extend(group)

        R = 3.0
        MAX_BOOST = 10
        delete_counts = Counter(f["state"] for f in to_delete if f.get("state") is not None)
        keep_counts = Counter(f["state"] for f in to_keep if f.get("state") is not None)
        for f in to_delete:
            self.agent.record_decision(f.get("confidence"), accepted=True)
        for f in to_keep:
            self.agent.record_decision(f.get("confidence"), accepted=False)
        for state, count in delete_counts.items():
            weight = min(count, MAX_BOOST)
            self.agent.learn(state, 1, +R * weight)
            self.agent.learn(state, 0, -R * weight)
        for state, count in keep_counts.items():
            weight = min(count, MAX_BOOST)
            self.agent.learn(state, 0, +R * weight)
            self.agent.learn(state, 1, -R * weight)

        self._go_to(4)
        self.clean_msg.setText(f"Moving {len(to_delete)} file(s) to Recycle Bin…")
        self.clean_bar.setValue(0)
        QApplication.processEvents()

        freed = deleted = failed = skipped = 0
        self._last_trashed = []
        for i, f in enumerate(to_delete, 1):
            try:
                p = Path(f["path"])
                pl = str(p).replace("\\", "/").lower()
                if (
                    any(g and str(g).replace("\\", "/").lower() in pl for g in GAME_DIRS)
                    or any(h in pl for h in GAME_PATH_HINTS)
                    or p.suffix.lower() in GAME_EXTS
                ):
                    skipped += 1
                elif p.exists() and p.is_file():
                    send_to_trash(p)
                    self._last_trashed.append(str(p))
                    deleted += 1
                    freed += f["size"]
                else:
                    skipped += 1
            except Exception:
                failed += 1
            if i % 10 == 0 or i == len(to_delete):
                self.clean_bar.setValue(int(100 * i / max(1, len(to_delete))))
                self.clean_msg.setText(f"Moving {i} of {len(to_delete)}…")
                QApplication.processEvents()

        self.agent.save()
        train_agent(self.agent, episodes=1500)
        self.agent.save()
        self._refresh_agent_info()
        self._show_done(freed, deleted, len(to_keep))
        self._go_to(5)
        if failed:
            self._log(f"Recycle Bin: {failed} file(s) could not be moved.")
        if skipped:
            self._log(f"Recycle Bin: {skipped} file(s) were skipped by protection rules.")

    def windows_restore_last_batch(self):
        batch = getattr(self, "_last_trashed", [])
        if not batch:
            QMessageBox.information(
                self,
                "Nothing to restore",
                "No files were sent to the Recycle Bin in this session.",
            )
            return
        if QMessageBox.question(
            self,
            "Restore files?",
            f"{len(batch)} file(s) were sent to the Windows Recycle Bin.\n\n"
            "Open it so you can select them and choose Restore?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        try:
            open_recycle_bin()
            QMessageBox.information(
                self,
                "Recycle Bin opened",
                "Windows Explorer opened the Recycle Bin.\n\n"
                "Select the files, right-click them, and choose Restore.",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Couldn't open Recycle Bin",
                f"Open the Recycle Bin manually.\n\n{exc}",
            )

    Wizard.__init__ = windows_init
    Wizard._current_admin_method = windows_current_admin_method
    Wizard._preset_whole_system = windows_preset_whole_system
    Wizard._do_admin_relaunch = windows_do_admin_relaunch
    Wizard._confirm_and_delete = windows_confirm_and_delete
    Wizard._restore_last_batch = windows_restore_last_batch
