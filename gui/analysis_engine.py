"""
Technical analysis engine for cryptocurrency trading signals.
Computes indicators, backtests box patterns, and generates long/short recommendations.
"""

import math
from typing import List, Dict, Optional, Tuple
from collections import deque


# ── Technical Indicators ─────────────────────────────────────

def calc_rsi(closes: List[float], period: int = 14) -> List[float]:
    """Calculate Relative Strength Index for a price series."""
    if len(closes) < period + 1:
        return [50.0] * len(closes)

    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(diff if diff > 0 else 0)
        losses.append(abs(diff) if diff < 0 else 0)

    rsi = [50.0] * period  # First 'period' values are neutral
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100.0 - (100.0 / (1.0 + rs)))

    return rsi


def calc_macd(closes: List[float]) -> Tuple[List[float], List[float], List[float]]:
    """Calculate MACD (12, 26, 9). Returns (macd_line, signal_line, histogram)."""
    if len(closes) < 26:
        zeros = [0.0] * len(closes)
        return zeros, zeros, zeros

    def ema(data: List[float], period: int) -> List[float]:
        k = 2.0 / (period + 1)
        result = [data[0]]
        for i in range(1, len(data)):
            result.append(data[i] * k + result[-1] * (1 - k))
        return result

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(closes))]
    signal_line = ema(macd_line, 9)
    histogram = [macd_line[i] - signal_line[i] for i in range(len(closes))]

    return macd_line, signal_line, histogram


def calc_ma(closes: List[float], period: int) -> List[float]:
    """Calculate Simple Moving Average."""
    if len(closes) < period:
        return [closes[0]] * len(closes)
    ma = [closes[0]] * (period - 1)
    window = deque(closes[:period], maxlen=period)
    for i in range(period - 1, len(closes)):
        window.append(closes[i])
        ma.append(sum(window) / period)
    return ma


def calc_volume_profile(volumes: List[float], closes: List[float], levels: int = 10) -> Dict:
    """Calculate volume profile across price levels."""
    if not closes or not volumes:
        return {"levels": [], "volume_at_level": []}

    price_min = min(closes)
    price_max = max(closes)
    if price_max == price_min:
        price_max = price_min * 1.01

    step = (price_max - price_min) / levels
    level_volumes = [0.0] * levels
    level_prices = [price_min + i * step for i in range(levels)]

    for i, price in enumerate(closes):
        idx = min(int((price - price_min) / step), levels - 1)
        if idx >= 0:
            level_volumes[idx] += volumes[i] if i < len(volumes) else 0

    return {
        "levels": level_prices,
        "volume_at_level": level_volumes,
    }


# ── Box Range Analysis ───────────────────────────────────────

def analyze_box_quality(result: Dict) -> Dict:
    """Analyze the quality of a detected box range pattern."""
    conf = result.get("confidence", 0)
    range_pct = result.get("range_pct", 0)
    position = result.get("position_pct", 50)
    touches_r = result.get("resistance_touches", 0)
    touches_s = result.get("support_touches", 0)
    containment = result.get("containment_ratio", 0)

    # Support strength (0-100)
    support_strength = min(touches_s * 20, 60) + min(containment * 40, 40)

    # Resistance strength (0-100)
    resistance_strength = min(touches_r * 20, 60) + min(containment * 40, 40)

    # Breakout probability
    # Narrow boxes (< 10%) more likely to break out
    if range_pct <= 5:
        breakout_prob = 75
    elif range_pct <= 10:
        breakout_prob = 60
    elif range_pct <= 15:
        breakout_prob = 45
    else:
        breakout_prob = 30

    # Direction bias: if near support, more likely to bounce up
    if position <= 25:
        direction_bias = "up"
    elif position >= 75:
        direction_bias = "down"
    else:
        direction_bias = "neutral"

    return {
        "support_strength": round(support_strength, 1),
        "resistance_strength": round(resistance_strength, 1),
        "breakout_probability": breakout_prob,
        "direction_bias": direction_bias,
        "quality_grade": _grade_confidence(conf),
    }


# ── Trading Signal Generator ─────────────────────────────────

def generate_trading_signal(
    result: Dict,
    candles: List[Dict],
    volumes: Optional[List[float]] = None,
    funding_risk: Optional[Dict] = None,
) -> Dict:
    """
    Generate a comprehensive trading signal based on box range analysis,
    technical indicators, volume analysis, ATR, ADX, and funding rate.

    Returns a dict with:
        signal: "STRONG_LONG" | "LONG" | "NEUTRAL" | "SHORT" | "STRONG_SHORT"
        score_long: 0-100
        score_short: 0-100
        reasons: list of reasoning strings
        risk_level: "LOW" | "MEDIUM" | "HIGH"
        suggested_entry: price
        suggested_stop_loss: price
        suggested_take_profit: price
    """
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    vols = volumes or [c.get("volume", 0) for c in candles]

    support = result["support"]
    resistance = result["resistance"]
    current = result["current_price"]
    position = result.get("position_pct", 50)
    conf = result.get("confidence", 0)

    # 新增字段
    atr_value = result.get("atr_value", 0)
    adx = result.get("adx", 0)
    vol_breakout = result.get("volume_breakout", {})

    box_analysis = analyze_box_quality(result)

    # Calculate indicators
    rsi_values = calc_rsi(closes, 14)
    latest_rsi = rsi_values[-1] if rsi_values else 50
    ma5 = calc_ma(closes, 5)
    ma20 = calc_ma(closes, 20)
    latest_ma5 = ma5[-1] if ma5 else current
    latest_ma20 = ma20[-1] if ma20 else current
    macd_line, signal_line, histogram = calc_macd(closes)
    latest_hist = histogram[-1] if histogram else 0

    # Volume analysis
    recent_vol = vols[-5:] if len(vols) >= 5 else vols
    avg_vol = sum(recent_vol) / len(recent_vol) if recent_vol else 1
    prev_vol = vols[-10:-5] if len(vols) >= 10 else vols[:-5] if len(vols) > 5 else vols
    prev_avg_vol = sum(prev_vol) / len(prev_vol) if prev_vol else avg_vol
    vol_change = ((avg_vol - prev_avg_vol) / prev_avg_vol * 100) if prev_avg_vol > 0 else 0

    reasons = []
    score_long = 0
    score_short = 0

    # ── 1. Position in box (0-30 points) ──
    if position <= 20:
        score_long += 30
        reasons.append(f"[+] 价格接近支撑位 (位置 {position:.0f}%)，买入优势")
    elif position <= 35:
        score_long += 20
        reasons.append(f"[+] 价格偏近支撑位 (位置 {position:.0f}%)，偏多")
    elif position >= 80:
        score_short += 30
        reasons.append(f"[-] 价格接近阻力位 (位置 {position:.0f}%)，卖出优势")
    elif position >= 65:
        score_short += 20
        reasons.append(f"[-] 价格偏近阻力位 (位置 {position:.0f}%)，偏空")

    # ── 2. RSI (0-20 points) ──
    if latest_rsi < 30:
        score_long += 20
        reasons.append(f"[+] RSI={latest_rsi:.0f} 超卖区域，反弹概率高")
    elif latest_rsi < 40:
        score_long += 10
        reasons.append(f"[+] RSI={latest_rsi:.0f} 偏低，有反弹空间")
    elif latest_rsi > 70:
        score_short += 20
        reasons.append(f"[-] RSI={latest_rsi:.0f} 超买区域，回调概率高")
    elif latest_rsi > 60:
        score_short += 10
        reasons.append(f"[-] RSI={latest_rsi:.0f} 偏高，有回调压力")

    # ── 3. Moving averages (0-15 points) ──
    if current > latest_ma20:
        score_long += 10
        if current > latest_ma5:
            score_long += 5
            reasons.append("[+] 价格在 MA5/MA20 上方，短期偏多")
        else:
            reasons.append("[+] 价格在 MA20 上方，中期偏多")
    elif current < latest_ma20:
        score_short += 10
        if current < latest_ma5:
            score_short += 5
            reasons.append("[-] 价格在 MA5/MA20 下方，短期偏空")
        else:
            reasons.append("[-] 价格在 MA20 下方，中期偏空")

    # ── 4. MACD (0-15 points) ──
    if latest_hist > 0:
        score_long += 10
        if len(histogram) >= 2 and histogram[-2] < 0:
            score_long += 5
            reasons.append("[+] MACD 金叉，看涨信号")
        else:
            reasons.append("[+] MACD 柱为正，动能向上")
    elif latest_hist < 0:
        score_short += 10
        if len(histogram) >= 2 and histogram[-2] > 0:
            score_short += 5
            reasons.append("[-] MACD 死叉，看跌信号")
        else:
            reasons.append("[-] MACD 柱为负，动能向下")

    # ── 5. Volume analysis (0-10 points) ──
    if vol_change > 20:
        if position <= 40:
            score_long += 10
            reasons.append(f"[+] 放量+{vol_change:.0f}%，支撑位放量是买入信号")
        elif position >= 60:
            score_short += 10
            reasons.append(f"[-] 放量+{vol_change:.0f}%，阻力位放量是卖出信号")
    elif vol_change < -20:
        reasons.append(f"[*] 缩量{vol_change:.0f}%，等待方向选择")

    # ── 5b. Volume Breakout Check (0-10 points) ──
    if vol_breakout.get("breakout_warning"):
        vb_dir = vol_breakout.get("direction", "none")
        vb_ratio = vol_breakout.get("vol_ratio", 1.0)
        if vb_dir == "up":
            score_short += 10
            reasons.append(f"[!] 成交量放量 {vb_ratio:.1f}x + 接近阻力位 → 警惕向上突破")
        elif vb_dir == "down":
            score_long += 10
            reasons.append(f"[!] 成交量放量 {vb_ratio:.1f}x + 接近支撑位 → 警惕向下突破")
    elif vol_breakout.get("volume_surge"):
        reasons.append(f"[*] 成交量放量 {vol_breakout.get('vol_ratio', 1.0):.1f}x，关注方向选择")

    # ── 6. Box quality (0-10 points) ──
    if conf >= 80:
        bonus = 10
        reasons.append("[*] 高质量箱体 (置信度 >= 80)")
    elif conf >= 65:
        bonus = 5
        reasons.append("[*] 较优箱体 (置信度 >= 65)")
    else:
        bonus = 0
    # Add bonus to whichever side has more points
    if score_long > score_short:
        score_long += bonus
    elif score_short > score_long:
        score_short += bonus

    # ── 7. ADX Trend Strength (0-10 points adjustment) ──
    if adx > 0:
        if adx < 20:
            reasons.append(f"[+] ADX={adx:.1f} 横盘确认，箱体策略适用")
        elif adx < 25:
            reasons.append(f"[*] ADX={adx:.1f} 趋势形成中，注意箱体可能突破")
        elif adx < 35:
            reasons.append(f"[!] ADX={adx:.1f} 温和趋势，箱体信号可靠度降低")
        else:
            reasons.append(f"[!] ADX={adx:.1f} 强趋势，不建议箱体策略")

    # ── 8. Funding Rate Risk Warning ──
    if funding_risk and funding_risk.get("risk_level") in ("high", "extreme"):
        fr_warning = funding_risk.get("warning", "")
        if fr_warning:
            reasons.append(f"[!] 资金费率: {fr_warning}")
        if funding_risk.get("crowd_side") == "long" and score_short > 0:
            score_short += 5  # 多头拥挤 + 做空信号增强
        elif funding_risk.get("crowd_side") == "short" and score_long > 0:
            score_long += 5  # 空头拥挤 + 做多信号增强

    # ── Determine final signal ──
    diff = score_long - score_short

    if score_long >= 70:
        signal = "STRONG_LONG"
    elif score_long >= 50:
        signal = "LONG"
    elif score_short >= 70:
        signal = "STRONG_SHORT"
    elif score_short >= 50:
        signal = "SHORT"
    else:
        signal = "NEUTRAL"

    # ── Risk level (incorporate ADX and funding risk) ──
    risk_deductions = 0
    if adx > 30:
        risk_deductions += 15  # Higher trend = higher risk for range trading
    if funding_risk and funding_risk.get("risk_level") == "extreme":
        risk_deductions += 10

    effective_conf = max(conf - risk_deductions, 30)
    if effective_conf >= 80:
        risk = "LOW"
    elif effective_conf >= 60:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    # ── Suggested prices (ATR-based dynamic stops) ──
    # 优先使用 detect_box_range 中计算的ATR止损止盈
    result_long_stop = result.get("long_stop_loss")
    result_short_stop = result.get("short_stop_loss")
    result_long_tp = result.get("long_take_profit")
    result_short_tp = result.get("short_take_profit")
    result_entry = result.get("suggested_entry")

    if signal in ("STRONG_LONG", "LONG"):
        suggested_entry = result_entry if result_entry else support * 1.005
        suggested_stop_loss = result_long_stop if result_long_stop else support * 0.98
        suggested_take_profit = result_long_tp if result_long_tp else resistance * 0.99
    elif signal in ("STRONG_SHORT", "SHORT"):
        suggested_entry = result_entry if result_entry else resistance * 0.995
        suggested_stop_loss = result_short_stop if result_short_stop else resistance * 1.02
        suggested_take_profit = result_short_tp if result_short_tp else support * 1.01
    else:
        suggested_entry = current
        suggested_stop_loss = result_long_stop or support * 0.97
        suggested_take_profit = result_long_tp or resistance * 0.99

    # ── Risk/Reward ──
    if signal in ("STRONG_LONG", "LONG"):
        risk_amount = suggested_entry - suggested_stop_loss
        reward_amount = suggested_take_profit - suggested_entry
    else:
        risk_amount = suggested_stop_loss - suggested_entry
        reward_amount = suggested_entry - suggested_take_profit

    rr_ratio = reward_amount / max(risk_amount, 0.0001)

    return {
        "signal": signal,
        "score_long": score_long,
        "score_short": score_short,
        "reasons": reasons,
        "risk_level": risk,
        "suggested_entry": round(suggested_entry, 8),
        "suggested_stop_loss": round(suggested_stop_loss, 8),
        "suggested_take_profit": round(suggested_take_profit, 8),
        "risk_reward_ratio": round(rr_ratio, 2),
        "rsi": round(latest_rsi, 1),
        "volume_change_pct": round(vol_change, 1),
        "ma5": round(latest_ma5, 8),
        "ma20": round(latest_ma20, 8),
        "atr": round(atr_value, 8),
        "adx": round(adx, 1),
        "box_analysis": box_analysis,
    }


# ── Helpers ──────────────────────────────────────────────────

def _grade_confidence(conf: int) -> str:
    if conf >= 80:
        return "优秀 ★"
    elif conf >= 65:
        return "良好 ☆"
    elif conf >= 50:
        return "一般"
    else:
        return "较弱"


SIGNAL_LABELS = {
    "STRONG_LONG": "强烈做多",
    "LONG": "偏多",
    "NEUTRAL": "观望",
    "SHORT": "偏空",
    "STRONG_SHORT": "强烈做空",
}

SIGNAL_COLORS = {
    "STRONG_LONG": "#00FF88",
    "LONG": "#88FFBB",
    "NEUTRAL": "#94A3B8",
    "SHORT": "#FF8888",
    "STRONG_SHORT": "#EF4444",
}
