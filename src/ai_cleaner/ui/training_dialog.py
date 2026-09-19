"""Full import dialog: preview, column mapping, options, progress."""
import traceback
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QComboBox, QGroupBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QProgressBar, QTextEdit,
    QMessageBox, QHeaderView, QAbstractItemView, QSplitter,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor

from ..training import TrainingSession, ImportOptions
from ..training.schema import COLUMN_ALIASES


MAPPABLE_FIELDS = [
    ("extension",    "Extension"),
    ("size_bytes",   "Size (bytes)"),
    ("age_days",     "Age (days)"),
    ("location",     "Location"),
    ("label",        "Label"),
    ("weight",       "Weight"),
    ("ext_bucket",   "Ext bucket"),
    ("size_bucket",  "Size bucket"),
    ("age_bucket",   "Age bucket"),
    ("loc_bucket",   "Location bucket"),
]


class TrainerThread(QThread):
    progress = pyqtSignal(int, int, int, dict)   # epoch, total, pct, metrics
    finished_ok = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, session, agent, examples):
        super().__init__()
        self.session = session
        self.agent = agent
        self.examples = examples
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            report = self.session.train(
                self.agent,
                self.examples,
                progress_cb=lambda e, t, p, m:
                    self.progress.emit(e, t, p, m),
                cancel_cb=lambda: self._cancel,
            )
            self.finished_ok.emit(report)
        except Exception as e:
            traceback.print_exc()
            self.failed.emit(f"{type(e).__name__}: {e}")


class TrainingDialog(QDialog):
    def __init__(self, session: TrainingSession, agent, parent=None):
        super().__init__(parent)
        self.session = session
        self.agent = agent
        self.examples = []
        self.trainer = None
        self.setWindowTitle(f"Import training data — {session.path.name}")
        self.resize(1000, 700)
        self._build()
        self._populate()

    # ---------------------------------------------------------------- UI
    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(12)

        if self.session.load_error:
            err = QLabel(f"❌ Could not load file:\n{self.session.load_error}")
            err.setStyleSheet("color:#c0392b; padding:20px;")
            v.addWidget(err)
            btn = QPushButton("Close")
            btn.clicked.connect(self.reject)
            v.addWidget(btn, alignment=Qt.AlignRight)
            return

        splitter = QSplitter(Qt.Vertical)

        # ---- preview + mapping ----
        top = QGroupBox("1.  Columns")
        tv = QVBoxLayout(top)

        info = QLabel(
            f"File: {self.session.path.name}   "
            f"|  {len(self.session.rows):,} rows  "
            f"|  {len(self.session.columns)} columns")
        info.setStyleSheet("color:#5a6478;")
        tv.addWidget(info)

        self.map_table = QTableWidget(len(MAPPABLE_FIELDS), 2)
        self.map_table.setHorizontalHeaderLabels(["Field", "Source column"])
        self.map_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.map_table.verticalHeader().setVisible(False)
        self.map_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tv.addWidget(self.map_table)

        self.preview = QTableWidget(0, len(self.session.columns))
        self.preview.setHorizontalHeaderLabels(self.session.columns)
        self.preview.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.preview.verticalHeader().setVisible(False)
        self.preview.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tv.addWidget(self.preview, 1)

        splitter.addWidget(top)

        # ---- options ----
        opt = QGroupBox("2.  Options")
        ov = QVBoxLayout(opt)

        # dedupe
        drow = QHBoxLayout()
        self.cb_dedupe = QCheckBox("Deduplicate (state, label) pairs")
        self.cb_dedupe.setChecked(True)
        drow.addWidget(self.cb_dedupe)
        self.cmb_dedupe_mode = QComboBox()
        self.cmb_dedupe_mode.addItems(["sum_weights", "keep_first", "vote"])
        drow.addWidget(QLabel("mode:"))
        drow.addWidget(self.cmb_dedupe_mode)
        drow.addStretch(1)
        ov.addLayout(drow)

        # conflicts + balance
        brow = QHBoxLayout()
        self.cb_drop_conflicts = QCheckBox("Drop conflicting states")
        brow.addWidget(self.cb_drop_conflicts)
        brow.addSpacing(20)
        brow.addWidget(QLabel("Balance:"))
        self.cmb_balance = QComboBox()
        self.cmb_balance.addItems(
            ["class_weights", "oversample", "undersample", "none"])
        brow.addWidget(self.cmb_balance)
        brow.addSpacing(20)
        brow.addWidget(QLabel("Max examples:"))
        self.sp_max = QSpinBox()
        self.sp_max.setRange(0, 100_000_000)
        self.sp_max.setSpecialValueText("no cap")
        brow.addWidget(self.sp_max)
        brow.addStretch(1)
        ov.addLayout(brow)

        # training
        trow = QHBoxLayout()
        trow.addWidget(QLabel("Passes:"))
        self.sp_passes = QSpinBox()
        self.sp_passes.setRange(1, 50)
        self.sp_passes.setValue(3)
        trow.addWidget(self.sp_passes)
        trow.addSpacing(20)
        trow.addWidget(QLabel("LR schedule:"))
        self.cmb_lr = QComboBox()
        self.cmb_lr.addItems(
            ["warmup_decay", "cosine", "linear_decay", "constant"])
        trow.addWidget(self.cmb_lr)
        trow.addSpacing(20)
        trow.addWidget(QLabel("Holdout:"))
        self.sp_holdout = QDoubleSpinBox()
        self.sp_holdout.setRange(0.0, 0.5)
        self.sp_holdout.setSingleStep(0.05)
        self.sp_holdout.setDecimals(2)
        self.sp_holdout.setValue(0.15)
        trow.addWidget(self.sp_holdout)
        trow.addSpacing(20)
        self.cb_shuffle = QCheckBox("Shuffle each pass")
        self.cb_shuffle.setChecked(True)
        trow.addWidget(self.cb_shuffle)
        trow.addStretch(1)
        ov.addLayout(trow)

        splitter.addWidget(opt)

        # ---- analysis ----
        ana = QGroupBox("3.  Analysis")
        av = QVBoxLayout(ana)
        self.analysis = QTextEdit()
        self.analysis.setReadOnly(True)
        self.analysis.setMinimumHeight(140)
        av.addWidget(self.analysis)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)
        av.addWidget(self.progress)

        splitter.addWidget(ana)
        splitter.setSizes([280, 200, 220])
        v.addWidget(splitter, 1)

        # ---- bottom buttons ----
        brow2 = QHBoxLayout()
        self.btn_reanalyze = QPushButton("Re-analyze")
        self.btn_reanalyze.setObjectName("Ghost")
        self.btn_reanalyze.clicked.connect(self._populate)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("Ghost")
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_train = QPushButton("Train")
        self.btn_train.clicked.connect(self._on_train)
        brow2.addWidget(self.btn_reanalyze)
        brow2.addStretch(1)
        brow2.addWidget(self.btn_cancel)
        brow2.addWidget(self.btn_train)
        v.addLayout(brow2)

    # -------------------------------------------------------------- populate
    def _populate(self):
        # fill mapping dropdowns
        choices = ["(none)"] + list(self.session.columns)
        for row, (field, label) in enumerate(MAPPABLE_FIELDS):
            self.map_table.setItem(row, 0, QTableWidgetItem(label))
            cmb = QComboBox()
            cmb.addItems(choices)
            current = self.session.schema.get(field)
            if current in choices:
                cmb.setCurrentText(current)
            cmb.currentTextChanged.connect(
                lambda text, f=field: self._on_map_change(f, text))
            self.map_table.setCellWidget(row, 1, cmb)

        # preview
        n = min(8, len(self.session.rows))
        self.preview.setRowCount(n)
        for r in range(n):
            for c, col in enumerate(self.session.columns):
                val = self.session.rows[r].get(col, "")
                self.preview.setItem(r, c, QTableWidgetItem(str(val)[:40]))

        self._analyze()

    def _on_map_change(self, field, text):
        if text == "(none)":
            self.session.options.schema_override.pop(field, None)
        else:
            self.session.options.schema_override[field] = text

    def _collect_options(self):
        o = self.session.options
        o.dedupe = self.cb_dedupe.isChecked()
        o.dedupe_mode = self.cmb_dedupe_mode.currentText()
        o.drop_conflicts = self.cb_drop_conflicts.isChecked()
        o.balance = self.cmb_balance.currentText()
        o.max_examples = self.sp_max.value()
        o.passes = self.sp_passes.value()
        o.lr_schedule = self.cmb_lr.currentText()
        o.holdout_frac = self.sp_holdout.value()
        o.shuffle = self.cb_shuffle.isChecked()

    def _analyze(self):
        self._collect_options()

        if not self.session.ready():
            missing = self.session.missing_fields()
            self.analysis.setPlainText(
                "⚠  Missing required columns:\n\n  • "
                + "\n  • ".join(missing)
                + "\n\nAssign them above, or use Re-analyze after mapping.")
            self.btn_train.setEnabled(False)
            return

        try:
            examples, stats = self.session.preprocess()
        except Exception as e:
            self.analysis.setPlainText(f"❌ Preprocessing error:\n{e}")
            self.btn_train.setEnabled(False)
            return

        self.examples = examples
        val = self.session.validate(examples)

        txt = []
        txt.append(f"Ready to train on {stats['examples_final']:,} examples.")
        txt.append("")
        txt.append(f"  Class balance : {val['class_balance'] * 100:.1f}% delete")
        txt.append(f"  Coverage      : {val['coverage'] * 100:.1f}% of state space")
        txt.append(f"  Conflicts     : {val['conflicts']} states with mixed labels")
        txt.append(f"  Risk          : {val['risk'].upper()}")
        if val["warnings"]:
            txt.append("")
            txt.append("Warnings:")
            for w in val["warnings"]:
                txt.append(f"  • {w}")
        self.analysis.setPlainText("\n".join(txt))
        self.btn_train.setEnabled(len(examples) > 0)

    # -------------------------------------------------------------- actions
    def _on_cancel(self):
        if self.trainer and self.trainer.isRunning():
            self.trainer.cancel()
            return
        self.reject()

    def _on_train(self):
        if not self.examples:
            return
        if QMessageBox.question(
            self, "Start training?",
            f"Train the agent on {len(self.examples):,} examples "
            f"over {self.session.options.passes} pass(es)?\n\n"
            "This will update the Q-table and save it when done.",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        self.btn_train.setEnabled(False)
        self.btn_reanalyze.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setValue(0)

        self.trainer = TrainerThread(self.session, self.agent, self.examples)
        self.trainer.progress.connect(self._on_progress)
        self.trainer.finished_ok.connect(self._on_done)
        self.trainer.failed.connect(self._on_failed)
        self.trainer.start()

    def _on_progress(self, epoch, total, pct, metrics):
        self.progress.setValue(pct)
        acc = metrics.get("train_accuracy")
        hold = metrics.get("holdout_accuracy")
        bits = [f"Epoch {epoch}/{total}",
                f"lr×{metrics['lr_multiplier']:.2f}"]
        if acc is not None:
            bits.append(f"train {acc*100:.1f}%")
        if hold is not None:
            bits.append(f"holdout {hold*100:.1f}%")
        self.setWindowTitle("Training…  " + "  ".join(bits))

    def _on_done(self, training_report):
        self.agent.save()
        self.progress.setValue(100)
        self.setWindowTitle(f"Import training data — {self.session.path.name}")

        stats = getattr(self, "_last_stats", None)
        # re-run preprocess to grab stats (cheap)
        _, stats = self.session.preprocess()
        validation = self.session.validate(self.examples)
        full_report = self.session.report(stats, validation, training_report)

        box = QMessageBox(self)
        box.setWindowTitle("Training complete")
        box.setIcon(QMessageBox.Information)
        box.setText("Training finished. Agent saved.")
        box.setDetailedText(full_report)
        box.exec_()

        self.btn_train.setEnabled(True)
        self.btn_reanalyze.setEnabled(True)
        self.accept()

    def _on_failed(self, msg):
        self.progress.setVisible(False)
        self.btn_train.setEnabled(True)
        self.btn_reanalyze.setEnabled(True)
        self.setWindowTitle(f"Import training data — {self.session.path.name}")
        QMessageBox.critical(self, "Training failed", msg)