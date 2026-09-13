"""Small reusable Qt widgets."""
from PyQt5.QtWidgets import QFrame, QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt


def card():
    f = QFrame()
    f.setObjectName("Card")
    return f


def make_stat(value, label):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    vl = QLabel(value)
    vl.setObjectName("BigStat")
    vl.setAlignment(Qt.AlignCenter)
    ll = QLabel(label)
    ll.setObjectName("StatLbl")
    ll.setAlignment(Qt.AlignCenter)
    v.addWidget(vl)
    v.addWidget(ll)
    return w


def set_bigstat(widget, text):
    for w in widget.findChildren(QLabel):
        if w.objectName() == "BigStat":
            w.setText(text)
            return