"""Dialog to add a single rule."""

import os

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from ..config import HOME
from ..protection import expand_user_path


class RuleEditor(QDialog):
    def __init__(self, parent=None, preset=None):
        super().__init__(parent)
        self.setWindowTitle("Add a rule")
        self.resize(620, 460)
        self.result_rule = None
        self._build(preset or {})

    def _build(self, preset):
        v = QVBoxLayout(self)
        v.setSpacing(12)
        v.setContentsMargins(24, 24, 24, 20)

        t = QLabel("New rule")
        t.setObjectName("Section")
        v.addWidget(t)

        v.addWidget(QLabel("1.  What should I do?"))
        self.rb_protect = QRadioButton("🛡  Always keep these files — never touch them")
        self.rb_flag = QRadioButton("🗑  Always suggest deleting these files")
        self.rb_protect.setChecked(True)
        v.addWidget(self.rb_protect)
        v.addWidget(self.rb_flag)

        v.addWidget(QLabel("2.  How do I recognize them?"))
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(
            [
                "Files inside a folder…",
                "Files with a file extension…",
                "Files whose name contains…",
                "Files matching a wildcard…",
            ]
        )
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

        self.hint = QLabel("")
        self.hint.setObjectName("Hint")
        self.hint.setWordWrap(True)
        v.addWidget(self.hint)

        v.addWidget(QLabel("3.  (Optional) A short note for yourself:"))
        self.inp_note = QLineEdit()
        self.inp_note.setPlaceholderText("e.g. Icon theme files — do not delete")
        v.addWidget(self.inp_note)

        if preset:
            if preset.get("action") == "flag":
                self.rb_flag.setChecked(True)
            m = {"folder": 0, "extension": 1, "name_contains": 2, "glob": 3}
            if preset.get("type") in m:
                self.cmb_type.setCurrentIndex(m[preset["type"]])
            self.inp_value.setText(preset.get("value", ""))
            self.inp_note.setText(preset.get("note", ""))

        self._on_type_change()
        v.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        bc = QPushButton("Cancel")
        bc.setObjectName("Ghost")
        bc.clicked.connect(self.reject)
        bo = QPushButton("Save rule")
        bo.clicked.connect(self._ok)
        row.addWidget(bc)
        row.addWidget(bo)
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
        if idx == 0:
            self.inp_value.setPlaceholderText("Path to folder… (or Browse)")
        elif idx == 1:
            self.inp_value.setPlaceholderText(".deb")
        elif idx == 2:
            self.inp_value.setPlaceholderText("backup_")
        else:
            self.inp_value.setPlaceholderText("*.bak")

    def _browse(self):
        start = self.inp_value.text().strip() or HOME
        if start.startswith("~"):
            start = expand_user_path(start)
        if not os.path.isdir(start):
            start = HOME
        d = QFileDialog.getExistingDirectory(
            self, "Pick a folder to protect", start, QFileDialog.ShowDirsOnly
        )
        if d:
            self.inp_value.setText(d)

    def _ok(self):
        types = ["folder", "extension", "name_contains", "glob"]
        val = self.inp_value.text().strip()
        if not val:
            QMessageBox.warning(
                self, "Missing value", "Please enter a value so I know what to match."
            )
            return
        self.result_rule = {
            "type": types[self.cmb_type.currentIndex()],
            "value": val,
            "action": "protect" if self.rb_protect.isChecked() else "flag",
            "note": self.inp_note.text().strip(),
            "enabled": True,
        }
        self.accept()
