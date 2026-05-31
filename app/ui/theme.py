APP_QSS = """
QMainWindow, QWidget {
    background: #101316;
    color: #eef2f6;
    font-family: "Microsoft YaHei UI", "Segoe UI";
    font-size: 12px;
}
QFrame#Panel {
    background: #191d22;
    border: 1px solid #303842;
}
QToolBar {
    background: #15191d;
    border-bottom: 1px solid #303842;
    spacing: 8px;
    padding: 6px;
}
QListWidget, QTextEdit, QLineEdit, QSpinBox, QComboBox {
    background: #15191e;
    color: #eef2f6;
    border: 1px solid #303842;
    border-radius: 6px;
    padding: 6px;
}
QListWidget::item {
    padding: 8px;
    border: 1px solid #303842;
    border-radius: 7px;
    background: #20262d;
}
QListWidget::item:disabled {
    color: #697582;
    background: transparent;
    border: none;
    font-weight: 700;
}
QListWidget::item:selected {
    background: #2459a8;
}
QPushButton {
    background: #20262d;
    color: #eef2f6;
    border: 1px solid #303842;
    border-radius: 6px;
    padding: 7px 10px;
}
QPushButton:hover {
    background: #2a323b;
}
QPushButton#PrimaryButton {
    background: #1d3a2a;
    color: #d9ffe8;
    border-color: rgba(54, 194, 117, 0.45);
    font-weight: 700;
}
QTabWidget::pane {
    border: 1px solid #303842;
    background: #191d22;
}
QTabBar::tab {
    background: #15191e;
    color: #9aa6b2;
    border: 1px solid #303842;
    padding: 8px 14px;
}
QTabBar::tab:selected {
    background: #20262d;
    color: #eef2f6;
}
QFrame#NodeCard, QFrame#MetricCard {
    background: #20262d;
    border: 1px solid #303842;
    border-radius: 7px;
}
QLabel#NodeTitle {
    color: #eef2f6;
    font-size: 14px;
    font-weight: 700;
}
QLabel#MetricValue {
    color: #eef2f6;
    font-size: 18px;
    font-weight: 700;
}
QLabel#Muted {
    color: #9aa6b2;
}
"""
