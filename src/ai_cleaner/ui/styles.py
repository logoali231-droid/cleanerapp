"""Qt stylesheet — one big QSS string."""

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