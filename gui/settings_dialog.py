"""
Settings dialog for configuring scan parameters and proxy settings.
"""

import os
from typing import Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QPushButton, QTabWidget, QWidget,
    QFormLayout, QDialogButtonBox, QMessageBox,
)
from PySide6.QtCore import Qt


DEFAULT_PARAMS = {
    "kline_interval": "1d",
    "kline_limit": 30,
    "top_bottom_n": 5,
    "touch_threshold_pct": 2.0,
    "min_touches": 2,
    "min_containment": 0.70,
    "max_normalized_slope": 0.15,
    "min_range_pct": 3.0,
    "max_range_pct": 25.0,
    "min_volume_usdt": 1_000_000,
    "request_delay": 0.5,
    "proxy": "",
    # 新增高级参数
    "enable_fgi": True,           # 启用恐惧贪婪指数
    "enable_funding_rate": True,  # 启用资金费率扫描
    "adx_threshold": 25.0,        # ADX趋势阈值
    "vol_breakout_mult": 1.5,     # 成交量突破倍数
    "atr_stop_mult": 1.5,         # ATR止损倍数
}


class SettingsDialog(QDialog):
    """Dialog for editing scan and network settings."""

    def __init__(self, current_params: Optional[Dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("扫描参数设置")
        self.setMinimumWidth(520)
        self.resize(560, 600)
        self.setModal(True)

        # Merge current params with defaults
        self._params = DEFAULT_PARAMS.copy()
        if current_params:
            self._params.update(current_params)

        self._build_ui()
        self._load_params()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Tab widget
        tabs = QTabWidget()

        # ── Tab 1: Detection Parameters ──
        detect_tab = QWidget()
        detect_layout = QVBoxLayout(detect_tab)

        # K-line settings
        kline_group = QGroupBox("K线设置")
        kline_form = QFormLayout(kline_group)
        kline_form.setSpacing(8)

        self.kline_interval = QComboBox()
        self.kline_interval.addItems(["15m", "1h", "4h", "12h", "1d", "1w"])
        self.kline_interval.setToolTip(
            "K线周期：\n"
            "15m=15分钟 | 1h=1小时 | 4h=4小时 | 12h=12小时\n"
            "1d=日线 | 1w=周线\n"
            "注意：CoinGecko仅支持日线(1d)"
        )
        kline_form.addRow("K线周期:", self.kline_interval)

        self.kline_limit = QSpinBox()
        self.kline_limit.setRange(10, 120)
        self.kline_limit.setToolTip("获取最近多少根K线（建议20-60）")
        kline_form.addRow("K线数量:", self.kline_limit)

        self.top_bottom_n = QSpinBox()
        self.top_bottom_n.setRange(2, 15)
        self.top_bottom_n.setToolTip("计算支撑/阻力时取最高/最低的N根K线")
        kline_form.addRow("极值采样数:", self.top_bottom_n)

        detect_layout.addWidget(kline_group)

        # Box detection settings
        box_group = QGroupBox("箱体检测参数")
        box_form = QFormLayout(box_group)
        box_form.setSpacing(8)

        self.min_range_pct = QDoubleSpinBox()
        self.min_range_pct.setRange(0.5, 10.0)
        self.min_range_pct.setSingleStep(0.5)
        self.min_range_pct.setSuffix(" %")
        self.min_range_pct.setToolTip("箱体最小振幅（低于此值视为稳定币行为）")
        box_form.addRow("最小振幅:", self.min_range_pct)

        self.max_range_pct = QDoubleSpinBox()
        self.max_range_pct.setRange(10.0, 50.0)
        self.max_range_pct.setSingleStep(1.0)
        self.max_range_pct.setSuffix(" %")
        self.max_range_pct.setToolTip("箱体最大振幅（高于此值视为趋势行情）")
        box_form.addRow("最大振幅:", self.max_range_pct)

        self.touch_threshold_pct = QDoubleSpinBox()
        self.touch_threshold_pct.setRange(0.5, 10.0)
        self.touch_threshold_pct.setSingleStep(0.5)
        self.touch_threshold_pct.setSuffix(" %")
        self.touch_threshold_pct.setToolTip("触及边界判定阈值（容差百分比）")
        box_form.addRow("触及容差:", self.touch_threshold_pct)

        self.min_touches = QSpinBox()
        self.min_touches.setRange(1, 10)
        self.min_touches.setToolTip("支撑位和阻力位各自至少被触及的次数")
        box_form.addRow("最小触及次数:", self.min_touches)

        self.min_containment = QDoubleSpinBox()
        self.min_containment.setRange(0.3, 0.95)
        self.min_containment.setSingleStep(0.05)
        self.min_containment.setToolTip("收盘价在箱体内的最低比例")
        box_form.addRow("最小包含率:", self.min_containment)

        self.max_normalized_slope = QDoubleSpinBox()
        self.max_normalized_slope.setRange(0.05, 0.5)
        self.max_normalized_slope.setSingleStep(0.01)
        self.max_normalized_slope.setDecimals(2)
        self.max_normalized_slope.setToolTip("最大归一化斜率（越小越平坦）")
        box_form.addRow("最大斜率:", self.max_normalized_slope)

        detect_layout.addWidget(box_group)
        detect_layout.addStretch()
        tabs.addTab(detect_tab, "检测参数")

        # ── Tab 2: Filter & Network ──
        filter_tab = QWidget()
        filter_layout = QVBoxLayout(filter_tab)

        # Volume filter
        vol_group = QGroupBox("成交量过滤")
        vol_form = QFormLayout(vol_group)
        vol_form.setSpacing(8)

        self.min_volume_usdt = QDoubleSpinBox()
        self.min_volume_usdt.setRange(10000, 100_000_000)
        self.min_volume_usdt.setSingleStep(100000)
        self.min_volume_usdt.setDecimals(0)
        self.min_volume_usdt.setSuffix(" USDT")
        self.min_volume_usdt.setToolTip("最小24h成交量（USDT计价）")
        vol_form.addRow("最小24h成交量:", self.min_volume_usdt)

        filter_layout.addWidget(vol_group)

        # Network settings
        net_group = QGroupBox("网络设置")
        net_form = QFormLayout(net_group)
        net_form.setSpacing(8)

        self.request_delay = QDoubleSpinBox()
        self.request_delay.setRange(0.1, 5.0)
        self.request_delay.setSingleStep(0.1)
        self.request_delay.setDecimals(1)
        self.request_delay.setSuffix(" 秒")
        self.request_delay.setToolTip("每次API请求间隔（控制频率，避免被限流）")
        net_form.addRow("请求间隔:", self.request_delay)

        self.proxy = QLineEdit()
        self.proxy.setPlaceholderText("例如: http://127.0.0.1:7890")
        self.proxy.setToolTip(
            "HTTP/HTTPS 代理地址。留空则不使用代理。\n"
            "Clash 默认: http://127.0.0.1:7890\n"
            "V2Ray 默认: http://127.0.0.1:10809"
        )
        net_form.addRow("代理地址:", self.proxy)

        filter_layout.addWidget(net_group)
        filter_layout.addStretch()
        tabs.addTab(filter_tab, "网络与过滤")

        # ── Tab 3: Advanced Analysis ──
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        # Sentiment & Rate settings
        external_group = QGroupBox("外部数据集成")
        external_form = QFormLayout(external_group)
        external_form.setSpacing(8)

        self.enable_fgi = QComboBox()
        self.enable_fgi.addItems(["启用", "禁用"])
        self.enable_fgi.setToolTip(
            "恐惧贪婪指数 (Fear & Greed Index)\n"
            "极端恐惧时提升买入信号置信度\n"
            "极端贪婪时降低追高信号置信度"
        )
        external_form.addRow("恐惧贪婪指数:", self.enable_fgi)

        self.enable_funding_rate = QComboBox()
        self.enable_funding_rate.addItems(["启用", "禁用"])
        self.enable_funding_rate.setToolTip(
            "永续合约资金费率扫描\n"
            "极高正费率=多头拥挤→回调风险\n"
            "极高负费率=空头拥挤→轧空风险"
        )
        external_form.addRow("资金费率扫描:", self.enable_funding_rate)

        advanced_layout.addWidget(external_group)

        # Indicator thresholds
        indicator_group = QGroupBox("技术指标阈值")
        indicator_form = QFormLayout(indicator_group)
        indicator_form.setSpacing(8)

        self.adx_threshold = QDoubleSpinBox()
        self.adx_threshold.setRange(10.0, 50.0)
        self.adx_threshold.setSingleStep(5.0)
        self.adx_threshold.setToolTip(
            "ADX趋势强度阈值：\n"
            "低于此值=横盘（箱体策略适用）\n"
            "高于此值=趋势（降低箱体置信度）"
        )
        indicator_form.addRow("ADX趋势阈值:", self.adx_threshold)

        self.vol_breakout_mult = QDoubleSpinBox()
        self.vol_breakout_mult.setRange(1.2, 5.0)
        self.vol_breakout_mult.setSingleStep(0.1)
        self.vol_breakout_mult.setSuffix(" x")
        self.vol_breakout_mult.setToolTip(
            "成交量突破确认倍数：\n"
            "最近成交量÷平均成交量≥此值时触发突破预警"
        )
        indicator_form.addRow("成交量突破倍率:", self.vol_breakout_mult)

        self.atr_stop_mult = QDoubleSpinBox()
        self.atr_stop_mult.setRange(1.0, 5.0)
        self.atr_stop_mult.setSingleStep(0.5)
        self.atr_stop_mult.setSuffix(" x ATR")
        self.atr_stop_mult.setToolTip(
            "ATR止损倍数：\n"
            "止损=支撑位 - N×ATR（做多）\n"
            "止损=阻力位 + N×ATR（做空）"
        )
        indicator_form.addRow("ATR止损倍数:", self.atr_stop_mult)

        advanced_layout.addWidget(indicator_group)
        advanced_layout.addStretch()
        tabs.addTab(advanced_tab, "高级分析")

        layout.addWidget(tabs)

        # ── Dialog buttons ──
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self._restore_defaults)

        # Style the restore button
        restore_btn = button_box.button(QDialogButtonBox.RestoreDefaults)
        restore_btn.setText("恢复默认")

        layout.addWidget(button_box)

    def _load_params(self):
        """Load current parameters into UI widgets."""
        p = self._params

        idx = self.kline_interval.findText(p.get("kline_interval", "1d"))
        if idx >= 0:
            self.kline_interval.setCurrentIndex(idx)

        self.kline_limit.setValue(p.get("kline_limit", 30))
        self.top_bottom_n.setValue(p.get("top_bottom_n", 5))
        self.min_range_pct.setValue(p.get("min_range_pct", 3.0))
        self.max_range_pct.setValue(p.get("max_range_pct", 25.0))
        self.touch_threshold_pct.setValue(p.get("touch_threshold_pct", 2.0))
        self.min_touches.setValue(p.get("min_touches", 2))
        self.min_containment.setValue(p.get("min_containment", 0.70))
        self.max_normalized_slope.setValue(p.get("max_normalized_slope", 0.15))
        self.min_volume_usdt.setValue(p.get("min_volume_usdt", 1_000_000))
        self.request_delay.setValue(p.get("request_delay", 0.5))
        self.proxy.setText(p.get("proxy", ""))

        # Advanced params
        fgi_enabled = "启用" if p.get("enable_fgi", True) else "禁用"
        self.enable_fgi.setCurrentText(fgi_enabled)
        fr_enabled = "启用" if p.get("enable_funding_rate", True) else "禁用"
        self.enable_funding_rate.setCurrentText(fr_enabled)
        self.adx_threshold.setValue(p.get("adx_threshold", 25.0))
        self.vol_breakout_mult.setValue(p.get("vol_breakout_mult", 1.5))
        self.atr_stop_mult.setValue(p.get("atr_stop_mult", 1.5))

    def _on_accept(self):
        """Validate and accept the settings."""
        if self.min_range_pct.value() >= self.max_range_pct.value():
            QMessageBox.warning(
                self, "参数错误",
                "最小振幅必须小于最大振幅，请重新设置。"
            )
            return
        self._save_params()
        self.accept()

    def _save_params(self):
        """Save current UI values to params dict."""
        self._params["kline_interval"] = self.kline_interval.currentText()
        self._params["kline_limit"] = self.kline_limit.value()
        self._params["top_bottom_n"] = self.top_bottom_n.value()
        self._params["touch_threshold_pct"] = self.touch_threshold_pct.value()
        self._params["min_touches"] = self.min_touches.value()
        self._params["min_containment"] = self.min_containment.value()
        self._params["max_normalized_slope"] = self.max_normalized_slope.value()
        self._params["min_range_pct"] = self.min_range_pct.value()
        self._params["max_range_pct"] = self.max_range_pct.value()
        self._params["min_volume_usdt"] = int(self.min_volume_usdt.value())
        self._params["request_delay"] = self.request_delay.value()
        self._params["proxy"] = self.proxy.text().strip()
        # Advanced params
        self._params["enable_fgi"] = self.enable_fgi.currentText() == "启用"
        self._params["enable_funding_rate"] = self.enable_funding_rate.currentText() == "启用"
        self._params["adx_threshold"] = self.adx_threshold.value()
        self._params["vol_breakout_mult"] = self.vol_breakout_mult.value()
        self._params["atr_stop_mult"] = self.atr_stop_mult.value()

    def _restore_defaults(self):
        """Restore all parameters to defaults."""
        reply = QMessageBox.question(
            self, "恢复默认设置",
            "确定要将所有参数恢复为默认值吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._params = DEFAULT_PARAMS.copy()
            self._load_params()

    def get_params(self) -> Dict:
        """Return the current parameter settings."""
        return self._params.copy()
