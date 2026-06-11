"""
Matplotlib candlestick chart embedded in PySide6 via FigureCanvasQTAgg.
"""
from typing import List, Dict, Optional

import matplotlib
matplotlib.use("QtAgg")
# Use font that supports CJK characters
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BG = "#0A0A0F"
GRID = "#1A1A2A"
TEXT = "#94A3B8"
GREEN = "#00FF88"
RED = "#EF4444"
SUPPORT_C = "#00FF88"
RESIST_C = "#EF4444"
MA5_C = "#FFD700"
MA20_C = "#00D4FF"


class KLineChartWidget(FigureCanvasQTAgg):

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(10, 5), facecolor=BG, dpi=100)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setMinimumHeight(300)
        self.setSizePolicy(
            self.sizePolicy().horizontalPolicy(),
            self.sizePolicy().verticalPolicy().Expanding,
        )
        self._candles: List[Dict] = []
        self._symbol: str = ""
        self._main_ax = None
        self._vol_ax = None

    def plot_chart(
        self, candles, support, resistance, current_price,
        symbol="", ma5=None, ma20=None, rsi_values=None,
    ):
        self._candles = candles
        self._symbol = symbol

        if not candles or len(candles) < 2:
            self._draw_empty("等待数据...")
            return

        try:
            self._do_plot(candles, support, resistance, current_price, symbol, ma5, ma20)
        except Exception as e:
            self._draw_empty(f"Render error: {e}")

    # ── Internal ─────────────────────────────────────────────

    def _get_axes(self):
        """Reuse existing axes if possible, otherwise create new ones."""
        if self._main_ax is not None and self._main_ax in self.fig.axes:
            self._main_ax.clear()
            self._vol_ax.clear()
            return self._main_ax, self._vol_ax
        else:
            self.fig.clf()
            self._main_ax, self._vol_ax = self.fig.subplots(
                2, 1, sharex=True,
                gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05},
            )
            # Leave generous margins so title/labels are never clipped
            self.fig.subplots_adjust(left=0.12, right=0.93, top=0.88, bottom=0.12, hspace=0.08)
            return self._main_ax, self._vol_ax

    def _do_plot(self, candles, support, resistance, current_price, symbol, ma5, ma20):
        ax_main, ax_vol = self._get_axes()
        n = len(candles)

        opens  = np.array([c["open"]  for c in candles])
        highs  = np.array([c["high"]  for c in candles])
        lows   = np.array([c["low"]   for c in candles])
        closes = np.array([c["close"] for c in candles])
        vols   = np.array([c.get("volume", 0) for c in candles])

        p_min = min(lows.min(), support * 0.95)
        p_max = max(highs.max(), resistance * 1.05)
        p_rng = p_max - p_min or 1

        # ── Candlestick ──
        ax_main.set_facecolor(BG)
        ax_main.tick_params(colors=TEXT, labelsize=8)
        ax_main.yaxis.tick_right()
        ax_main.grid(True, alpha=0.15, color=GRID)
        ax_main.set_xlim(-0.6, n + 0.6)
        ax_main.set_ylim(p_min - p_rng * 0.02, p_max + p_rng * 0.02)
        ax_main.set_title(f"{symbol}", color=GREEN, fontsize=13, fontweight="bold", pad=6)

        bw = 0.6
        for i in range(n):
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            clr = GREEN if c >= o else RED
            ax_main.plot([i, i], [l, h], color=clr, linewidth=1, alpha=0.85)
            bot = min(o, c)
            ht = abs(c - o) or p_rng * 0.001
            ax_main.add_patch(mpatches.Rectangle(
                (i - bw/2, bot), bw, ht,
                facecolor=clr, edgecolor=clr, linewidth=0.5, alpha=0.9,
            ))

        ax_main.axhline(support, color=SUPPORT_C, lw=1.5, ls="--", alpha=0.8,
                        label=f"Support {self._fmt(support)}")
        ax_main.axhline(resistance, color=RESIST_C, lw=1.5, ls="--", alpha=0.8,
                        label=f"Resistance {self._fmt(resistance)}")
        ax_main.fill_between([0, n-1], support, resistance, alpha=0.05, color="#FFF")
        if ma5 and len(ma5) == n:
            ax_main.plot(range(n), ma5, color=MA5_C, lw=1, alpha=0.8, label="MA5")
        if ma20 and len(ma20) == n:
            ax_main.plot(range(n), ma20, color=MA20_C, lw=1, alpha=0.8, label="MA20")
        ax_main.axhline(current_price, color="#FFF", lw=0.8, ls=":", alpha=0.5)
        ax_main.annotate(
            self._fmt(current_price), xy=(n-1, current_price),
            xytext=(n+0.5, current_price), color="#FFF", fontsize=8,
            arrowprops=dict(arrowstyle="->", color="#FFF", lw=0.5), va="center",
        )
        ax_main.legend(loc="upper left", fontsize=7, framealpha=0.3,
                       facecolor=BG, edgecolor=GRID, labelcolor=TEXT)

        # ── Volume ──
        ax_vol.set_facecolor(BG)
        ax_vol.tick_params(colors=TEXT, labelsize=8)
        ax_vol.yaxis.tick_right()
        ax_vol.grid(True, alpha=0.1, color=GRID)
        ax_vol.set_ylabel("Volume", color=TEXT, fontsize=9)
        ax_vol.set_xlim(-0.6, n + 0.6)
        plt.setp(ax_main.get_xticklabels(), visible=False)

        for i in range(n):
            clr = GREEN if closes[i] >= opens[i] else RED
            ax_vol.bar(i, vols[i], width=bw, color=clr, alpha=0.4, edgecolor="none")

        avg = np.mean(vols) if len(vols) > 1 else 0
        if avg > 0:
            ax_vol.axhline(avg, color=TEXT, lw=0.5, ls=":", alpha=0.4)

        self.draw()

    def _draw_empty(self, msg="No chart data available"):
        self._main_ax = None
        self._vol_ax = None
        self.fig.clf()
        ax = self.fig.add_subplot(111)
        ax.set_facecolor(BG)
        ax.text(0.5, 0.5, msg, ha="center", va="center",
                color=TEXT, fontsize=14, transform=ax.transAxes)
        ax.set_xticks([])
        ax.set_yticks([])
        self.draw()

    @staticmethod
    def _fmt(p):
        if p >= 1000:   return f"{p:,.2f}"
        elif p >= 1:   return f"{p:.2f}"
        elif p >= 0.01: return f"{p:.4f}"
        elif p >= 0.0001: return f"{p:.6f}"
        else:           return f"{p:.8f}"
