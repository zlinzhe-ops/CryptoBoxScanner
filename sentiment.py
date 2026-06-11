"""
恐惧贪婪指数 (Fear & Greed Index) 模块
======================================
从 alternative.me API 获取加密货币市场情绪指数，
用于调整箱体震荡检测的置信度评分。

极端恐惧时提升买入信号的可靠性，
极端贪婪时降低追高信号的可靠性。

数据源: https://alternative.me/crypto/fear-and-greed-index/
API: https://api.alternative.me/fng/
"""

from typing import Optional, Dict
import requests
import time


# 缓存，避免频繁请求
_cache: Optional[Dict] = None
_cache_time: float = 0
CACHE_TTL = 600  # 10分钟缓存


def fetch_fear_greed_index(limit: int = 1) -> Optional[Dict]:
    """获取最新的恐惧贪婪指数。

    参数:
        limit: 获取最近多少天的数据（默认1=仅最新）

    返回:
        {
            "value": 45,              # 0-100，数值越高越贪婪
            "value_classification": "Fear",
            "timestamp": "1734567890",
            "time_until_update": "3600",
        }
        或 None (网络错误时)
    """
    global _cache, _cache_time

    now = time.time()
    if _cache is not None and (now - _cache_time) < CACHE_TTL:
        return _cache

    try:
        url = f"https://api.alternative.me/fng/?limit={limit}"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data and len(data["data"]) > 0:
                _cache = data["data"][0]
                _cache_time = now
                return _cache
    except Exception:
        pass

    return _cache  # 返回旧缓存（如有）


def get_sentiment_classification(fgi_value: int) -> str:
    """根据恐惧贪婪指数值返回情绪分类"""
    if fgi_value <= 20:
        return "极度恐惧"
    elif fgi_value <= 40:
        return "恐惧"
    elif fgi_value <= 60:
        return "中性"
    elif fgi_value <= 80:
        return "贪婪"
    else:
        return "极度贪婪"


def get_sentiment_adjustment(fgi_value: int) -> Dict:
    """根据恐惧贪婪指数计算置信度调整因子和交易建议。

    逆向投资策略:
    - 极度恐惧(0-20): 历史低点，买入窗口 → 做多置信度×1.15
    - 恐惧(20-40): 偏低估 → 做多置信度×1.05
    - 中性(40-60): 无调整
    - 贪婪(60-80): 偏乐观 → 做多置信度×0.90
    - 极度贪婪(80-100): 可能见顶 → 做多置信度×0.80

    返回:
        {
            "fgi_value": int,
            "classification": str,
            "confidence_multiplier": float,   # 置信度乘数
            "bias": str,                      # "bullish" / "neutral" / "bearish"
            "suggestion": str,                # 交易建议文本
        }
    """
    classification = get_sentiment_classification(fgi_value)

    if fgi_value <= 20:
        confidence_mult = 1.15
        bias = "bullish"
        suggestion = "极度恐惧 → 市场恐慌，历史性买入窗口（逆向投资）"
    elif fgi_value <= 40:
        confidence_mult = 1.05
        bias = "bullish"
        suggestion = "恐惧 → 市场偏悲观，逢低关注买入机会"
    elif fgi_value <= 60:
        confidence_mult = 1.00
        bias = "neutral"
        suggestion = "中性 → 市场情绪正常，按技术信号操作"
    elif fgi_value <= 80:
        confidence_mult = 0.90
        bias = "bearish"
        suggestion = "贪婪 → 市场偏乐观，注意控制仓位和止盈"
    else:
        confidence_mult = 0.80
        bias = "bearish"
        suggestion = "极度贪婪 → 警惕见顶风险，建议减仓或设止损保护"

    return {
        "fgi_value": fgi_value,
        "classification": classification,
        "confidence_multiplier": confidence_mult,
        "bias": bias,
        "suggestion": suggestion,
    }


def apply_sentiment_to_confidence(confidence: int, fgi_value: Optional[int] = None) -> Dict:
    """将市场情绪应用到置信度评分。

    参数:
        confidence: 原始置信度 (0-100)
        fgi_value: 恐惧贪婪指数值 (None则自动获取)

    返回:
        {
            "original_confidence": int,
            "adjusted_confidence": int,
            "sentiment": { ... },  # get_sentiment_adjustment 的返回值
        }
    """
    if fgi_value is None:
        fgi_data = fetch_fear_greed_index()
        if fgi_data is None:
            return {
                "original_confidence": confidence,
                "adjusted_confidence": confidence,
                "sentiment": None,
            }
        try:
            fgi_value = int(fgi_data["value"])
        except (KeyError, ValueError, TypeError):
            return {
                "original_confidence": confidence,
                "adjusted_confidence": confidence,
                "sentiment": None,
            }

    sentiment = get_sentiment_adjustment(fgi_value)
    adjusted = round(confidence * sentiment["confidence_multiplier"])
    adjusted = max(0, min(100, adjusted))

    return {
        "original_confidence": confidence,
        "adjusted_confidence": adjusted,
        "sentiment": sentiment,
    }
