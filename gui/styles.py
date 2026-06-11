"""
OLED Dark + Cyberpunk theme for Crypto Box Scanner.
Generated with UI/UX Pro Max design system recommendations.
"""

DARK_THEME = """
/* ===== Global ===== */
QWidget {
    background-color: #0A0A0F;
    color: #E0E0E0;
    font-family: "Segoe UI", "Microsoft YaHei", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

/* ===== Main Window ===== */
QMainWindow {
    background-color: #0A0A0F;
}

QMainWindow::separator {
    background-color: #2A2A3A;
    width: 1px;
    height: 1px;
}

/* ===== Menu Bar ===== */
QMenuBar {
    background-color: #0D0D14;
    color: #94A3B8;
    border-bottom: 1px solid #2A2A3A;
    padding: 2px 0;
}

QMenuBar::item {
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
    margin: 2px;
}

QMenuBar::item:selected {
    background-color: #1A1A2E;
    color: #00FF88;
}

QMenu {
    background-color: #12121A;
    border: 1px solid #2A2A3A;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 8px 32px 8px 16px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #1A1A2E;
    color: #00FF88;
}

QMenu::separator {
    height: 1px;
    background: #2A2A3A;
    margin: 4px 8px;
}

/* ===== Tool Bar ===== */
QToolBar {
    background-color: #0D0D14;
    border-bottom: 1px solid #2A2A3A;
    spacing: 8px;
    padding: 4px 8px;
}

/* ===== Title Label ===== */
QLabel#titleLabel {
    color: #00FF88;
    font-size: 18px;
    font-weight: bold;
    font-family: "Segoe UI", "Microsoft YaHei";
}

QLabel#summaryLabel {
    color: #94A3B8;
    font-size: 12px;
    padding: 4px 0;
}

QLabel#sectionTitle {
    color: #00FF88;
    font-size: 13px;
    font-weight: bold;
    padding: 4px 0;
}

/* ===== Buttons ===== */
QPushButton {
    background-color: #1A1A2E;
    color: #E0E0E0;
    border: 1px solid #2A2A3A;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: 13px;
    min-height: 32px;
}

QPushButton:hover {
    background-color: #22223A;
    border-color: #00FF88;
}

QPushButton:pressed {
    background-color: #0D0D14;
    border-color: #00CC6A;
}

QPushButton:disabled {
    background-color: #12121A;
    color: #4A4A5A;
    border-color: #1A1A2A;
}

/* Primary action button */
QPushButton#scanButton {
    background-color: #00FF88;
    border: none;
    color: #0A0A0F;
    font-size: 15px;
    font-weight: bold;
    padding: 10px 32px;
    border-radius: 6px;
    min-height: 40px;
}

QPushButton#scanButton:hover {
    background-color: #33FF9F;
}

QPushButton#scanButton:pressed {
    background-color: #00CC6A;
}

QPushButton#scanButton:disabled {
    background-color: #1A3A2A;
    color: #4A6A5A;
}

/* Destructive / stop button */
QPushButton#stopButton {
    background-color: #EF4444;
    border: none;
    color: #FFFFFF;
    font-weight: bold;
    border-radius: 6px;
    padding: 8px 20px;
}

QPushButton#stopButton:hover {
    background-color: #F87171;
}

QPushButton#stopButton:pressed {
    background-color: #DC2626;
}

QPushButton#stopButton:disabled {
    background-color: #3A1A1A;
    color: #6A4A4A;
}

/* Secondary / outline button */
QPushButton#secondaryButton {
    background-color: transparent;
    color: #00FF88;
    border: 1px solid #00FF88;
}

QPushButton#secondaryButton:hover {
    background-color: rgba(0, 255, 136, 0.1);
}

/* ===== Check Box ===== */
QCheckBox {
    spacing: 8px;
    color: #E0E0E0;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 2px solid #2A2A3A;
    border-radius: 4px;
    background-color: #0A0A0F;
}

QCheckBox::indicator:checked {
    background-color: #00FF88;
    border-color: #00FF88;
}

QCheckBox::indicator:hover {
    border-color: #00FF88;
}

/* ===== Combo Box ===== */
QComboBox {
    background-color: #12121A;
    color: #E0E0E0;
    border: 1px solid #2A2A3A;
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 120px;
    min-height: 32px;
}

QComboBox:hover {
    border-color: #00FF88;
}

QComboBox:focus {
    border-color: #00FF88;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #2A2A3A;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
    background-color: #12121A;
}

QComboBox QAbstractItemView {
    background-color: #12121A;
    border: 1px solid #2A2A3A;
    border-radius: 4px;
    selection-background-color: #1A1A2E;
    selection-color: #00FF88;
    outline: none;
    padding: 4px;
}

/* ===== Progress Bar ===== */
QProgressBar {
    background-color: #12121A;
    border: 1px solid #2A2A3A;
    border-radius: 6px;
    height: 22px;
    text-align: center;
    color: #E0E0E0;
    font-weight: bold;
    font-size: 12px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #00FF88, stop:0.5 #00D4FF, stop:1 #00FF88);
    border-radius: 5px;
}

/* ===== Table Widget ===== */
QTableWidget {
    background-color: #0A0A0F;
    alternate-background-color: #0F0F17;
    border: 1px solid #2A2A3A;
    border-radius: 6px;
    gridline-color: #1A1A2A;
    selection-background-color: #1A2E1A;
    selection-color: #00FF88;
    outline: none;
    font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;
    font-size: 12px;
}

QTableWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #151525;
    color: #E0E0E0;
}

QTableWidget::item:selected {
    background-color: #1A2E1A;
    color: #00FF88;
}

QHeaderView::section {
    background-color: #0D0D14;
    color: #00FF88;
    font-weight: bold;
    font-size: 12px;
    padding: 10px 12px;
    border: none;
    border-bottom: 2px solid #00FF88;
    border-right: 1px solid #1A1A2E;
    font-family: "Segoe UI", "Microsoft YaHei";
}

QHeaderView::section:hover {
    background-color: #12122A;
}

/* ===== Scrollbar ===== */
QScrollBar:vertical {
    background-color: #0A0A0F;
    width: 8px;
    border-radius: 4px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background-color: #2A2A3A;
    border-radius: 4px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #00FF88;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #0A0A0F;
    height: 8px;
    border-radius: 4px;
}

QScrollBar::handle:horizontal {
    background-color: #2A2A3A;
    border-radius: 4px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #00FF88;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ===== Tab Widget ===== */
QTabWidget::pane {
    background-color: #0A0A0F;
    border: 1px solid #2A2A3A;
    border-radius: 6px;
    top: -1px;
}

QTabBar::tab {
    background-color: #0D0D14;
    color: #94A3B8;
    padding: 10px 24px;
    border: 1px solid transparent;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #0A0A0F;
    color: #00FF88;
    border: 1px solid #2A2A3A;
    border-bottom: 2px solid #00FF88;
    font-weight: bold;
}

QTabBar::tab:hover:!selected {
    color: #E0E0E0;
    background-color: #12122A;
}

/* ===== Group Box ===== */
QGroupBox {
    background-color: #0D0D14;
    border: 1px solid #2A2A3A;
    border-radius: 8px;
    margin-top: 16px;
    padding: 16px;
    padding-top: 28px;
    font-weight: bold;
    color: #E0E0E0;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    background-color: #1A1A2E;
    border: 1px solid #00FF88;
    border-radius: 4px;
    color: #00FF88;
    font-size: 12px;
}

/* ===== Plain Text Edit (Log) ===== */
QPlainTextEdit {
    background-color: #050510;
    color: #94A3B8;
    border: 1px solid #2A2A3A;
    border-radius: 6px;
    font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;
    font-size: 12px;
    padding: 8px;
    selection-background-color: #1A2E1A;
    selection-color: #00FF88;
    line-height: 1.6;
}

/* ===== Splitter ===== */
QSplitter::handle {
    background-color: #2A2A3A;
    width: 2px;
}

QSplitter::handle:hover {
    background-color: #00FF88;
}

/* ===== Status Bar ===== */
QStatusBar {
    background-color: #0D0D14;
    color: #94A3B8;
    border-top: 1px solid #2A2A3A;
    font-size: 12px;
    padding: 4px 8px;
}

QStatusBar QLabel {
    color: #94A3B8;
}

/* ===== Spin Box / Double Spin Box ===== */
QSpinBox, QDoubleSpinBox {
    background-color: #12121A;
    color: #E0E0E0;
    border: 1px solid #2A2A3A;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 28px;
}

QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #00FF88;
}

QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #00FF88;
}

/* ===== Line Edit ===== */
QLineEdit {
    background-color: #12121A;
    color: #E0E0E0;
    border: 1px solid #2A2A3A;
    border-radius: 4px;
    padding: 6px 10px;
    min-height: 28px;
}

QLineEdit:hover {
    border-color: #00FF88;
}

QLineEdit:focus {
    border-color: #00FF88;
    background-color: #0D0D14;
}

QLineEdit::placeholder {
    color: #4A4A5A;
}

/* ===== Dialog ===== */
QDialog {
    background-color: #0A0A0F;
}

/* ===== Tool Tip ===== */
QToolTip {
    background-color: #12121A;
    color: #E0E0E0;
    border: 1px solid #00FF88;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

/* ===== Message Box ===== */
QMessageBox {
    background-color: #0A0A0F;
}

QMessageBox QLabel {
    color: #E0E0E0;
}

/* ===== Detail Panel Labels ===== */
QLabel#detailKey {
    color: #94A3B8;
    font-weight: bold;
    font-size: 12px;
}

QLabel#detailValue {
    color: #E0E0E0;
    font-size: 14px;
    font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;
}

/* ===== Separator Line ===== */
QFrame#separator {
    background-color: #2A2A3A;
    max-height: 1px;
}

/* ===== Focus States ===== */
*:focus {
    outline: none;
}

QPushButton:focus {
    border-color: #00FF88;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #00FF88;
}
"""
