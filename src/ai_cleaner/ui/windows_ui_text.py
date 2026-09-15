"""Windows-only wording for controls inherited from the Linux-first wizard."""

from ..platform import IS_WINDOWS


def install_windows_ui_text(Wizard):
    if not IS_WINDOWS:
        return

    def update_warning(self):
        msgs = []
        if self.deep_mode:
            msgs.append(
                "⚠  Deep scan includes hidden folders and protected Windows locations. "
                "Windows permissions may still cause some files to be skipped."
            )
        if getattr(self, "admin_check", None) is not None and self.admin_check.isChecked():
            msgs.append("🔓  Windows UAC: a confirmation dialog will appear before elevated access.")
        if msgs:
            self.warn_label.setText("\n\n".join(msgs))
            self.warn_frame.setVisible(True)
        else:
            self.warn_frame.setVisible(False)

    Wizard._update_pick_warning = update_warning
