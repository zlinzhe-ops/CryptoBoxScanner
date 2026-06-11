"""
Crypto Box Scanner — GUI Application Entry Point
=================================================
每日自动扫描加密货币交易所，识别处于箱体震荡形态的币种。

Usage:
    python main.py

Dependencies:
    pip install -r requirements.txt
"""

import sys
import os

# Ensure the project root is in Python path
_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gui.main_window import MainWindow


def main():
    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Crypto Box Scanner")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("CryptoBoxScanner")

    # Apply dark theme palette as fallback
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
