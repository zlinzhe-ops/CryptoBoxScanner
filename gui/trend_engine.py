"""
Uptrend detection engine — identifies coins in rising trends and generates
buy/hold/sell signals based on technical indicators.
"""

from typing import List, Dict, Optional, Tuple
from gui.analysis_engine import calc_ma, calc_rsi, calc_macd
import crypto_box_scanner as _scanner

# ── Uptrend Detection ───────────────────────────────────────

def detect_uptrend(candles: List[Dict], volumes: Optional[List[float]] = None) -> Optional[Dict]:
    """
    Detect if a trading pair is in a healthy uptrend.
    Returns a dict with symbol, score, and trend metrics, or None if no clear trend.
    """
    n = len(candles)
    if n < 20:
        return None

    closes = [c["close"] for c in candles]
    highs  = [c["high"]  for c in candles]
    lows   = [c["low"]   for c in candles]
    vols   = volumes or [c.get("volume", 0) for c in candles]

    current = closes[-1]
    if current <= 0:
        return None

    # ── Indicators ──
    ma5   = calc_ma(closes, 5)
    ma10  = calc_ma(closes, 10)
    ma20  = calc_ma(closes, 20)
    rsi_vals = calc_rsi(closes, 14)
    latest_rsi = rsi_vals[-1] if rsi_vals else 50
    macd_line, signal_line, histogram = calc_macd(closes)

    score = 0
    reasons = []

    # 1. Price above key MAs (25 points)
    above_ma20 = current > ma20[-1]
    above_ma5  = current > ma5[-1]
    if above_ma20:
        score += 15
        reasons.append("[+] 价格在 MA20 上方，中期多头")
    if above_ma5:
        score += 10
        reasons.append("[+] 价格在 MA5 上方，短期偏强")

    # 2. MA alignment: short > medium > long (20 points)
    ma5_above_ma20 = ma5[-1] > ma20[-1]
    if ma5_above_ma20:
        score += 12
        reasons.append("[+] MA5 > MA20，均线多头排列")
    if len(closes) >= 10 and ma10[-1] > ma20[-1]:
        score += 8
        reasons.append("[+] MA10 > MA20，中期趋势向上")

    # 3. Higher highs & higher lows (20 points)
    hh_score = 0
    for i in range(1, min(5, len(highs))):
        if highs[-i] >= highs[-i-1]:
            hh_score += 1
    if hh_score >= 4:
        score += 12
        reasons.append(f"[+] 近5日 {hh_score}/4 日创更高高点")
    elif hh_score >= 2:
        score += 6

    hl_score = 0
    for i in range(1, min(5, len(lows))):
        if lows[-i] >= lows[-i-1] - (lows[-i] * 0.005):  # 0.5% tolerance
            hl_score += 1
    if hl_score >= 4:
        score += 8
        reasons.append(f"[+] 低点持续抬高")

    # 4. RSI: healthy range (15 points)
    if 55 <= latest_rsi <= 70:
        score += 12
        reasons.append(f"[+] RSI={latest_rsi:.0f}，强势区间")
    elif 40 <= latest_rsi < 55:
        score += 8
        reasons.append(f"[*] RSI={latest_rsi:.0f}，中性偏强")
    elif 30 <= latest_rsi < 40:
        score += 4
        reasons.append(f"[*] RSI={latest_rsi:.0f}，低位但可能反弹")
    elif latest_rsi > 70:
        score += 3
        reasons.append(f"[!] RSI={latest_rsi:.0f}，超买需谨慎")

    # 5. MACD bullish (10 points)
    if len(histogram) >= 2:
        if histogram[-1] > 0 and histogram[-1] > histogram[-2]:
            score += 8
            reasons.append("[+] MACD 柱为正且扩大，动能增强")
        elif histogram[-1] > 0:
            score += 5
            reasons.append("[+] MACD 柱为正")
        elif histogram[-1] > histogram[-2]:
            score += 3
            reasons.append("[*] MACD 柱收窄，可能反转")

    # 6. Recent performance (10 points)
    if len(closes) >= 10:
        recent_avg = sum(closes[-5:]) / 5
        prev_avg = sum(closes[-10:-5]) / 5
        if prev_avg > 0:
            gain_pct = (recent_avg - prev_avg) / prev_avg * 100
            if gain_pct > 10:
                score += 8
                reasons.append(f"[+] 近5日均价涨 {gain_pct:.1f}%，强势拉升")
            elif gain_pct > 5:
                score += 6
                reasons.append(f"[+] 近5日均价涨 {gain_pct:.1f}%")
            elif gain_pct > 2:
                score += 3
                reasons.append(f"[*] 近5日均价涨 {gain_pct:.1f}%，缓慢爬升")

    # ── Determine trend grade ──
    if score >= 65:
        trend = "STRONG_UPTREND"
    elif score >= 45:
        trend = "UPTREND"
    elif score >= 25:
        trend = "WEAK_UPTREND"
    else:
        return None  # No clear uptrend, don't include in results

    # ── Suggested entry & targets ──
    recent_low = min(lows[-5:])
    recent_high = max(highs[-5:])

    if trend == "STRONG_UPTREND":
        suggestion = "逢低买入"
        entry = current * 0.995
        stop_loss = recent_low * 0.98
        target = current * 1.08
    elif trend == "UPTREND":
        suggestion = "回调买入"
        entry = ma20[-1] * 1.005
        stop_loss = ma20[-1] * 0.97
        target = recent_high * 1.03
    else:
        suggestion = "观望等待确认"
        entry = ma20[-1]
        stop_loss = ma20[-1] * 0.96
        target = recent_high

    # ── ATR & ADX (same as box mode) ──
    atr_value = _scanner.calc_atr(candles, 14)
    atr_pct = (atr_value / current * 100) if current > 0 else 0
    adx = _scanner.calc_adx(candles, 14)
    vwap = _scanner.calc_vwap(candles)
    # ATR-based dynamic stops
    long_stop = recent_low - 1.5 * atr_value
    long_tp = current * 1.08  # 8% target for uptrend

    return {
        "symbol": "",
        "score": score,
        "trend": trend,
        "current_price": round(current, 8),
        "rsi": round(latest_rsi, 1),
        "ma20": round(ma20[-1], 8),
        "ma5": round(ma5[-1], 8),
        "gain_5d_pct": round(gain_pct, 2) if 'gain_pct' in dir() else 0,
        "recent_high": round(recent_high, 8),
        "recent_low": round(recent_low, 8),
        "suggestion": suggestion,
        "entry": round(entry, 8),
        "stop_loss": round(stop_loss, 8),
        "target": round(target, 8),
        "reasons": reasons,
        # ATR/ADX/VWAP fields (same as box mode)
        "atr_value": round(atr_value, 8),
        "atr_pct": round(atr_pct, 2),
        "adx": round(adx, 1),
        "trend_strength": _scanner._adx_label(adx),
        "vwap": round(vwap, 8),
        "confidence": score,  # alias for post-scan enhancement compatibility
        "long_stop_loss": round(max(long_stop, recent_low * 0.92), 8),
        "long_take_profit": round(long_tp, 8),
    }


TREND_LABELS = {
    "STRONG_UPTREND": "强势上涨",
    "UPTREND": "上涨趋势",
    "WEAK_UPTREND": "弱势上涨",
}

TREND_COLORS = {
    "STRONG_UPTREND": "#00FF88",
    "UPTREND": "#88FFBB",
    "WEAK_UPTREND": "#FFD700",
}
