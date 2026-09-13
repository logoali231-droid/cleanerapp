"""Manage all rules in one place."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .rule_editor import RuleEditor


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
        v = QVBoxLayout(self)
        v.setSpacing(12)
        v.setContentsMargins(24, 24, 24, 20)

        t = QLabel("Your rules")
        t.setObjectName("Section")
        v.addWidget(t)
        intro = QLabel(
            "Rules take priority over the AI. You can also right-click any file in the "
            "Review list to create a rule on the spot.")
        intro.setObjectName("Hint")
        intro.setWordWrap(True)
        v.addWidget(intro)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "Rule", "Action", "Note", ""])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 36)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 220)
        self.table.setColumnWidth(4, 100)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table, 1)

        self.empty = QLabel("You haven't added any rules yet.")
        self.empty.setObjectName("Hint")
        self.empty.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty)

                # ---------- settings section ----------
        settings_header = QLabel("⚙  Settings")
        settings_header.setStyleSheet(
            "color:#5a6478; font-weight:700; padding-top:6px;")
        v.addWidget(settings_header)

        # screenshot age
        age_row = QHBoxLayout()
        age_lbl = QLabel("Flag screenshots older than:")
        age_row.addWidget(age_lbl)

        self.sp_screenshot_age = QSpinBox()
        self.sp_screenshot_age.setRange(0, 3650)
        self.sp_screenshot_age.setSuffix(" days")
        self.sp_screenshot_age.setSpecialValueText("Never (off)")
        self.sp_screenshot_age.setToolTip(
            "Screenshots in known folders (Pictures/Screenshots, etc.) older "
            "than this are flagged automatically.\n\n"
            "Set to 0 to disable screenshot detection entirely.")
        self.sp_screenshot_age.setValue(int(
            self.manager.settings.get("screenshot_min_age_days", 30)))
        self.sp_screenshot_age.valueChanged.connect(self._toggle_screenshot_age)
        age_row.addWidget(self.sp_screenshot_age)
        age_row.addStretch(1)
        v.addLayout(age_row)

                # AI confidence threshold
        conf_row = QHBoxLayout()
        conf_row.addWidget(QLabel("Only show AI suggestions with confidence ≥"))
        self.sp_min_conf = QDoubleSpinBox()
        self.sp_min_conf.setRange(-1.0, 100.0)
        self.sp_min_conf.setSingleStep(0.5)
        self.sp_min_conf.setDecimals(1)
        self.sp_min_conf.setSpecialValueText("Auto (AI decides)")
        self.sp_min_conf.setToolTip(
            "How confident the AI must be before it shows you a file.\n\n"
            "Auto (AI decides) = the agent looks at how often you've accepted "
            "its past suggestions and derives the threshold itself.\n\n"
            "Set any other value to override with a fixed threshold.")
        self.sp_min_conf.setValue(float(
            self.manager.settings.get("min_confidence", -1)))
        self.sp_min_conf.valueChanged.connect(self._toggle_min_confidence)
        conf_row.addWidget(self.sp_min_conf)
        conf_row.addStretch(1)
        v.addLayout(conf_row)

        # skip confirmation
        srow = QHBoxLayout()
        self.cb_skip = QCheckBox("Add new rules without asking for confirmation")
        self.cb_skip.setChecked(bool(self.manager.settings.get("skip_rule_confirmation")))
        self.cb_skip.stateChanged.connect(self._toggle_skip)
        srow.addWidget(self.cb_skip)
        srow.addStretch(1)
        v.addLayout(srow)

        row = QHBoxLayout()
        b_add = QPushButton("＋  Add a rule…")
        b_add.clicked.connect(self._add_rule)
        b_close = QPushButton("Done")
        b_close.setObjectName("Ghost")
        b_close.clicked.connect(self.accept)
        row.addWidget(b_add)
        row.addStretch(1)
        row.addWidget(b_close)
        v.addLayout(row)

    def _toggle_skip(self, state):
        self.manager.settings["skip_rule_confirmation"] = bool(state)
        self.manager.save_settings()
    def _toggle_screenshot_age(self, value):
        self.manager.settings["screenshot_min_age_days"] = int(value)
        self.manager.save_settings()

    def _toggle_min_confidence(self, value):
        self.manager.settings["min_confidence"] = float(value)
        self.manager.save_settings()

    def _refresh(self):
        self.table.setRowCount(0)
        if not self.manager.rules:
            self.empty.setVisible(True)
            return
        self.empty.setVisible(False)
        for i, rule in enumerate(self.manager.rules):
            r = self.table.rowCount()
            self.table.insertRow(r)

            cb = QCheckBox()
            cb.setChecked(rule.get("enabled", True))
            cb.stateChanged.connect(lambda st, idx=i: self._toggle(idx, st))
            cw = QWidget()
            cl = QHBoxLayout(cw)
            cl.addWidget(cb)
            cl.setAlignment(Qt.AlignCenter)
            cl.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, 0, cw)

            desc = self.manager.describe(rule)
            if rule.get("default"):
                desc = "★  " + desc
            item = QTableWidgetItem(desc)
            if rule.get("default"):
                item.setForeground(QColor("#7a5a10"))
            self.table.setItem(r, 1, item)

            act = "Keep" if rule.get("action") == "protect" else "Suggest delete"
            ai = QTableWidgetItem(act)
            ai.setForeground(QColor("#2f7ad6" if act == "Keep" else "#e04b4b"))
            self.table.setItem(r, 2, ai)

            self.table.setItem(r, 3, QTableWidgetItem(rule.get("note", "")))

            b_del = QPushButton("Remove")
            b_del.setObjectName("Ghost")
            b_del.clicked.connect(lambda _, idx=i: self._delete(idx))
            self.table.setCellWidget(r, 4, b_del)

    def _toggle(self, idx, state):
        if 0 <= idx < len(self.manager.rules):
            self.manager.rules[idx]["enabled"] = bool(state)
            self.manager.save()
            self.rules_changed.emit()

    def _delete(self, idx):
        self.manager.remove(idx)
        self._refresh()
        self.rules_changed.emit()

    def _add_rule(self):
        dlg = RuleEditor(self)
        if dlg.exec_() == QDialog.Accepted and dlg.result_rule:
            self.manager.add(dlg.result_rule)
            self._refresh()
            self.rules_changed.emit()


Qt_AlignCenter = _Qt.AlignCenter