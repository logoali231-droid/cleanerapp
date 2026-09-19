"""Main wizard window."""
import os
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path

from PyQt5.QtCore import QEventLoop, Qt, QTimer
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ai_cleaner.training import apply_training, load_training_file
from ai_cleaner.training.session import TrainingSession
from ai_cleaner.ui.training_dialog import TrainingDialog

from ..admin import (
    _admin_log,
    find_terminal,
    relaunch_as_admin,
    terminal_argv,
)
from ..agent import QLearningAgent, reinforce_agent_from_rule, train_agent
from ..config import CONFIG_DIR, HOME, IS_ROOT
from ..demo import create_demo_files
from ..rules import RulesManager
from ..scanner import ScannerThread
from ..utils import age, duration, human, short_path
from .rules_dialog import RulesDialog
from .styles import QSS
from .widgets import card, make_stat, set_bigstat


class Wizard(QMainWindow):
    STEPS = ["Welcome", "Choose folder", "Scan", "Review", "Clean up", "Done"]  # noqa: RUF012

    def __init__(self, admin_mode=False, start_folder=None, start_deep=False):
        super().__init__()
        base_title = "AI File Cleaner" + ("  —  Administrator" if IS_ROOT else "")
        self.setWindowTitle(base_title)
        self._base_title = base_title
        self.setWindowIcon(self._app_icon())
        self.setGeometry(120, 80, 1100, 760)
        self.setMinimumSize(940, 620)

        self.agent = QLearningAgent()
        loaded = self.agent.load()
        self.rules = RulesManager()
        seeded = self.rules.seed_defaults_once()
        if seeded:
            print(f"[defaults] Seeded {seeded} protection rule(s).")

        self.scanner = None
        self.scan_results = []
        self.folder = None
        self.deep_mode = False
        self._last_trashed = []

        self.setAcceptDrops(True)
        self._base_title = self.windowTitle()

        self._build_menu()
        self._build_ui()

        if not loaded:
            QTimer.singleShot(150, lambda: self._train_agent(12000, silent=True))

        if admin_mode and start_folder:
            self._set_folder(start_folder)
            if start_deep:
                self.deep_check.setChecked(True)
            QTimer.singleShot(400, self._start_scan)

        # =========================================================== training import
    def _import_training_file_dialog(self):
        d = QFileDialog.getOpenFileName(
            self, "Pick a training file", HOME,
                        "Training data (*.csv *.tsv *.json *.jsonl *.ndjson "
            "*.parquet *.pq *.xlsx *.xls *.db *.sqlite *.sqlite3);;All files (*)")
        if not d or not d[0]:
            return
        self._import_training_file(Path(d[0]))

    def _import_training_file(self, path: Path):
        session = TrainingSession(path)
        if session.load_error:
            QMessageBox.critical(
                self, "Couldn't read file",
                f"{type(session.load_error).__name__}: {session.load_error}")
            return
        if not session.rows:
            QMessageBox.information(
                self, "No data",
                f"{path.name} contained no usable rows.")
            return

        dlg = TrainingDialog(session, self.agent, self)
        if dlg.exec_() == dlg.Accepted:
            self._refresh_agent_info()
            self._log(f"Imported training data from {path.name}")
    def _show_training_help(self):
        QMessageBox.information(
            self, "Training data format",
            "Drop a file onto the window, or use Tools → Import training data.\n\n"

            "Supported formats: CSV, TSV, JSON, JSONL, NDJSON, "
            "Parquet, Excel, SQLite.\n\n"

            "Required columns (name-flexible, auto-detected):\n"
            "  • extension (or ext, file_type, …)\n"
            "  • size_bytes (or size, file_size, …)\n"
            "  • age_days (or age, days_old, …)\n"
            "  • location (or path, directory, folder, …)\n"
            "  • label (1=delete, 0=keep)\n\n"

            "Optional: weight (default 1.0)\n\n"

            "Or supply pre-bucketed data with these instead:\n"
            "  ext_bucket, size_bucket, age_bucket, loc_bucket\n\n"

            "The dialog auto-maps columns. You can override any mapping\n"
            "in the import window if detection got it wrong.")
    # ============================================================== icon
    def _app_icon(self):
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor("#2f7ad6")))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(2, 2, 60, 60, 14, 14)
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawRoundedRect(20, 16, 24, 32, 3, 3)
        p.end()
        return QIcon(pm)

        # =========================================================== drag-drop
    TRAINING_EXTS = (".csv", ".tsv", ".json")

    def _drag_training_file(self, event):
        if not event.mimeData().hasUrls():
            return None
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.suffix.lower() in self.TRAINING_EXTS:
                return p
        return None

    def dragEnterEvent(self, event):
        if self._drag_training_file(event):
            event.acceptProposedAction()
            self.setWindowTitle("📥  Drop to import training data…")
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setWindowTitle(self._base_title)

    def dropEvent(self, event):
        self.setWindowTitle(self._base_title)
        p = self._drag_training_file(event)
        if not p:
            return
        event.acceptProposedAction()
        self._import_training_file(p)

    # ============================================================== menu
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
        t.addAction("Import training data (CSV/JSON)…",
        self._import_training_file_dialog)
        t.addAction("Show training format help", self._show_training_help)

        t.addSeparator()
        if not IS_ROOT:
            t.addAction("Relaunch as administrator…", self._relaunch_admin)
        t.addAction("Scan entire system…", self._preset_whole_system)
        h = m.addMenu("&Help")
        h.addAction("How it works", self._show_help)
        h.addAction("Teach the AI (quick guide)", self._show_teach_guide)
        h.addAction("About", self._show_about)

    # ============================================================== UI
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- sidebar ----
        sidebar = QFrame()
        sidebar.setStyleSheet("background: white; border-right: 1px solid #e6e9f0;")
        sidebar.setFixedWidth(240)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(20, 24, 20, 20)
        sv.setSpacing(6)

        logo = QLabel("🧹  AI Cleaner")
        logo.setStyleSheet("font-size:18px; font-weight:800; color:#1e2430; padding:4px 0 18px 0;")
        sv.addWidget(logo)

        self.step_labels = []
        for i, name in enumerate(self.STEPS):
            lbl = QLabel(f"{i+1}.  {name}")
            lbl.setStyleSheet("color:#5a6478; padding:8px 12px; border-radius:6px;")
            sv.addWidget(lbl)
            self.step_labels.append(lbl)
        sv.addStretch(1)

        if IS_ROOT:
            badge = QLabel("🔓  Running as administrator")
            badge.setObjectName("Admin")
            badge.setWordWrap(True)
            sv.addWidget(badge)

        self.agent_info = QLabel("AI is ready.")
        self.agent_info.setObjectName("Hint")
        self.agent_info.setWordWrap(True)
        sv.addWidget(self.agent_info)

        self.rules_info = QLabel("")
        self.rules_info.setObjectName("Hint")
        self.rules_info.setWordWrap(True)
        sv.addWidget(self.rules_info)

        root.addWidget(sidebar)

        # ---- content ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(32, 24, 32, 20)
        rv.setSpacing(14)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_welcome())
        self.stack.addWidget(self._page_pick())
        self.stack.addWidget(self._page_scan())
        self.stack.addWidget(self._page_review())
        self.stack.addWidget(self._page_cleanup())
        self.stack.addWidget(self._page_done())
        rv.addWidget(self.stack, 1)

        nav = QHBoxLayout()
        self.btn_back = QPushButton("←  Back")
        self.btn_back.setObjectName("Ghost")
        self.btn_back.clicked.connect(self._go_back)
        self.btn_back.setVisible(False)
        self.btn_next = QPushButton("Get Started  →")
        self.btn_next.setObjectName("Big")
        self.btn_next.clicked.connect(self._go_next)
        nav.addWidget(self.btn_back)
        nav.addStretch(1)
        nav.addWidget(self.btn_next)
        rv.addLayout(nav)

        root.addWidget(right, 1)

        self._refresh_agent_info()
        self._set_step(0)

    # ============================================================== pages
    def _page_welcome(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setSpacing(20)
        v.addStretch(1)

        t = QLabel("Hi there 👋")
        t.setObjectName("Hero")
        sub = QLabel(
            "I find files you probably don't need — old installers, forgotten "
            "downloads, cache leftovers — and remove them safely.\n\n"
            "You can teach me what to keep or flag anytime:  right-click any file, "
            "or use  Tools → Teach the AI.")
        sub.setObjectName("SubHero")
        sub.setWordWrap(True)
        v.addWidget(t)
        v.addWidget(sub)

        info = card()
        iv = QVBoxLayout(info)
        iv.setContentsMargins(20, 20, 20, 20)
        iv.setSpacing(8)
        h = QLabel("How it works")
        h.setObjectName("Section")
        iv.addWidget(h)
        for s in [
            "1.  Pick a folder (Home is a good start).",
            "2.  I scan and show you what I found.",
            "3.  Right-click anything to teach me a rule.",
            "4.  One click frees up space.",
        ]:
            l = QLabel(s)
            l.setObjectName("Hint")
            iv.addWidget(l)
        v.addWidget(info)

        tip = QLabel("💡  First time?  Tools → Create demo files  to try me safely.")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        v.addWidget(tip)
        v.addStretch(1)
        return p

    def _page_pick(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setSpacing(14)

        t = QLabel("Which folder should I look through?")
        t.setObjectName("Section")
        v.addWidget(t)
        h = QLabel("Pick a folder. Nothing happens until you click 'Scan'.")
        h.setObjectName("Hint")
        h.setWordWrap(True)
        v.addWidget(h)

        c = card()
        cv = QVBoxLayout(c)
        cv.setContentsMargins(24, 24, 24, 24)
        cv.setSpacing(14)

        self.folder_label = QLabel("No folder selected yet")
        self.folder_label.setStyleSheet("font-size:16px; font-weight:600; color:#1e2430;")
        self.folder_label.setWordWrap(True)
        cv.addWidget(self.folder_label)

        row = QHBoxLayout()
        b1 = QPushButton("📁  Choose folder…")
        b1.clicked.connect(self._pick_folder)
        b2 = QPushButton("🏠  Home")
        b2.setObjectName("Ghost")
        b2.clicked.connect(lambda: self._set_folder(HOME))
        b3 = QPushButton("📥  Downloads")
        b3.setObjectName("Ghost")
        b3.clicked.connect(lambda: self._set_folder(os.path.join(HOME, "Downloads")))
        b4 = QPushButton("🌍  Entire system")
        b4.setObjectName("Ghost")
        b4.clicked.connect(self._preset_whole_system)
        row.addWidget(b1); row.addWidget(b2); row.addWidget(b3); row.addWidget(b4)
        row.addStretch(1)
        cv.addLayout(row)

        self.deep_check = QCheckBox("Deep scan — include hidden files and system folders")
        self.deep_check.stateChanged.connect(self._on_deep_toggle)
        cv.addWidget(self.deep_check)

        if IS_ROOT:
            al = QLabel("🔓  Already running as administrator.")
            al.setObjectName("Admin")
            cv.addWidget(al)
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

            mrow = QHBoxLayout()
            mrow.addSpacing(28)
            lbl = QLabel("Method:")
            lbl.setObjectName("Hint")
            mrow.addWidget(lbl)
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

            test_row = QHBoxLayout()
            test_row.addSpacing(28)
            b_test = QPushButton("🧪  Test elevation")
            b_test.setObjectName("Browse")
            b_test.clicked.connect(self._test_admin_method)
            test_row.addWidget(b_test)
            test_row.addStretch(1)
            cv.addLayout(test_row)

            self.admin_check.stateChanged.connect(
                lambda s: self.admin_method.setVisible(bool(s)))

        self.warn_frame = QFrame()
        self.warn_frame.setObjectName("Warn")
        self.warn_frame.setVisible(False)
        wv = QVBoxLayout(self.warn_frame)
        wv.setContentsMargins(16, 12, 16, 12)
        self.warn_label = QLabel("")
        self.warn_label.setWordWrap(True)
        self.warn_label.setStyleSheet("color:#7a5a10; font-weight:600;")
        wv.addWidget(self.warn_label)
        cv.addWidget(self.warn_frame)

        v.addWidget(c)

        hint2 = QLabel("🔒  Games, PrismLauncher instances, Minecraft saves, and .jar "
                       "files are always skipped — even in deep mode.")
        hint2.setObjectName("Hint")
        hint2.setWordWrap(True)
        v.addWidget(hint2)
        v.addStretch(1)
        return p

    def _page_scan(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setSpacing(14)
        v.addStretch(1)

        t = QLabel("Scanning…")
        t.setObjectName("Section")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)

        self.scan_status = QLabel("Getting ready")
        self.scan_status.setObjectName("Hint")
        self.scan_status.setAlignment(Qt.AlignCenter)
        v.addWidget(self.scan_status)

        self.scan_bar = QProgressBar()
        self.scan_bar.setRange(0, 100)
        self.scan_bar.setMaximumWidth(640)
        self.scan_bar.setMinimumHeight(20)
        bw = QHBoxLayout()
        bw.addStretch(1)
        bw.addWidget(self.scan_bar)
        bw.addStretch(1)
        v.addLayout(bw)

        self.scan_counter = QLabel("Counting files…")
        self.scan_counter.setObjectName("Hint")
        self.scan_counter.setAlignment(Qt.AlignCenter)
        v.addWidget(self.scan_counter)

        self.scan_curdir = QLabel("")
        self.scan_curdir.setObjectName("Mono")
        self.scan_curdir.setAlignment(Qt.AlignCenter)
        v.addWidget(self.scan_curdir)

        self.scan_eta = QLabel("")
        self.scan_eta.setObjectName("Hint")
        self.scan_eta.setAlignment(Qt.AlignCenter)
        v.addWidget(self.scan_eta)

        live = card()
        lv = QHBoxLayout(live)
        lv.setContentsMargins(24, 20, 24, 20)
        self.live_files = make_stat("0", "Suspicious files")
        self.live_size = make_stat("0 MB", "Reclaimable")
        lv.addWidget(self.live_files)
        lv.addWidget(self.live_size)
        lw = QHBoxLayout()
        lw.addStretch(1)
        lw.addWidget(live)
        lw.addStretch(1)
        v.addLayout(lw)
        v.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("Ghost")
        self.btn_cancel.clicked.connect(self._cancel_scan)
        row.addWidget(self.btn_cancel)
        v.addLayout(row)
        return p

    def _page_review(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setSpacing(12)

        t = QLabel("Here's what I found 🔍")
        t.setObjectName("Section")
        v.addWidget(t)
        h = QLabel("Uncheck anything you want to keep.  Right-click a row to teach me a rule.")
        h.setObjectName("Hint")
        h.setWordWrap(True)
        v.addWidget(h)

        s = card()
        sv = QHBoxLayout(s)
        sv.setContentsMargins(24, 20, 24, 20)
        self.rev_count = make_stat("0", "Files flagged")
        self.rev_size = make_stat("0 MB", "You can free up")
        self.rev_prot = make_stat("Auto", "Games protected")
        sv.addWidget(self.rev_count)
        sv.addWidget(self.rev_size)
        sv.addWidget(self.rev_prot)
        v.addWidget(s)

        bar = QHBoxLayout()
        b_all = QPushButton("Select all")
        b_all.setObjectName("Ghost")
        b_none = QPushButton("Deselect all")
        b_none.setObjectName("Ghost")
        b_rules = QPushButton("🛡  Manage rules…")
        b_rules.setObjectName("Ghost")
        b_all.clicked.connect(lambda: self._toggle_all(True))
        b_none.clicked.connect(lambda: self._toggle_all(False))
        b_rules.clicked.connect(self._manage_rules)
        self.live_total = QLabel("")
        self.live_total.setObjectName("Hint")
        bar.addWidget(b_all)
        bar.addWidget(b_none)
        bar.addWidget(b_rules)
        bar.addStretch(1)
        bar.addWidget(self.live_total)
        v.addLayout(bar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["✔", "File", "Location", "Count", "Size", "Age", "Why"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(2, 240)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 90)
        self.table.setColumnWidth(6, 240)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)
        v.addWidget(self.table, 1)
        return p

    def _page_cleanup(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setSpacing(16)
        v.addStretch(1)
        t = QLabel("Ready to clean up")
        t.setObjectName("Section")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        self.clean_msg = QLabel("")
        self.clean_msg.setObjectName("Hint")
        self.clean_msg.setAlignment(Qt.AlignCenter)
        self.clean_msg.setWordWrap(True)
        v.addWidget(self.clean_msg)
        self.clean_bar = QProgressBar()
        self.clean_bar.setRange(0, 100)
        self.clean_bar.setMaximumWidth(600)
        self.clean_bar.setMinimumHeight(20)
        bw = QHBoxLayout()
        bw.addStretch(1)
        bw.addWidget(self.clean_bar)
        bw.addStretch(1)
        v.addLayout(bw)
        v.addStretch(1)
        return p

    def _page_done(self):
        p = QWidget()
        v = QVBoxLayout(p)
        v.setSpacing(18)
        v.addStretch(1)

        t = QLabel("All done! ✨")
        t.setObjectName("Hero")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)

        self.done_msg = QLabel("")
        self.done_msg.setObjectName("SubHero")
        self.done_msg.setAlignment(Qt.AlignCenter)
        self.done_msg.setWordWrap(True)
        v.addWidget(self.done_msg)

        c = card()
        cv = QHBoxLayout(c)
        cv.setContentsMargins(24, 20, 24, 20)
        self.done_freed = make_stat("0 MB", "Space freed")
        self.done_files = make_stat("0", "Files removed")
        self.done_kept = make_stat("0", "Files kept")
        cv.addWidget(self.done_freed)
        cv.addWidget(self.done_files)
        cv.addWidget(self.done_kept)
        cw = QHBoxLayout()
        cw.addStretch(1)
        cw.addWidget(c)
        cw.addStretch(1)
        v.addLayout(cw)

        note = QLabel("Deleted files are moved to Trash — you can restore them "
                      "from Nemo if you change your mind.")
        note.setObjectName("Hint")
        note.setAlignment(Qt.AlignCenter)
        v.addWidget(note)

        restore_row = QHBoxLayout()
        restore_row.addStretch(1)
        self.btn_restore = QPushButton("↩  Restore last batch from Trash")
        self.btn_restore.setObjectName("Ghost")
        self.btn_restore.setEnabled(False)
        self.btn_restore.clicked.connect(self._restore_last_batch)
        restore_row.addWidget(self.btn_restore)
        restore_row.addStretch(1)
        v.addLayout(restore_row)
        v.addStretch(1)
        return p

    # =========================================================== navigation
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
            self.btn_next.setText("Get Started  →")
            self.btn_next.setEnabled(True)
        elif i == 1:
            self.btn_next.setText("Scan now  →")
            self.btn_next.setEnabled(bool(self.folder))
        elif i == 3:
            n, sz = self._checked_summary()
            self.btn_next.setText(f"Free up {human(sz)}  →")
            self.btn_next.setEnabled(n > 0)
        elif i == 5:
            self.btn_next.setText("Scan another folder")
            self.btn_next.setEnabled(True)
        else:
            self.btn_next.setEnabled(False)

    def _go_next(self):
        i = self.step
        if i == 0:
            self._go_to(1)
        elif i == 1:
            self._start_scan()
        elif i == 3:
            self._confirm_and_delete()
        elif i == 5:
            self.folder = None
            self.folder_label.setText("No folder selected yet")
            self._go_to(1)

    def _go_back(self):
        if self.step == 3:
            self._go_to(1)
        elif self.step == 1:
            self._go_to(0)

    def _go_to(self, i):
        self._set_step(i)

    # =========================================================== folder
    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose a folder", HOME)
        if d:
            self._set_folder(d)

    def _set_folder(self, path):
        self.folder = path
        self.folder_label.setText(f"📂  {path}")
        self._update_next_button()

    def _preset_whole_system(self):
        self._set_folder("/")
        self.deep_check.setChecked(True)
        if self.admin_check is not None and not IS_ROOT:
            self.admin_check.setChecked(True)
        self._go_to(1)
        self._update_pick_warning()

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

    def _current_admin_method(self):
        if not self.admin_method:
            return "terminal"
        return ["terminal", "pkexec", "askpass"][self.admin_method.currentIndex()]

    # =========================================================== demo
    def _make_demo(self):
        d = QFileDialog.getExistingDirectory(self, "Where to create the demo?", HOME)
        if not d:
            return
        target = Path(d) / "ai_cleaner_demo"
        try:
            info = create_demo_files(target)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Oops", f"Couldn't create demo files:\n{e}")
            return
        QMessageBox.information(
            self, "Demo files created 🎉",
            f"Created {info['junk']} junk, {info['keepers']} keepers, "
            f"{info['protected']} protected.\n\nLocation:\n{info['path']}")
        self._set_folder(info["path"])
        self._go_to(1)

    # =========================================================== rules
    def _manage_rules(self):
        if not hasattr(self.rules, "settings") or self.rules.settings is None:
            self.rules.settings = {"skip_rule_confirmation": False}
        try:
            dlg = RulesDialog(self.rules, self)
            dlg.rules_changed.connect(self._on_rules_changed)
            dlg.exec_()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
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
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Couldn't add rule",
                                 f"{type(e).__name__}: {e}")

    def _apply_rules_to_table(self):
        removed = 0
        for r in reversed(range(self.table.rowCount())):
            item = self.table.item(r, 1)
            if item is None:
                continue
            group = item.data(Qt.UserRole)
            if not group:
                continue
            action, _ = self.rules.match(Path(group[0]["path"]))
            if action == "protect":
                self.table.removeRow(r)
                removed += 1
        if removed:
            self._log(f"{removed} row(s) hidden by your rules.")
            self._refresh_review_summary()

    def _table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if item is None:
            return
        row = item.row()
        name_item = self.table.item(row, 1)
        if name_item is None:
            return
        group = name_item.data(Qt.UserRole)
        if not group:
            return
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
            self._add_rule_and_train(rule)
            return
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
        if box.exec_() != QMessageBox.Yes:
            return
        if cb.isChecked():
            self.rules.settings["skip_rule_confirmation"] = True
            if hasattr(self.rules, "save_settings"):
                self.rules.save_settings()
        self._add_rule_and_train(rule)

    # =========================================================== scan
    def _start_scan(self):
        if not self.folder:
            return
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
        self.scan_curdir.setText("")
        self.scan_eta.setText("")
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
            if os.path.exists(sig):
                os.remove(sig)
        except Exception:  # noqa: BLE001, S110
            pass

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
        timer = QTimer()
        timer.setInterval(250)

        def _poll():
            nonlocal started
            if os.path.exists(sig):
                started = True
                loop.quit()
                return
            if time.time() > deadline:
                loop.quit()
                return

        timer.timeout.connect(_poll)
        wait.button(QMessageBox.Cancel).clicked.connect(loop.quit)
        timer.start()
        QTimer.singleShot(200, _poll)
        loop.exec_()
        timer.stop()
        wait.close()

        if started:
            _admin_log("child confirmed — closing launcher")
            self.close()
        else:
            _admin_log("child did NOT confirm within 25s")
            QMessageBox.warning(
                self, "Admin instance didn't start",
                "The root window didn't appear.\n\n"
                "This window stays open. Try a different method.\n\n"
                f"Log: {os.path.join(CONFIG_DIR, 'admin-launch.log')}")

    def _on_progress(self, scanned, total, cur_dir, eta, is_counting):
        if is_counting:
            self.scan_bar.setRange(0, 0)
            self.scan_counter.setText(f"Counting…  {scanned:,} files so far")
            if cur_dir:
                self.scan_curdir.setText(short_path(cur_dir))
            return
        if total > 0:
            self.scan_bar.setRange(0, 100)
            self.scan_bar.setValue(int(100 * scanned / total))
        else:
            self.scan_bar.setRange(0, 0)
        self.scan_counter.setText(f"{scanned:,} / {total:,} files checked")
        if cur_dir:
            self.scan_curdir.setText(short_path(cur_dir))
        if eta < 0:
            # Sentinel from the scanner: not enough data yet
            self.scan_eta.setText("Calculating…")
        elif eta < 5:
            self.scan_eta.setText("Almost done…")
        else:
            self.scan_eta.setText(f"About {duration(eta)} remaining")

    def _on_file_found(self, info):
        self.scan_results.append(info)
        n = len(self.scan_results)
        total = sum(f["size"] for f in self.scan_results)
        set_bigstat(self.live_files, f"{n:,}")
        set_bigstat(self.live_size, human(total))

    def _cancel_scan(self):
        if self.scanner:
            self.scanner.stop()
            self.scanner.wait(1500)
        self.scan_status.setText("Cancelled.")
        self._go_to(1)

    def _on_scan_done(self, files):
        self.scan_results = files
        self._fill_review_table()
        if not files:
            QMessageBox.information(self, "Nothing to clean! 🎉",
                                    "I didn't find anything worth removing here.")
            self._show_done(0, 0, 0)
            self._go_to(5)
        else:
            self._go_to(3)

    # =========================================================== review
    def _fill_review_table(self):
        self.table.setRowCount(0)
        self.table.setHorizontalHeaderLabels(
            ["✔", "File", "Location", "Count", "Size", "Age", "Why"])

        groups = {}
        for info in self.scan_results:
            key = (info["name"], round(info["size"] / 1024), info["age"])
            groups.setdefault(key, []).append(info)

        ordered = sorted(groups.values(),
                         key=lambda g: -sum(f["size"] for f in g))

        for group in ordered:
            r = self.table.rowCount()
            self.table.insertRow(r)
            first = group[0]
            total_size = sum(f["size"] for f in group)
            count = len(group)

            cb = QCheckBox()
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_next_button)
            cw = QWidget()
            cl = QHBoxLayout(cw)
            cl.addWidget(cb)
            cl.setAlignment(Qt.AlignCenter)
            cl.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, 0, cw)

            label = "📄  " + first["name"]
            if count > 1:
                label = f"📄  {first['name']}   ×{count}"
            name_item = QTableWidgetItem(label)
            name_item.setData(Qt.UserRole, group)
            name_item.setToolTip("\n".join(f["path"] for f in group[:20])
                                 + ("\n…" if count > 20 else ""))
            self.table.setItem(r, 1, name_item)

            parents = sorted({str(Path(f["path"]).parent) for f in group})
            if len(parents) == 1:
                loc_text = short_path(parents[0], 55)
            else:
                loc_text = f"{short_path(parents[0], 35)}  (+{len(parents)-1} more)"
            loc = QTableWidgetItem(loc_text)
            loc.setForeground(QColor("#5a6478"))
            loc.setToolTip("\n".join(parents))
            self.table.setItem(r, 2, loc)

            cnt = QTableWidgetItem(f"×{count}" if count > 1 else "1")
            cnt.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, 3, cnt)

            size_item = QTableWidgetItem(human(total_size))
            size_item.setData(Qt.UserRole, total_size)
            self.table.setItem(r, 4, size_item)

            self.table.setItem(r, 5, QTableWidgetItem(age(first["age"])))
            why = QTableWidgetItem(first["reason"])
            why.setForeground(QColor("#5a6478"))
            self.table.setItem(r, 6, why)

        self._refresh_review_summary()

    def _refresh_review_summary(self):
        n, total = self._checked_summary()
        set_bigstat(self.rev_count, f"{n:,}")
        set_bigstat(self.rev_size, human(total))
        self.live_total.setText(f"{n:,} of {len(self.scan_results):,} selected")
        self._update_next_button()

    def _checked_summary(self):
        n = 0
        sz = 0
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if not w:
                continue
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
                if cb:
                    cb.setChecked(state)
        self._refresh_review_summary()

    # =========================================================== delete
    def _confirm_and_delete(self):
        n, sz = self._checked_summary()
        if n == 0:
            return
        if QMessageBox.question(
            self, "Ready to clean up?",
            f"I'll move {n:,} file(s) to Trash, freeing about {human(sz)}.\n\n"
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

                # ---- Batch-aware reinforcement ----
        # Group decisions by state so 20 deleted screenshots produce one
        # strong update instead of 20 weak identical ones. Capped so a
        # 500-file batch doesn't slam the Q-values out of range.
        R = 3.0
        MAX_BOOST = 10

        delete_counts = Counter(
            f["state"] for f in to_delete if f.get("state") is not None)
        keep_counts = Counter(
            f["state"] for f in to_keep if f.get("state") is not None)
                # --- record calibration data (one entry per file, not per state) ---
        for f in to_delete:
            self.agent.record_decision(f.get("confidence"), accepted=True)
        for f in to_keep:
            self.agent.record_decision(f.get("confidence"), accepted=False)
        cluster_info = []
        for state, count in delete_counts.items():
            weight = min(count, MAX_BOOST)
            self.agent.learn(state, 1, +R * weight)
            self.agent.learn(state, 0, -R * weight)
            cluster_info.append(f"delete×{count}→{weight}")
        for state, count in keep_counts.items():
            weight = min(count, MAX_BOOST)
            self.agent.learn(state, 0, +R * weight)
            self.agent.learn(state, 1, -R * weight)
            cluster_info.append(f"keep×{count}→{weight}")

        if cluster_info:
            self._log(f"Batch learning: {len(cluster_info)} state clusters "
                      f"({', '.join(cluster_info[:5])}"
                      f"{', …' if len(cluster_info) > 5 else ''})")
            self._log(f"Calibration: {self.agent.calibration_summary()}")

        self._go_to(4)
        self.clean_msg.setText(f"Trashing {len(to_delete)} file(s)…")
        self.clean_bar.setValue(0)
        QApplication.processEvents()

        freed = deleted = failed = skipped = 0
        self._last_trashed = []
        for i, f in enumerate(to_delete, 1):
            try:
                p = Path(f["path"])
                pl = str(p).lower()
                if any(g and g.lower() in pl for g in GAME_DIRS) \
                   or any(h in pl for h in GAME_PATH_HINTS) \
                   or p.suffix.lower() in GAME_EXTS:
                    skipped += 1
                    continue
                if p.exists() and p.is_file():
                    rc = subprocess.run(
                        ["gio", "trash", "--", str(p)],
                        check=False, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ).returncode
                    if rc == 0:
                        self._last_trashed.append(str(p))
                        deleted += 1
                        freed += f["size"]
                    else:
                        p.unlink()
                        deleted += 1
                        freed += f["size"]
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001
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
            f"You just freed up {human(freed)} by removing {deleted} file(s).")
        set_bigstat(self.done_freed, human(freed))
        set_bigstat(self.done_files, f"{deleted:,}")
        set_bigstat(self.done_kept, f"{kept:,}")
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
        restored = 0
        failed = 0
        for path in batch:
            try:
                rc = subprocess.run(
                    ["gio", "trash", "--restore", "--", path],
                    check=False, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                if rc == 0:
                    restored += 1
                else:
                    failed += 1
            except Exception:  # noqa: BLE001
                failed += 1
        QMessageBox.information(self, "Done",
                                f"Restored {restored} file(s). {failed} failed.")
        self.btn_restore.setEnabled(False)
        self._last_trashed = []

    # =========================================================== AI
    def _train_agent(self, episodes, silent=False):
        if not silent:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        t0 = time.time()
        train_agent(self.agent, episodes=episodes)
        self.agent.save()
        if not silent:
            QApplication.restoreOverrideCursor()
            QMessageBox.information(
                self, "AI retrained",
                f"Trained on {episodes:,} examples in {time.time()-t0:.1f}s.")
        self._refresh_agent_info()

    def _reset_agent(self):
        if QMessageBox.question(
            self, "Reset AI",
            "Forget everything the AI has learned?  (Your rules stay.)",
            QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self.agent.reset()
        self._train_agent(20000)
        for rule in self.rules.rules:
            reinforce_agent_from_rule(self.agent, rule)
        self.agent.save()
        self._refresh_agent_info()

    def _refresh_agent_info(self):
        self.agent_info.setText(
            f"AI has seen {self.agent.visited_states():,} situations.")
        n = len(self.rules.rules)
        if n == 0:
            self.rules_info.setText("No rules yet — right-click a file to add one.")
        else:
            enabled = sum(1 for r in self.rules.rules if r.get("enabled", True))
            self.rules_info.setText(
                f"📋 {enabled} of {n} rule(s) active.\n"
                "Manage in Tools → Teach the AI.")

    def _log(self, m):
        print(f"[{time.strftime('%H:%M:%S')}] {m}")

    # =========================================================== admin
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
        fd, _out = tempfile.mkstemp(prefix="ai-cleaner-test-", suffix=".log")
        os.close(fd)
        if method == "terminal":
            term = find_terminal()
            if not term:
                QMessageBox.critical(self, "No terminal",
                                     "Couldn't find a terminal emulator.")
                return
            fd2, tmp = tempfile.mkstemp(prefix="ai-cleaner-testterm-", suffix=".sh")
            os.close(fd2)
            with open(tmp, "w") as f:
                f.write("#!/bin/bash\n")
                f.write("echo 'Testing sudo…'\n")
                f.write(f"sudo -E id 2>&1 | tee {tmp}\n")
                f.write("echo '=== done. Press Enter. ==='\n")
                f.write("read _\n")
                f.write(f"rm -f {tmp}\n")
            os.chmod(tmp, 0o755)
            try:
                subprocess.Popen(terminal_argv(term, tmp), close_fds=True)
            except Exception as e:  # noqa: BLE001
                QMessageBox.critical(self, "Launch failed", str(e))
                return
            QMessageBox.information(
                self, "Terminal opened",
                "A terminal window just opened.\n\n"
                "Type your password there. If you see  uid=0(root)…, "
                "the terminal method works.")
        else:
            QMessageBox.information(
                self, "Test",
                "For pkexec / askpass, testing opens the real dialog. "
                "Use the scan itself — log at:\n"
                f"{os.path.join(CONFIG_DIR, 'admin-launch.log')}")

    # =========================================================== help
    def _show_help(self):
        QMessageBox.information(
            self, "How it works",
            "The cleaner uses reinforcement learning to decide, for each file, "
            "whether to KEEP it or DELETE it.\n\n"
            "🛡  Protected forever: Steam, Lutris, Heroic, Wine, "
            "PrismLauncher / MultiMC instances, .minecraft, all .jar files, "
            "and game data (.pak, .sav, .vpk, .bsa…).\n\n"
            "Teach me anytime: right-click a file in the Review list, or use "
            "Tools → Teach the AI.")

    def _show_teach_guide(self):
        QMessageBox.information(
            self, "Teach the AI",
            "Two ways to teach me:\n\n"
            "  1.  Right-click any file in the Review list.\n"
            "  2.  Tools → Teach the AI — manage rules…\n\n"
            "For folder rules, click  📁 Browse…  instead of typing the path.\n\n"
            "Rules take priority over the AI. Extension rules also nudge the AI.")

    def _show_about(self):
        admin = "  (administrator)" if IS_ROOT else ""
        QMessageBox.about(
            self, "About AI File Cleaner",
            f"<h3>AI File Cleaner — Wizard Edition v7{admin}</h3>"
            "<p>RL-powered cleaner with in-app rule training and admin mode.</p>"
            "<p>Runs entirely on your machine. No network, no cloud.</p>")

    # =========================================================== events
    def closeEvent(self, e):
        if self.scanner and self.scanner.isRunning():
            self.scanner.stop()
            self.scanner.wait(1500)
        try:
            self.agent.save()
        except Exception:  # noqa: BLE001, S110
            pass
        try:
            self.rules.save()
        except Exception:  # noqa: BLE001, S110
            pass
        e.accept()


# The wizard imports these directly from the modules above; the constants
# are re-exported here for convenience of the delete loop.
from ..protection import GAME_DIRS, GAME_EXTS, GAME_PATH_HINTS


# ======================================================================
def main():
    import argparse
    import sys

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
        except Exception as e:  # noqa: BLE001
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