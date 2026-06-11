"""
Main window for the Crypto Box Scanner GUI application.
"""

import os
import json
import csv
import sys
from datetime import datetime
from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QMenuBar, QMenu, QToolBar, QStatusBar,
    QPushButton, QCheckBox, QComboBox, QLabel,
    QProgressBar, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QPlainTextEdit, QSplitter, QGroupBox,
    QGridLayout, QFrame, QFileDialog, QMessageBox,
    QAbstractItemView, QApplication, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot, QTimer
from PySide6.QtGui import QAction, QColor, QBrush, QFont

from gui.scan_worker import ScanWorker
from gui.settings_dialog import SettingsDialog, DEFAULT_PARAMS
from gui.styles import DARK_THEME
# Heavy imports deferred to first use:
#   from gui.chart_widget import KLineChartWidget   (loads matplotlib, ~2s)
#   from gui.analysis_engine import ...             (needed on coin select)
#   from gui.trend_engine import ...                (needed on coin select in trend mode)

# Add parent directory to path for scanner import
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

OUTPUT_DIR = os.path.join(_parent_dir, "output")

# Lazy import helpers (defer heavy module loading to first use)
def _lazy_chart_widget():
    from gui.chart_widget import KLineChartWidget
    return KLineChartWidget

def _lazy_analysis():
    from gui.analysis_engine import (
        generate_trading_signal, calc_ma, calc_rsi, calc_macd,
        SIGNAL_LABELS, SIGNAL_COLORS,
    )
    return generate_trading_signal, calc_ma, calc_rsi, calc_macd, SIGNAL_LABELS, SIGNAL_COLORS

def _lazy_trend():
    from gui.trend_engine import detect_uptrend, TREND_LABELS, TREND_COLORS
    return detect_uptrend, TREND_LABELS, TREND_COLORS


class MainWindow(QMainWindow):
    """Main application window for the Crypto Box Scanner."""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("虚拟货币箱体震荡选币软件 - Crypto Box Scanner")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 820)

        # State
        self._scan_results: List[Dict] = []
        self._scan_meta: Optional[Dict] = None
        self._scan_params: Dict = DEFAULT_PARAMS.copy()
        self._is_scanning = False
        self._scan_thread: Optional[QThread] = None
        self._scan_worker: Optional[ScanWorker] = None
        self._current_source: str = "gateio"

        self._build_menu_bar()
        self._build_central_ui()
        self._build_status_bar()

        # Apply theme
        self.setStyleSheet(DARK_THEME)

        # Self-test: verify chart widget renders with sample data
        # Defer matplotlib-heavy self-test to 3s after startup (after window is visible)
        QTimer.singleShot(3000, self._chart_self_test)

        # Start FGI refresh timer (every 10 minutes)
        self._fgi_timer = QTimer()
        self._fgi_timer.timeout.connect(self._refresh_fgi)
        self._fgi_timer.start(600000)  # 10 minutes
        QTimer.singleShot(1000, self._refresh_fgi)  # Initial fetch after 1s

    def _get_chart_widget(self):
        """Lazy-init chart widget: loads matplotlib only when first needed."""
        if self.chart_widget is None:
            self._chart_placeholder.hide()
            self.chart_widget = _lazy_chart_widget()()
            self._chart_layout.addWidget(self.chart_widget)
        return self.chart_widget

    def _chart_self_test(self):
        """Verify the chart widget works by plotting sample data on startup."""
        try:
            cw = self._get_chart_widget()
            test_candles = [{'open': 100 + i, 'high': 105 + i, 'low': 99 + i,
                           'close': 103 + i, 'volume': 1000} for i in range(30)]
            ma5 = [100 + i for i in range(30)]
            ma20 = [100 + i for i in range(30)]
            cw.plot_chart(test_candles, 100, 110, 103, "Self-test", ma5, ma20)
            self._append_log("[OK] Chart self-test passed")
        except Exception as e:
            self._append_log(f"[!] Chart self-test failed: {e}")

    # ── Menu Bar ──────────────────────────────────────────────

    def _build_menu_bar(self):
        menu_bar = self.menuBar()

        # ── File menu ──
        file_menu = menu_bar.addMenu("文件(&F)")

        export_csv_action = QAction("导出 CSV...", self)
        export_csv_action.setShortcut("Ctrl+Shift+C")
        export_csv_action.triggered.connect(self._export_csv)
        file_menu.addAction(export_csv_action)

        export_json_action = QAction("导出 JSON...", self)
        export_json_action.setShortcut("Ctrl+Shift+J")
        export_json_action.triggered.connect(self._export_json)
        file_menu.addAction(export_json_action)

        file_menu.addSeparator()

        exit_action = QAction("退出(&X)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ── Settings menu ──
        settings_menu = menu_bar.addMenu("设置(&S)")

        params_action = QAction("扫描参数...", self)
        params_action.setShortcut("Ctrl+P")
        params_action.triggered.connect(self._open_settings)
        settings_menu.addAction(params_action)

        # ── Help menu ──
        help_menu = menu_bar.addMenu("帮助(&H)")

        usage_action = QAction("使用说明", self)
        usage_action.triggered.connect(self._show_usage)
        help_menu.addAction(usage_action)

        help_menu.addSeparator()

        about_action = QAction("关于...", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # ── Central UI ────────────────────────────────────────────

    def _build_central_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(8)

        # ── Top control bar ──
        control_bar = QHBoxLayout()
        control_bar.setSpacing(10)

        # Title
        title = QLabel("Box Scanner — 箱体震荡扫描 v2.0")
        title.setObjectName("titleLabel")
        control_bar.addWidget(title)

        # FGI Indicator (always visible)
        self.fgi_label = QLabel("FGI: —")
        self.fgi_label.setObjectName("fgiLabel")
        self.fgi_label.setToolTip(
            "恐惧贪婪指数 (Fear & Greed Index)\n"
            "0-20 极度恐惧 → 买入窗口\n"
            "20-40 恐惧 → 偏多信号\n"
            "40-60 中性\n"
            "60-80 贪婪 → 偏空信号\n"
            "80-100 极度贪婪 → 见顶风险"
        )
        self.fgi_label.setStyleSheet(
            "color: #94A3B8; font-size: 13px; font-weight: bold; "
            "padding: 2px 8px; border: 1px solid #444; border-radius: 4px;"
        )
        control_bar.addWidget(self.fgi_label)

        control_bar.addStretch()

        # Data source selector
        source_label = QLabel("数据源:")
        control_bar.addWidget(source_label)

        self.source_combo = QComboBox()
        self.source_combo.addItems(["Gate.io", "Binance", "CoinGecko"])
        self.source_combo.setCurrentIndex(0)
        self.source_combo.setToolTip(
            "Gate.io: 国内可直接访问\n"
            "Binance: 需要代理\n"
            "CoinGecko: 免费API，频率限制较严"
        )
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        control_bar.addWidget(self.source_combo)

        # Scan mode selector
        mode_label = QLabel("模式:")
        control_bar.addWidget(mode_label)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["箱体震荡", "上涨趋势"])
        self.mode_combo.setToolTip(
            "箱体震荡: 寻找横盘整理币种\n"
            "上涨趋势: 寻找上升趋势币种"
        )
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)
        control_bar.addWidget(self.mode_combo)

        # Test mode checkbox
        self.test_mode_check = QCheckBox("测试模式 (仅扫20个主流币)")
        self.test_mode_check.setToolTip(
            "[!] 勾选后仅扫描20个主流币种（约10-30秒）\n"
            "取消勾选将扫描全部数千个交易对（约2-5分钟）"
        )
        self.test_mode_check.setStyleSheet(
            "QCheckBox { color: #fdcb6e; font-weight: bold; }"
            "QCheckBox::indicator:checked { background-color: #e17055; }"
        )
        self.test_mode_check.toggled.connect(self._on_test_mode_toggled)
        control_bar.addWidget(self.test_mode_check)

        control_bar.addSpacing(8)

        # Scan button
        self.scan_button = QPushButton("开始扫描")
        self.scan_button.setObjectName("scanButton")
        self.scan_button.setMinimumWidth(140)
        self.scan_button.clicked.connect(self._start_scan)
        control_bar.addWidget(self.scan_button)

        # Stop button
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_scan)
        control_bar.addWidget(self.stop_button)

        main_layout.addLayout(control_bar)

        # ── Progress bar ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # ── Tab widget ──
        self.tab_widget = QTabWidget()

        # Tab 1: Scan Results
        self._build_results_tab()
        self.tab_widget.addTab(self.results_tab, "扫描结果")

        # Tab 2: Scan Log
        self._build_log_tab()
        self.tab_widget.addTab(self.log_tab, "扫描日志")

        main_layout.addWidget(self.tab_widget, stretch=1)

    def _build_results_tab(self):
        """Build the results tab with table and detail panel."""
        self.results_tab = QWidget()
        layout = QVBoxLayout(self.results_tab)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        # Summary label
        self.summary_label = QLabel("就绪 — 点击「开始扫描」启动扫描")
        self.summary_label.setObjectName("summaryLabel")
        layout.addWidget(self.summary_label)

        # Splitter: table on top, detail panel on bottom
        splitter = QSplitter(Qt.Vertical)

        # ── Results table ──
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(True)

        self._setup_table_columns("box")

        splitter.addWidget(self.table)

        # ── Bottom tabs: Details + Signal + Chart ──
        self.bottom_tabs = QTabWidget()

        # Tab 1: Details & Signal
        detail_tab = QWidget()
        detail_layout = QHBoxLayout(detail_tab)
        detail_layout.setContentsMargins(8, 8, 8, 8)
        detail_layout.setSpacing(10)

        # Left: Detail info
        detail_group = QGroupBox("币种详情")
        detail_form = QGridLayout(detail_group)
        detail_form.setSpacing(6)

        self.detail_labels: Dict[str, QLabel] = {}
        self.detail_key_labels: Dict[str, QLabel] = {}  # Store label widgets for text updates
        fields = [
            ("symbol", "交易对:", 0, 0),
            ("support", "支撑位:", 0, 2),
            ("resistance", "阻力位:", 0, 4),
            ("range_pct", "振幅:", 1, 0),
            ("current_price", "当前价:", 1, 2),
            ("position_pct", "位置:", 1, 4),
            ("confidence", "置信度:", 2, 0),
            ("containment", "包含率:", 2, 2),
            ("touches", "触及次数:", 2, 4),
            ("slope", "归一化斜率:", 3, 0),
            ("candles", "K线数:", 3, 2),
            ("atr", "ATR:", 4, 0),
            ("adx", "ADX:", 4, 2),
            ("sentiment", "市场情绪:", 4, 4),
            ("funding", "资金费率风险:", 5, 0),
        ]

        for key, label_text, row, col in fields:
            lbl = QLabel(label_text)
            lbl.setObjectName("detailKey")
            detail_form.addWidget(lbl, row, col)
            val = QLabel("—")
            val.setObjectName("detailValue")
            detail_form.addWidget(val, row, col + 1)
            self.detail_labels[key] = val
            self.detail_key_labels[key] = lbl

        # ── Tooltips for enhanced fields ──
        _tooltips = {
            "atr": ("ATR (Average True Range) — 平均真实波幅\n"
                    "衡量价格波动性的指标，数值越大波动越剧烈。\n"
                    "用于动态止损：止损位 = 支撑/阻力 ± ATR×倍数\n"
                    "例：ATR=5, 止损倍数1.5 → 止损距离=7.5"),
            "adx": ("ADX (Average Directional Index) — 趋势强度指数\n"
                    "范围0-100，衡量趋势的强弱（不判断方向）：\n"
                    "  0-20: 横盘/无趋势 → 箱体策略最佳区间\n"
                    " 20-25: 趋势形成中 → 关注方向选择\n"
                    " 25-50: 明确趋势 → 箱体策略风险升高\n"
                    " 50+: 极强趋势 → 不适合箱体策略"),
            "sentiment": ("市场情绪 — 基于恐惧贪婪指数(FGI)\n"
                          "数据来源: alternative.me (0-100)：\n"
                          "  0-20: 极度恐惧 → 逆向买入窗口\n"
                          " 20-40: 恐惧 → 偏多信号\n"
                          " 40-60: 中性 → 按技术信号操作\n"
                          " 60-80: 贪婪 → 谨慎追高\n"
                          " 80-100: 极度贪婪 → 见顶风险\n"
                          "当前情绪会按比例调整置信度评分"),
            "funding": ("资金费率风险 — 永续合约多头/空头拥挤度\n"
                        "正费率 = 多头付费给空头 → 做多拥挤\n"
                        "负费率 = 空头付费给多头 → 做空拥挤\n"
                        "费率绝对值越高，反向风险越大"),
        }
        for key, tip in _tooltips.items():
            if key in self.detail_key_labels:
                self.detail_key_labels[key].setToolTip(tip)
            if key in self.detail_labels:
                self.detail_labels[key].setToolTip(tip)

        detail_layout.addWidget(detail_group, stretch=3)

        # Right: Trading Signal
        signal_group = QGroupBox("交易信号")
        signal_vbox = QVBoxLayout(signal_group)
        signal_vbox.setSpacing(6)

        self.signal_header = QLabel("选择币种查看交易建议")
        self.signal_header.setStyleSheet("color: #94A3B8; font-size: 13px;")
        self.signal_header.setWordWrap(True)
        signal_vbox.addWidget(self.signal_header)

        self.signal_score_layout = QHBoxLayout()
        self.signal_score_long = QLabel("做多: —")
        self.signal_score_long.setStyleSheet("color: #00FF88; font-size: 14px; font-weight: bold;")
        self.signal_score_short = QLabel("做空: —")
        self.signal_score_short.setStyleSheet("color: #EF4444; font-size: 14px; font-weight: bold;")
        self.signal_score_layout.addWidget(self.signal_score_long)
        self.signal_score_layout.addStretch()
        self.signal_score_layout.addWidget(self.signal_score_short)
        signal_vbox.addLayout(self.signal_score_layout)

        self.signal_reasons_label = QLabel("")
        self.signal_reasons_label.setStyleSheet("color: #94A3B8; font-size: 11px;")
        self.signal_reasons_label.setWordWrap(True)
        signal_vbox.addWidget(self.signal_reasons_label)

        self.signal_risk_label = QLabel("")
        self.signal_risk_label.setStyleSheet("color: #94A3B8; font-size: 12px;")
        self.signal_risk_label.setWordWrap(True)
        signal_vbox.addWidget(self.signal_risk_label)

        self.signal_prices_label = QLabel("")
        self.signal_prices_label.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; color: #E0E0E0; font-size: 12px;"
        )
        self.signal_prices_label.setWordWrap(True)
        signal_vbox.addWidget(self.signal_prices_label)

        signal_vbox.addStretch()
        detail_layout.addWidget(signal_group, stretch=2)

        self.bottom_tabs.addTab(detail_tab, "详情与信号")

        # Tab 2: K-line Chart (lazy-init: matplotlib loaded on first access)
        self._chart_tab = QWidget()
        self._chart_layout = QVBoxLayout(self._chart_tab)
        self._chart_layout.setContentsMargins(4, 4, 4, 4)
        self._chart_placeholder = QLabel("走势图将在选中币种后加载...")
        self._chart_placeholder.setAlignment(Qt.AlignCenter)
        self._chart_placeholder.setStyleSheet("color: #94A3B8; font-size: 14px;")
        self._chart_layout.addWidget(self._chart_placeholder)
        self.chart_widget = None  # Created lazily on first use
        self.bottom_tabs.addTab(self._chart_tab, "K线走势图")

        splitter.addWidget(self.bottom_tabs)

        splitter.setSizes([400, 300])

        layout.addWidget(splitter)

    def _setup_table_columns(self, mode: str):
        """Configure table columns for box range or trend mode."""
        if mode == "trend":
            self.table.setColumnCount(8)
            self.table.setHorizontalHeaderLabels([
                "交易对", "趋势", "评分", "当前价",
                "RSI", "MA20", "5日涨幅", "建议",
            ])
        else:
            self.table.setColumnCount(12)
            self.table.setHorizontalHeaderLabels([
                "交易对", "支撑位", "阻力位", "振幅",
                "当前价", "位置", "置信度", "ADX",
                "ATR%", "费率风险", "包含率", "触及",
            ])

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, self.table.columnCount()):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        # Row click → show details
        self.table.itemSelectionChanged.connect(self._on_row_selected)

    def _build_log_tab(self):
        """Build the scan log tab."""
        self.log_tab = QWidget()
        layout = QVBoxLayout(self.log_tab)
        layout.setContentsMargins(0, 4, 0, 0)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)  # Keep last 5000 lines
        layout.addWidget(self.log_view)

        # Clear button
        clear_layout = QHBoxLayout()
        clear_layout.addStretch()
        clear_btn = QPushButton("清空日志")
        clear_btn.clicked.connect(lambda: self.log_view.clear())
        clear_layout.addWidget(clear_btn)
        layout.addLayout(clear_layout)

    # ── Status Bar ────────────────────────────────────────────

    def _build_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

        self.status_bar.addPermanentWidget(QLabel(""))

        self.last_scan_label = QLabel("")
        self.status_bar.addPermanentWidget(self.last_scan_label)

        self.result_count_label = QLabel("")
        self.status_bar.addPermanentWidget(self.result_count_label)

    # ── Source / Mode / Test Toggle ──────────────────────────

    def _on_mode_changed(self, text: str):
        """Update labels and table when scan mode changes."""
        if text == "上涨趋势":
            labels = {
                "symbol": "交易对:", "support": "趋势:", "resistance": "评分:",
                "range_pct": "RSI:", "current_price": "当前价:", "position_pct": "MA20:",
                "confidence": "MA5:", "containment": "5日涨幅:", "touches": "近期高:",
                "slope": "近期低:", "candles": "建议:",
            }
        else:
            labels = {
                "symbol": "交易对:", "support": "支撑位:", "resistance": "阻力位:",
                "range_pct": "振幅:", "current_price": "当前价:", "position_pct": "位置:",
                "confidence": "置信度:", "containment": "包含率:", "touches": "触及次数:",
                "slope": "归一化斜率:", "candles": "K线数:",
            }
        for key, text in labels.items():
            if key in self.detail_key_labels:
                self.detail_key_labels[key].setText(text)
            if key in self.detail_labels:
                self.detail_labels[key].setText("—")
        self.signal_header.setText("选择币种查看交易建议")

    def _on_source_changed(self, text: str):
        """Show proxy reminder when Binance is selected."""
        if text == "Binance":
            self.summary_label.setText("[!] Binance 需要代理才能访问。请在 设置 > 网络与过滤 中配置代理地址")
            self.summary_label.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 12px;")
        elif text == "CoinGecko":
            self.summary_label.setText("[!] CoinGecko 免费API频率限制较严格，扫描速度较慢")
            self.summary_label.setStyleSheet("color: #FFD700; font-size: 12px;")
        else:
            self.summary_label.setText("[OK] Gate.io 国内可直接访问，无需代理")
            self.summary_label.setStyleSheet("color: #00FF88; font-size: 12px;")

    def _on_test_mode_toggled(self, checked: bool):
        """Show a clear reminder when test mode changes."""
        if checked:
            self.summary_label.setText("[TEST] 测试模式：仅扫描 20 个主流币种")
            self.summary_label.setStyleSheet("color: #FFD700; font-weight: bold; font-size: 13px;")
        else:
            self.summary_label.setText("全量模式：扫描全部交易对（约 2-5 分钟）")
            self.summary_label.setStyleSheet("color: #94A3B8; font-size: 12px;")

    # ── Scan Control ─────────────────────────────────────────

    def _start_scan(self):
        """Start a new scan in a background thread."""
        if self._is_scanning:
            self._append_log("[!] 扫描已在进行中，忽略重复点击")
            return

        try:
            # Clean up any previous thread
            self._cleanup_thread()

            source_map = {"Gate.io": "gateio", "Binance": "binance", "CoinGecko": "coingecko"}
            source = source_map[self.source_combo.currentText()]
            self._current_source = source
            is_test = self.test_mode_check.isChecked()
            scan_mode = "trend" if self.mode_combo.currentText() == "上涨趋势" else "box"

            self._is_scanning = True
            self._scan_results = []
            self._scan_meta = None

            # Update UI state
            self.scan_button.setEnabled(False)
            self.scan_button.setText("扫描中...")
            self.stop_button.setEnabled(True)
            self.source_combo.setEnabled(False)
            self.mode_combo.setEnabled(False)
            self.test_mode_check.setEnabled(False)

            # Setup table columns for current mode
            self._setup_table_columns(scan_mode)
            self.table.setRowCount(0)
            self._clear_details()
            self.summary_label.setText("正在扫描中...")

            # Reset & show progress bar
            self.progress_bar.setVisible(True)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("准备中...")

            # Create worker and thread
            self._scan_thread = QThread()
            self._scan_worker = ScanWorker(
                source=source,
                is_test=is_test,
                params=self._scan_params,
                scan_mode=scan_mode,
            )

            self._scan_worker.moveToThread(self._scan_thread)

            # Connect worker signals
            self._scan_thread.started.connect(self._scan_worker.run)
            self._scan_worker.progress.connect(self._on_progress)
            self._scan_worker.result_found.connect(self._on_result_found)
            self._scan_worker.finished.connect(self._on_scan_finished)
            self._scan_worker.error_occurred.connect(self._on_scan_error)
            self._scan_worker.log_message.connect(self._on_log_message)
            self._scan_worker.status_update.connect(self._on_status_update)
            self._scan_worker.scan_complete.connect(self._on_scan_complete)

            # Thread cleanup chain
            self._scan_worker.scan_complete.connect(self._scan_thread.quit)
            self._scan_thread.finished.connect(self._cleanup_after_scan)

            self._scan_thread.start()
            self.status_label.setText("正在扫描...")
            self._append_log("--- 开始扫描 ---")

        except Exception as e:
            import traceback
            self._is_scanning = False
            self._restore_ui_after_scan()
            err_msg = f"启动扫描失败: {e}\n{traceback.format_exc()}"
            self._append_log(f"[ERROR] {err_msg}")
            QMessageBox.critical(self, "启动扫描失败", err_msg)

    def _stop_scan(self):
        """Request the scan to stop."""
        if self._scan_worker:
            self._scan_worker.request_stop()
            self.stop_button.setEnabled(False)
            self.stop_button.setText("停止中...")
            self.status_label.setText("正在停止...")

    def _cleanup_thread(self):
        """Clean up any existing thread."""
        if self._scan_thread and self._scan_thread.isRunning():
            if self._scan_worker:
                self._scan_worker.request_stop()
            self._scan_thread.quit()
            if not self._scan_thread.wait(3000):
                self._append_log("[!] 等待上一线程超时，强制终止")
                self._scan_thread.terminate()
                self._scan_thread.wait(2000)
        # Reset references
        self._scan_thread = None
        self._scan_worker = None

    @Slot()
    def _cleanup_after_scan(self):
        """Cleanup after thread finishes (called in main thread)."""
        if self._scan_thread:
            self._scan_thread.deleteLater()
            self._scan_thread = None
            self._scan_worker = None

    def _restore_ui_after_scan(self):
        """Restore UI controls to pre-scan state."""
        self.scan_button.setEnabled(True)
        self.scan_button.setText("开始扫描")
        self.stop_button.setEnabled(False)
        self.stop_button.setText("停止")
        self.source_combo.setEnabled(True)
        self.mode_combo.setEnabled(True)
        self.test_mode_check.setEnabled(True)

    # ── Signal Handlers ──────────────────────────────────────

    @Slot(int, int, str)
    def _on_progress(self, current: int, total: int, symbol: str):
        """Handle progress update from worker."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        pct = current / total * 100 if total > 0 else 0
        self.progress_bar.setFormat(f"{symbol}  [{current}/{total}] {pct:.1f}%")
        self.status_label.setText(f"扫描中: {symbol} ({current}/{total})")

    @Slot(object)
    def _on_result_found(self, result: Dict):
        """Handle a new box range result from worker."""
        self._scan_results.append(result)
        self._add_table_row(result)
        self.result_count_label.setText(f"已发现: {len(self._scan_results)} 个箱体")

    @Slot(object, object)
    def _on_scan_finished(self, results: List[Dict], meta: Dict):
        """Handle scan completion with results."""
        self._scan_results = results
        self._scan_meta = meta

        # Rebuild table with sorted results
        self._rebuild_table(results)

        # Update summary
        total = meta.get("total_pairs_found", 0)
        passed = len(results)
        source = meta.get("data_source", "Unknown")
        scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if passed > 0:
            avg_conf = sum(r["confidence"] for r in results) / passed
            best = results[0]
            self.summary_label.setText(
                f"[OK] 扫描完成 | 数据源: {source} | "
                f"共扫描 {total} 个 | 符合条件: {passed} 个 | "
                f"平均置信度: {avg_conf:.1f} | "
                f"最佳: {best['symbol']} (置信度 {best['confidence']})"
            )
        else:
            self.summary_label.setText(
                f"[INFO] 扫描完成 | 数据源: {source} | "
                f"共扫描 {total} 个 | 当前没有符合箱体条件的币种"
            )

        self.last_scan_label.setText(f"上次扫描: {scan_time}")
        self.result_count_label.setText(f"结果: {passed} 个箱体")

        # Auto-save results
        self._auto_save_results()

    @Slot(str)
    def _on_scan_error(self, error_msg: str):
        """Handle scan error."""
        self._append_log(f"[ERROR] {error_msg}")
        QMessageBox.critical(
            self, "扫描错误",
            f"扫描过程中发生错误：\n\n{error_msg}"
        )

    @Slot(str)
    def _on_log_message(self, message: str):
        """Handle log message from worker."""
        self._append_log(message)

    @Slot(str)
    def _on_status_update(self, message: str):
        """Handle status update from worker."""
        self.status_label.setText(message)

    @Slot()
    def _on_scan_complete(self):
        """Handle scan completion (success or error) — restore UI."""
        self._is_scanning = False
        self._restore_ui_after_scan()
        self.progress_bar.setVisible(False)
        self.status_label.setText("就绪")
        self._append_log("--- 扫描结束 ---\n")

    # ── Table Operations ─────────────────────────────────────

    def _add_table_row(self, result: Dict):
        """Add a single result row to the table."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        self._fill_row(row, result)

    def _rebuild_table(self, results: List[Dict]):
        """Rebuild the entire table from results list."""
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for result in results:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._fill_row(row, result)
        self.table.setSortingEnabled(True)

    def _fill_row(self, row: int, result: Dict):
        """Fill a table row — adapts to box or trend mode."""
        try:
            self._do_fill_row(row, result)
        except Exception as e:
            self._append_log(f"[CHART] _fill_row error for {result.get('symbol','?')}: {e}")

    def _do_fill_row(self, row: int, result: Dict):
        """Internal: fill a table row."""
        mode = self.mode_combo.currentText()

        if mode == "上涨趋势":
            _, TLABELS, TCOLORS = _lazy_trend()
            items = [
                self._make_item(result["symbol"], Qt.AlignLeft),
                self._make_item(TLABELS.get(result.get("trend",""), result.get("trend","")), Qt.AlignCenter),
                self._make_item(str(result.get("score",0)), Qt.AlignCenter),
                self._make_item(self._fmt_price(result["current_price"]), Qt.AlignRight),
                self._make_item(f"{result.get('rsi',50):.0f}", Qt.AlignCenter),
                self._make_item(self._fmt_price(result.get("ma20",0)), Qt.AlignRight),
                self._make_item(f"{result.get('gain_5d_pct',0):+.1f}%", Qt.AlignRight),
                self._make_item(result.get("suggestion","—"), Qt.AlignLeft),
            ]
            # Color the trend cell
            trend = result.get("trend","")
            color = QColor(TCOLORS.get(trend, "#94A3B8"))
            items[1].setForeground(QBrush(color))
            # Color the score
            score = result.get("score",0)
            if score >= 70: items[2].setForeground(QBrush(QColor("#00FF88")))
            elif score >= 50: items[2].setForeground(QBrush(QColor("#FFD700")))
        else:
            items = [
                self._make_item(result["symbol"], Qt.AlignLeft),
                self._make_item(self._fmt_price(result["support"]), Qt.AlignRight),
                self._make_item(self._fmt_price(result["resistance"]), Qt.AlignRight),
                self._make_item(f"{result['range_pct']:.1f}%", Qt.AlignRight),
                self._make_item(self._fmt_price(result["current_price"]), Qt.AlignRight),
            ]
            pos = result["position_pct"]
            pos_item = self._make_item(f"{pos:.1f}%", Qt.AlignRight)
            if pos <= 30: pos_item.setForeground(QBrush(QColor("#00FF88")))
            elif pos >= 70: pos_item.setForeground(QBrush(QColor("#EF4444")))
            else: pos_item.setForeground(QBrush(QColor("#FFD700")))
            items.append(pos_item)

            conf = result["confidence"]
            if conf >= 80: conf_text, c = f"★ {conf}", QColor("#FFD700")
            elif conf >= 65: conf_text, c = f"☆ {conf}", QColor("#FFD700")
            else: conf_text, c = f"  {conf}", QColor("#94A3B8")
            ci = self._make_item(conf_text, Qt.AlignCenter); ci.setForeground(QBrush(c))
            items.append(ci)

            # ADX column
            adx = result.get("adx", 0)
            adx_text = f"{adx:.0f}" if adx > 0 else "—"
            adx_item = self._make_item(adx_text, Qt.AlignCenter)
            if adx > 0:
                if adx < 20: adx_item.setForeground(QBrush(QColor("#00FF88")))
                elif adx < 25: adx_item.setForeground(QBrush(QColor("#FFD700")))
                elif adx < 35: adx_item.setForeground(QBrush(QColor("#FF9800")))
                else: adx_item.setForeground(QBrush(QColor("#EF4444")))
            items.append(adx_item)

            # ATR% column
            atr_pct = result.get("atr_pct", 0)
            atr_text = f"{atr_pct:.1f}%" if atr_pct > 0 else "—"
            items.append(self._make_item(atr_text, Qt.AlignRight))

            # Funding rate risk column
            fr = result.get("funding_risk", {}) or {}
            fr_risk = fr.get("risk_level", "unknown")
            if fr_risk == "extreme":
                fr_text, fr_color = "⚠ 极高", QColor("#EF4444")
            elif fr_risk == "high":
                fr_text, fr_color = "▲ 偏高", QColor("#FF9800")
            elif fr_risk == "normal":
                fr_text, fr_color = "正常", QColor("#00FF88")
            else:
                fr_text, fr_color = "—", QColor("#94A3B8")
            fr_item = self._make_item(fr_text, Qt.AlignCenter)
            fr_item.setForeground(QBrush(fr_color))
            items.append(fr_item)

            items.append(self._make_item(f"{result.get('containment_ratio',0):.1%}", Qt.AlignRight))
            r_t, s_t = result.get("resistance_touches",0), result.get("support_touches",0)
            items.append(self._make_item(f"R:{r_t}/S:{s_t}", Qt.AlignCenter))

        for col, item in enumerate(items):
            self.table.setItem(row, col, item)

    def _make_item(self, text: str, align: int = Qt.AlignLeft) -> QTableWidgetItem:
        """Create a table item with the given text and alignment."""
        item = QTableWidgetItem(text)
        item.setTextAlignment(align | Qt.AlignVCenter)
        return item

    def _clear_details(self):
        """Clear the detail panel and chart."""
        for label in self.detail_labels.values():
            label.setText("—")
        self.signal_header.setText("选择币种查看交易建议")
        self.signal_header.setStyleSheet("color: #94A3B8; font-size: 13px;")
        self.signal_score_long.setText("做多: —")
        self.signal_score_short.setText("做空: —")
        self.signal_reasons_label.setText("")
        self.signal_risk_label.setText("")
        self.signal_prices_label.setText("")
        self._get_chart_widget().plot_chart([], 0, 0, 0, "")

    @Slot()
    def _on_row_selected(self):
        """Handle row selection in the results table."""
        try:
            selected_rows = self.table.selectionModel().selectedRows()
            if not selected_rows:
                self._clear_details()
                return

            row = selected_rows[0].row()
            if row < 0 or row >= self.table.rowCount():
                self._clear_details()
                return

            symbol_item = self.table.item(row, 0)
            if not symbol_item:
                self._clear_details()
                return

            symbol = symbol_item.text().strip()

            result = None
            for r in self._scan_results:
                if r["symbol"] == symbol:
                    result = r
                    break

            if result is None:
                self._append_log(f"[CHART] WARN: {symbol} not in results ({len(self._scan_results)} total)")
                self._clear_details()
                return

            # DIAGNOSTIC: log the actual keys in the result dict
            keys = list(result.keys())
            has_atr = "atr_value" in result
            has_adx = "adx" in result
            has_fgi = "fgi_value" in result
            has_fr = "funding_risk" in result
            self._append_log(f"[DIAG] Result keys: atr={has_atr}, adx={has_adx}, fgi={has_fgi}, funding={has_fr}")
            if has_atr:
                self._append_log(f"[DIAG] ATR={result.get('atr_value')}, ADX={result.get('adx')}, FGI={result.get('fgi_value')}")

            self._show_detail(result)
            self._fetch_detail_data(result)
        except Exception as e:
            self._append_log(f"[CHART] _on_row_selected CRASHED: {e}")
            import traceback
            self._append_log(traceback.format_exc()[-500:])

    def _refresh_detail_panel(self, r: Dict):
        """Unified detail panel refresh — called from both _show_detail and _update_chart.
        Handles box mode, trend mode, and all enhanced fields (ATR/ADX/FGI/funding)."""
        mode = self.mode_combo.currentText()

        if mode == "上涨趋势":
            _, TLABELS, _ = _lazy_trend()
            trend = r.get("trend", "—")
            details = {
                "symbol": r["symbol"],
                "support": TLABELS.get(trend, trend),
                "resistance": str(r.get("score", "—")),
                "range_pct": f"{r.get('rsi', 50):.0f}",
                "current_price": self._fmt_price(r.get("current_price", 0)),
                "position_pct": self._fmt_price(r.get("ma20", 0)),
                "confidence": self._fmt_price(r.get("ma5", 0)),
                "containment": f"{r.get('gain_5d_pct', 0):+.1f}%",
                "touches": self._fmt_price(r.get("recent_high", 0)),
                "slope": self._fmt_price(r.get("recent_low", 0)),
                "candles": str(r.get("suggestion", "—")),
            }
            label_texts = {
                "symbol": "交易对:", "support": "趋势:", "resistance": "评分:",
                "range_pct": "RSI:", "current_price": "当前价:", "position_pct": "MA20:",
                "confidence": "MA5:", "containment": "5日涨幅:", "touches": "近期高:",
                "slope": "近期低:", "candles": "建议:",
                "atr": "ATR:", "adx": "ADX:", "sentiment": "市场情绪:", "funding": "资金费率:",
            }
        else:
            label_texts = {
                "symbol": "交易对:", "support": "支撑位:", "resistance": "阻力位:",
                "range_pct": "振幅:", "current_price": "当前价:", "position_pct": "位置:",
                "confidence": "置信度:", "containment": "包含率:", "touches": "触及次数:",
                "slope": "归一化斜率:", "candles": "K线数:",
                "atr": "ATR:", "adx": "ADX:", "sentiment": "市场情绪:", "funding": "资金费率:",
            }
            details = {
                "symbol": r["symbol"],
                "support": self._fmt_price(r.get("support", 0)),
                "resistance": self._fmt_price(r.get("resistance", 0)),
                "range_pct": f"{r.get('range_pct', 0):.2f}%",
                "current_price": self._fmt_price(r.get("current_price", 0)),
                "position_pct": f"{r.get('position_pct', 0):.1f}%",
                "confidence": self._fmt_confidence(r.get("confidence", r.get("score", 0))),
                "containment": f"{r.get('containment_ratio', 0):.1%}",
                "touches": f"R:{r.get('resistance_touches', 0)}/S:{r.get('support_touches', 0)}",
                "slope": f"{r.get('normalized_slope', 0):.4f}",
                "candles": f"{r.get('candle_count', 0)} 根",
            }

        # ── Enhanced fields (both modes) ──
        atr_val = r.get("atr_value", 0)
        atr_pct = r.get("atr_pct", 0)
        details["atr"] = f"{self._fmt_price(atr_val)} ({atr_pct:.1f}%)" if atr_val else "—"

        adx_val = r.get("adx", 0)
        trend_str = r.get("trend_strength", "")
        details["adx"] = f"{adx_val:.1f} ({trend_str})" if adx_val else "—"

        fgi_val = r.get("fgi_value")
        if fgi_val is not None:
            fgi_cls = r.get("fgi_classification", "")
            details["sentiment"] = f"FGI={fgi_val} ({fgi_cls})"
        else:
            details["sentiment"] = "—"

        fr = r.get("funding_risk")
        if fr:
            fr_rate = fr.get("rate_pct", 0)
            fr_risk = fr.get("risk_level", "unknown")
            if fr_rate:
                details["funding"] = f"{fr_rate:+.4f}% ({fr_risk})"
            elif fr_risk == "unknown":
                details["funding"] = "—"
            else:
                details["funding"] = "正常"
        else:
            details["funding"] = "—"

        # Apply to all labels
        self._detail_label_texts = label_texts
        for key, value in details.items():
            if key in self.detail_labels:
                if key in self.detail_key_labels:
                    self.detail_key_labels[key].setText(label_texts.get(key, key))
                self.detail_labels[key].setText(value)

    def _show_detail(self, r: Dict):
        """Display detailed information about a selected coin."""
        try:
            self._refresh_detail_panel(r)
        except Exception as e:
            self._append_log(f"[CHART] _show_detail error: {e}")

        # Show loading state in signal panel (don't touch chart until data arrives)
        self.signal_header.setText(f"正在分析 {r['symbol']}...")
        self.signal_score_long.setText("做多: —")
        self.signal_score_short.setText("做空: —")
        self.signal_reasons_label.setText("")
        self.signal_risk_label.setText("")
        self.signal_prices_label.setText("")

    def _fetch_detail_data(self, result: Dict):
        """Fetch detailed kline data in background thread, poll result from main thread."""
        import threading
        symbol = result["symbol"]
        source = self._current_source
        self._append_log(f"[CHART] Fetching detail data for {symbol}...")

        result_holder = {"candles": None, "error": None, "done": False}

        def fetch():
            try:
                import crypto_box_scanner as scanner
                session = scanner._create_session()
                candles = None
                if source == "gateio":
                    gate_symbol = symbol.replace("USDT", "_USDT") if symbol.endswith("USDT") and "_" not in symbol else symbol
                    candles = scanner.gateio_fetch_klines(session, gate_symbol, interval=scanner.KLINE_INTERVAL, limit=90)
                elif source == "binance":
                    candles = scanner.binance_fetch_klines(session, symbol, interval=scanner.KLINE_INTERVAL, limit=90)
                session.close()
                result_holder["candles"] = candles
            except Exception as e:
                import traceback
                result_holder["error"] = f"{e}\n{traceback.format_exc()[-300:]}"
            finally:
                result_holder["done"] = True

        t = threading.Thread(target=fetch, daemon=True)
        t.start()

        # Poll from MAIN thread (QTimer only works in main thread)
        def check():
            if result_holder["done"]:
                if result_holder["error"]:
                    self._append_log(f"[CHART] fetch error: {result_holder['error']}")
                    self._on_detail_data_ready(None, symbol)
                else:
                    c = result_holder["candles"]
                    self._on_detail_data_ready(c, symbol)
            else:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(100, check)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, check)

    @Slot(object, str)
    def _on_detail_data_ready(self, candles, symbol):
        """Handle detailed kline data — compute analysis and update chart."""
        try:
            self._append_log(f"[CHART] Data received for {symbol}: {len(candles) if candles else 0} candles")
            if not candles:
                self.signal_header.setText(f"{symbol}: 无法获取走势数据")
                return

            # Find the selected result
            result = None
            for r in self._scan_results:
                if r["symbol"] == symbol:
                    result = r
                    break
            if not result:
                self._append_log(f"[CHART] WARN: symbol {symbol} not in scan results")
                return
        except Exception as e:
            self._append_log(f"[CHART] _on_detail_data_ready phase1 error: {e}")
            return

        # Compute technical indicators
        try:
            generate_trading_signal, calc_ma, calc_rsi, calc_macd, SIGNAL_LABELS, SIGNAL_COLORS = _lazy_analysis()
            closes = [c["close"] for c in candles]
            vols = [c.get("volume", 0) for c in candles]
            ma5 = calc_ma(closes, 5)
            ma20 = calc_ma(closes, 20)
            rsi_vals = calc_rsi(closes, 14)

            # Generate analysis based on mode
            mode = self.mode_combo.currentText()
            if mode == "上涨趋势":
                detect_uptrend, TLABELS, TCOLORS = _lazy_trend()
                trend_result = detect_uptrend(candles, vols)
                if trend_result:
                    signal_data = {
                        "signal": trend_result["trend"],
                        "score_long": trend_result["score"],
                        "score_short": 0,
                        "reasons": trend_result.get("reasons", []),
                        "risk_level": "LOW" if trend_result["score"] >= 70 else "MEDIUM",
                        "rsi": trend_result.get("rsi", 50),
                        "volume_change_pct": 0,
                        "risk_reward_ratio": 1.5,
                        "suggested_entry": trend_result["entry"],
                        "suggested_stop_loss": trend_result["stop_loss"],
                        "suggested_take_profit": trend_result["target"],
                    }
                else:
                    signal_data = {
                        "signal": "NEUTRAL", "score_long": 0, "score_short": 0,
                        "reasons": ["当前无明显趋势信号"],
                        "risk_level": "HIGH", "rsi": rsi_vals[-1] if rsi_vals else 50,
                        "volume_change_pct": 0, "risk_reward_ratio": 0,
                        "suggested_entry": result["current_price"],
                        "suggested_stop_loss": result["current_price"] * 0.95,
                        "suggested_take_profit": result["current_price"] * 1.05,
                    }
                supp = min(c["low"] for c in candles[-15:]) if len(candles) >= 15 else candles[0]["low"]
                res = max(c["high"] for c in candles[-15:]) if len(candles) >= 15 else candles[0]["high"]
                result_for_chart = {**result, "support": supp, "resistance": res}
            else:
                # Pass funding risk info to signal generator
                funding_risk = result.get("funding_risk")
                signal_data = generate_trading_signal(result, candles, vols, funding_risk=funding_risk)
                result_for_chart = result

            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._update_chart(
                candles, symbol, result_for_chart, signal_data, ma5, ma20, rsi_vals
            ))
        except Exception as e:
            self._append_log(f"[CHART] _on_detail_data_ready phase2 error: {e}")
            import traceback
            self._append_log(traceback.format_exc()[-300:])

    def _update_chart(self, candles, symbol, result, signal, ma5, ma20, rsi_vals):
        """Update chart and signal panel (called via QTimer to avoid paint loss)."""
        _, _, _, _, SIGNAL_LABELS, SIGNAL_COLORS = _lazy_analysis()
        mode = self.mode_combo.currentText()
        try:
            self._get_chart_widget().plot_chart(
                candles=candles,
                support=result.get("support", 0),
                resistance=result.get("resistance", 0),
                current_price=result["current_price"],
                symbol=symbol,
                ma5=ma5,
                ma20=ma20,
            )
            self._append_log(f"[CHART] Plot updated for {symbol}")
        except Exception as e:
            self._append_log(f"[CHART] Plot FAILED: {e}")

        # Update signal panel
        if mode == "上涨趋势":
            _, TLABELS, TCOLORS = _lazy_trend()
            sig = signal["signal"]
            label = TLABELS.get(sig, sig)
            color = TCOLORS.get(sig, "#94A3B8")
            self.signal_header.setText(f"<b>{label}</b> — 评分: {signal['score_long']} | RSI: {signal['rsi']:.0f}")
            self.signal_header.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: bold;")
            self.signal_score_long.setText(f"评分: {signal['score_long']}")
            self.signal_score_short.setText("")
        else:
            sig = signal["signal"]
            atr_val = signal.get("atr", 0)
            adx_val = signal.get("adx", 0)
            header_parts = [
                f"<b>{SIGNAL_LABELS.get(sig, sig)}</b>",
                f"风险: {signal['risk_level']}",
                f"RSI: {signal['rsi']:.0f}",
                f"ADX: {adx_val:.0f}" if adx_val > 0 else "",
                f"量变: {signal['volume_change_pct']:+.0f}%",
            ]
            self.signal_header.setText(" — ".join(p for p in header_parts if p))
            self.signal_header.setStyleSheet(
                f"color: {SIGNAL_COLORS.get(sig, '#94A3B8')}; font-size: 15px; font-weight: bold;"
            )
            self.signal_score_long.setText(f"做多: {signal['score_long']}")
            self.signal_score_short.setText(f"做空: {signal['score_short']}")

        reasons_text = "<br>".join(signal.get("reasons", [])[:10])
        self.signal_reasons_label.setText(reasons_text)

        risk_color = "#00FF88" if signal["risk_level"] == "LOW" else "#FFD700" if signal["risk_level"] == "MEDIUM" else "#EF4444"
        atr_info = f" | ATR: {self._fmt_price(atr_val)}" if atr_val > 0 else ""
        self.signal_risk_label.setText(
            f"风险等级: <span style='color:{risk_color};font-weight:bold;'>{signal['risk_level']}</span> | "
            f"风险收益比: {signal.get('risk_reward_ratio', '—')}"
            f"{atr_info}"
        )

        self.signal_prices_label.setText(
            f"建议入场: {self._fmt_price(signal['suggested_entry'])}  |  "
            f"止损: {self._fmt_price(signal['suggested_stop_loss'])}  |  "
            f"止盈: {self._fmt_price(signal['suggested_take_profit'])}"
        )

        # ── Refresh detail panel with latest data ──
        self._refresh_detail_panel(result)

    # ── Export ───────────────────────────────────────────────

    def _export_csv(self):
        """Export scan results to CSV file."""
        if not self._scan_results:
            QMessageBox.information(self, "导出 CSV", "没有可导出的扫描结果。")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", self._default_export_path("csv"),
            "CSV 文件 (*.csv)"
        )
        if not filepath:
            return

        try:
            with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "交易对", "支撑位", "阻力位", "振幅(%)",
                    "当前价", "位置(%)", "置信度", "包含率",
                    "阻力触及次数", "支撑触及次数", "归一化斜率",
                ])
                for r in self._scan_results:
                    writer.writerow([
                        r["symbol"],
                        r["support"],
                        r["resistance"],
                        r["range_pct"],
                        r["current_price"],
                        r["position_pct"],
                        r["confidence"],
                        r.get("containment_ratio", ""),
                        r.get("resistance_touches", ""),
                        r.get("support_touches", ""),
                        r.get("normalized_slope", ""),
                    ])
            QMessageBox.information(self, "导出成功", f"已导出至:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 CSV 时出错:\n{e}")

    def _export_json(self):
        """Export scan results to JSON file."""
        if not self._scan_results:
            QMessageBox.information(self, "导出 JSON", "没有可导出的扫描结果。")
            return

        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出 JSON", self._default_export_path("json"),
            "JSON 文件 (*.json)"
        )
        if not filepath:
            return

        try:
            output = {
                "meta": self._scan_meta,
                "results": self._scan_results,
                "export_time": datetime.now().isoformat(),
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "导出成功", f"已导出至:\n{filepath}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出 JSON 时出错:\n{e}")

    def _default_export_path(self, ext: str) -> str:
        """Generate default export filename."""
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(OUTPUT_DIR, f"box_scan_export_{timestamp}.{ext}")

    def _auto_save_results(self):
        """Auto-save results to JSON (mirrors CLI behavior)."""
        if not self._scan_results or not self._scan_meta:
            return
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)

            avg_conf = sum(r["confidence"] for r in self._scan_results) / len(self._scan_results)

            dist = {"3-5%": 0, "5-10%": 0, "10-15%": 0, "15-25%": 0}
            for r in self._scan_results:
                rp = r["range_pct"]
                if rp <= 5:
                    dist["3-5%"] += 1
                elif rp <= 10:
                    dist["5-10%"] += 1
                elif rp <= 15:
                    dist["10-15%"] += 1
                else:
                    dist["15-25%"] += 1

            output = {
                "meta": self._scan_meta,
                "results": self._scan_results,
                "summary": {
                    "avg_confidence": round(avg_conf, 1),
                    "range_distribution": dist,
                },
            }

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(OUTPUT_DIR, f"box_scan_{timestamp}.json")
            latest_path = os.path.join(OUTPUT_DIR, "box_scan_latest.json")

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

            self._append_log(f"[SAVED] 结果已保存至: {filepath}")
        except Exception as e:
            self._append_log(f"[!] 自动保存失败: {e}")

    # ── Settings ─────────────────────────────────────────────

    def _open_settings(self):
        """Open the settings dialog."""
        dialog = SettingsDialog(current_params=self._scan_params, parent=self)
        if dialog.exec():
            self._scan_params = dialog.get_params()
            self._append_log("[CONFIG] 扫描参数已更新")

    # ── Help / About ─────────────────────────────────────────

    def _show_usage(self):
        """Show usage guide dialog."""
        text = (
            "<h3>使用说明</h3>"
            "<p><b>1. 选择数据源</b><br>"
            "Gate.io: 国内用户推荐，无需代理可直接访问。<br>"
            "Binance: 数据量大，需要代理。<br>"
            "CoinGecko: 免费API，频率限制较严格，速度较慢。</p>"
            "<p><b>2. 开始扫描</b><br>"
            "点击「开始扫描」按钮启动全量扫描。<br>"
            "勾选「测试模式」仅扫描20个主流币种，约10秒完成。</p>"
            "<p><b>3. 查看结果</b><br>"
            "结果按置信度从高到低排列。<br>"
            "★ 表示置信度 ≥80 的高质量箱体。<br>"
            "☆ 表示置信度 ≥65 的较优箱体。<br>"
            "点击任意行可查看该币种的详细信息。</p>"
            "<p><b>4. 导出结果</b><br>"
            "文件 → 导出 CSV/JSON 可保存扫描结果。<br>"
            "每次扫描结果会自动保存到 output 目录。</p>"
            "<p><b>位置百分比说明</b><br>"
            "<span style='color:#00FF88;'>●</span> 0%-30%: 接近支撑位，买入参考区。<br>"
            "<span style='color:#FFD700;'>●</span> 30%-70%: 箱体中部。<br>"
            "<span style='color:#EF4444;'>●</span> 70%-100%: 接近阻力位，卖出参考区。</p>"
            "<p><b>免责声明</b><br>"
            "本工具仅供学习参考，不构成任何投资建议。</p>"
        )
        QMessageBox.information(self, "使用说明", text)

    def _show_about(self):
        """Show about dialog."""
        text = (
            "<h3>虚拟货币箱体震荡选币软件</h3>"
            "<p>版本 1.0 (GUI)</p>"
            "<p>每日扫描加密货币交易所，识别处于<b>箱体震荡</b>（横盘整理）形态的币种，"
            "列出支撑位和阻力位，辅助交易决策。</p>"
            "<p><b>数据源:</b> Gate.io / Binance / CoinGecko</p>"
            "<p><b>技术栈:</b> Python + PySide6 (Qt)</p>"
            "<hr>"
            "<p style='color: #94A3B8;'>本工具仅供学习和参考，不构成任何投资建议。</p>"
        )
        QMessageBox.about(self, "关于", text)

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _fmt_price(price: float) -> str:
        """Smart price formatting."""
        if price >= 1000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:.2f}"
        elif price >= 0.01:
            return f"{price:.4f}"
        elif price >= 0.0001:
            return f"{price:.6f}"
        else:
            return f"{price:.8f}"

    @staticmethod
    def _fmt_confidence(conf: int) -> str:
        """Format confidence score with star indicator."""
        if conf >= 80:
            return f"★ {conf} (高质量)"
        elif conf >= 65:
            return f"☆ {conf} (较优)"
        else:
            return f"{conf}"

    def _append_log(self, message: str):
        """Append a message to the log view."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    # ── FGI Refresh ───────────────────────────────────────────

    def _refresh_fgi(self):
        """Fetch latest Fear & Greed Index and update the label.
        Uses urllib internally which natively supports Windows system proxy."""
        try:
            import crypto_box_scanner as scanner
            fgi = scanner.fetch_fear_greed_index()  # urllib handles system proxy automatically
            if fgi:
                value = int(fgi.get("value", 50))
                adj = scanner.get_fgi_adjustment(value)
                cls = adj["classification"]
                if value <= 20:
                    color = "#00FF88"
                elif value <= 40:
                    color = "#88FFBB"
                elif value <= 60:
                    color = "#FFD700"
                elif value <= 80:
                    color = "#FF9800"
                else:
                    color = "#EF4444"
                self.fgi_label.setText(f"FGI: {value} ({cls})")
                self.fgi_label.setStyleSheet(
                    f"color: {color}; font-size: 13px; font-weight: bold; "
                    "padding: 2px 8px; border: 1px solid #444; border-radius: 4px;"
                )
            else:
                self.fgi_label.setText("FGI: —")
        except Exception as e:
            self.fgi_label.setText("FGI: 错误")
            self._append_log(f"[FGI] {e}")

    # ── Window Close ─────────────────────────────────────────

    def closeEvent(self, event):
        """Handle window close event — ensure scan thread is stopped."""
        if self._is_scanning:
            reply = QMessageBox.question(
                self, "确认退出",
                "扫描正在进行中，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            self._cleanup_thread()
        event.accept()
