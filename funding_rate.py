"""
资金费率 (Funding Rate) 扫描模块
================================
批量获取永续合约资金费率，用于识别市场做多/做空拥挤程度。

极高正费率 → 多头拥挤，做多成本高，潜在回调风险
极高负费率 → 空头拥挤，可能轧空反弹

数据源: Gate.io / Binance 公开API

用法:
    from funding_rate import fetch_funding_rates, check_funding_risk
"""

from typing import Optional, Dict, List
import time
import requests


# Gate.io 永续合约资金费率接口
GATEIO_FUNDING_URL = "https://api.gateio.ws/api/v4/futures/usdt/contracts"


def fetch_gateio_funding_rates(session: Optional[requests.Session] = None) -> Dict[str, float]:
    """从 Gate.io 获取全部 USDT 永续合约的当前资金费率。

    返回:
        {"BTC_USDT": 0.0001, "ETH_USDT": 0.0003, ...}
        正值 = 多头付费给空头
        负值 = 空头付费给多头
    """
    try:
        s = session or requests.Session()
        if not session:
            s.headers.update({
                "Accept": "application/json",
                "User-Agent": "CryptoBoxScanner/1.0",
            })
        resp = s.get(GATEIO_FUNDING_URL, timeout=15)
        if resp.status_code != 200:
            return {}

        rates = {}
        for contract in resp.json():
            name = contract.get("name", "")
            if not name.endswith("_USDT"):
                continue
            try:
                rate = float(contract.get("funding_rate", 0))
                rates[name] = rate
            except (ValueError, TypeError):
                continue

        return rates
    except Exception:
        return {}


# Binance 永续合约资金费率接口
BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"


def fetch_binance_funding_rates(session: Optional[requests.Session] = None) -> Dict[str, float]:
    """从 Binance 获取全部 USDT 永续合约的当前资金费率。

    返回:
        {"BTCUSDT": 0.0001, "ETHUSDT": 0.0003, ...}
    """
    try:
        s = session or requests.Session()
        if not session:
            s.headers.update({
                "Accept": "application/json",
                "User-Agent": "CryptoBoxScanner/1.0",
            })
        resp = s.get(BINANCE_FUNDING_URL, timeout=15)
        if resp.status_code != 200:
            return {}

        rates = {}
        for item in resp.json():
            symbol = item.get("symbol", "")
            if not symbol.endswith("USDT"):
                continue
            try:
                rate = float(item.get("lastFundingRate", 0))
                rates[symbol] = rate
            except (ValueError, TypeError):
                continue

        return rates
    except Exception:
        return {}


def fetch_funding_rates(
    session: Optional[requests.Session] = None,
    source: str = "gateio",
) -> Dict[str, float]:
    """统一接口获取资金费率。

    参数:
        source: "gateio" 或 "binance"
    """
    if source == "binance":
        return fetch_binance_funding_rates(session)
    else:
        return fetch_gateio_funding_rates(session)


def check_funding_risk(
    symbol: str,
    funding_rates: Dict[str, float],
    extreme_threshold: float = 0.001,  # 0.1% 极端阈值
    high_threshold: float = 0.0005,     # 0.05% 高阈值
) -> Dict:
    """检查单个币种的资金费率风险。

    参数:
        symbol: 交易对名称 (如 "BTCUSDT" 或 "BTC_USDT")
        funding_rates: 资金费率字典
        extreme_threshold: 极端费率阈值 (默认0.1%)
        high_threshold: 高费率阈值 (默认0.05%)

    返回:
        {
            "symbol": str,
            "funding_rate": float,
            "rate_pct": float,         # 百分比形式
            "annualized_pct": float,   # 年化收益率估算
            "risk_level": str,         # "extreme" / "high" / "normal" / "unknown"
            "crowd_side": str,         # "long" / "short" / "neutral"
            "warning": str,            # 风险提示文本
        }
    """
    # 尝试匹配两种命名格式
    rate = funding_rates.get(symbol)
    if rate is None:
        # Gate.io 格式: BTC_USDT
        alt_symbol = symbol.replace("USDT", "_USDT")
        rate = funding_rates.get(alt_symbol)
    if rate is None:
        # Binance 格式: BTCUSDT
        alt_symbol = symbol.replace("_USDT", "USDT")
        rate = funding_rates.get(alt_symbol)

    if rate is None:
        return {
            "symbol": symbol,
            "funding_rate": None,
            "rate_pct": 0,
            "annualized_pct": 0,
            "risk_level": "unknown",
            "crowd_side": "neutral",
            "warning": "",
        }

    rate_pct = rate * 100  # 转换为百分比
    annualized_pct = abs(rate) * 3 * 365 * 100  # 按每8小时结算一次估算年化

    # 判断风险等级
    abs_rate = abs(rate)
    if abs_rate >= extreme_threshold:
        risk_level = "extreme"
    elif abs_rate >= high_threshold:
        risk_level = "high"
    else:
        risk_level = "normal"

    # 判断拥挤方向
    if rate > 0:
        crowd_side = "long"
        if risk_level == "extreme":
            warning = f"⚠ 多头极度拥挤！年化费率 {annualized_pct:.1f}%，回调风险高"
        elif risk_level == "high":
            warning = f"⚠ 多头拥挤，做多成本较高（年化 {annualized_pct:.1f}%）"
        else:
            warning = ""
    elif rate < 0:
        crowd_side = "short"
        if risk_level == "extreme":
            warning = f"⚠ 空头极度拥挤！年化费率 {annualized_pct:.1f}%，轧空风险高"
        elif risk_level == "high":
            warning = f"⚠ 空头拥挤，做空成本较高（年化 {annualized_pct:.1f}%）"
        else:
            warning = ""
    else:
        crowd_side = "neutral"
        warning = ""

    return {
        "symbol": symbol,
        "funding_rate": round(rate, 6),
        "rate_pct": round(rate_pct, 4),
        "annualized_pct": round(annualized_pct, 1),
        "risk_level": risk_level,
        "crowd_side": crowd_side,
        "warning": warning,
    }
