"""
加密货币箱体震荡选币软件
=========================
每日自动扫描所有 USDT 交易对，检测处于"箱体震荡"（横盘整理）
形态的币种，并列出支撑位、阻力位和价格区间。

数据源: Gate.io / Binance / CoinGecko 公开 API（无需 API Key）
依赖: pip install requests
用法: python crypto_box_scanner.py [--test] [--source gateio|binance|coingecko]
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, List, Tuple

import requests

# ============================================================
# 输出目录
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

# ============================================================
# 网络配置
# ============================================================
# 代理设置：如果你使用 Clash/V2Ray/ss 等代理工具，请设置以下地址
# 常见本地代理地址: http://127.0.0.1:7890 (Clash), http://127.0.0.1:10809 (V2Ray)
PROXY = None  # 示例: "http://127.0.0.1:7890" 或 "socks5://127.0.0.1:10808"
# 也可通过环境变量设置: set HTTPS_PROXY=http://127.0.0.1:7890

# 首选数据源: "gateio" (国内可直接访问) / "binance" / "coingecko"
DEFAULT_SOURCE = "gateio"

# ============================================================
# 扫描参数配置（可按需调整）
# ============================================================
KLINE_INTERVAL = "1d"           # K线周期: 1d=日线, 4h=四小时线
KLINE_LIMIT = 30                # 获取最近多少根K线（≥20）
TOP_BOTTOM_N = 5                # 计算支撑/阻力时取最高/最低的N根K线
TOUCH_THRESHOLD_PCT = 2.0       # 触及边界判定阈值 (%)
MIN_TOUCHES = 2                 # 支撑位和阻力位最少触及次数
MIN_CONTAINMENT = 0.70          # 收盘价在箱体内的最低比例
MAX_NORMALIZED_SLOPE = 0.15     # 最大归一化斜率（趋势平坦度）
MIN_RANGE_PCT = 3.0             # 箱体最小振幅 (%)
MAX_RANGE_PCT = 25.0            # 箱体最大振幅 (%)
MIN_VOLUME_USDT = 1_000_000     # 最小24h成交量 (USDT)
REQUEST_DELAY = 0.5             # 每次K线请求间隔（秒），控制频率
REQUEST_TIMEOUT = 20            # 单次HTTP请求超时（秒）
MAX_RETRIES = 2                 # 网络错误最大重试次数

# 高级分析参数
VOL_BREAKOUT_MULT = 1.5       # 成交量突破确认倍数
ATR_STOP_MULT = 1.5           # ATR止损倍数
ADX_THRESHOLD = 25.0          # ADX趋势阈值（低于此值视为横盘）

# 排除的稳定币
STABLECOINS = {
    "USDCUSDT", "BUSDUSDT", "TUSDUSDT", "DAIUSDT", "USDPUSDT",
    "FDUSDUSDT", "AEURUSDT", "EURUSDT",
}


# ============================================================
# 工具函数
# ============================================================
def linear_regression_slope(values: List[float]) -> float:
    """计算简单线性回归斜率（无外部依赖）"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


# ============================================================
# 技术指标计算函数
# ============================================================
def calc_atr(candles: List[Dict], period: int = 14) -> float:
    """计算 Average True Range (ATR)，用于动态止损止盈"""
    if len(candles) < period + 1:
        return 0.0

    true_ranges = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

    # Wilder's smoothing for ATR
    atr = sum(true_ranges[:period]) / period
    for i in range(period, len(true_ranges)):
        atr = (atr * (period - 1) + true_ranges[i]) / period

    return atr


def calc_adx(candles: List[Dict], period: int = 14) -> float:
    """计算 Average Directional Index (ADX)，判断趋势强度。
    ADX < 20: 无趋势/横盘
    ADX 20-25: 趋势形成中
    ADX > 25: 明确趋势
    ADX > 50: 极强趋势
    """
    if len(candles) < period * 2:
        return 0.0

    # Calculate +DM, -DM, and TR
    plus_dm = []
    minus_dm = []
    true_ranges = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_high = candles[i - 1]["high"]
        prev_low = candles[i - 1]["low"]
        prev_close = candles[i - 1]["close"]

        # True Range
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)

        # Directional Movement
        up_move = high - prev_high
        down_move = prev_low - low

        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)

        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)

    # Wilder's smoothing
    atr_val = sum(true_ranges[:period]) / period
    smoothed_plus_dm = sum(plus_dm[:period]) / period
    smoothed_minus_dm = sum(minus_dm[:period]) / period

    dx_values = []
    for i in range(period, len(true_ranges)):
        atr_val = (atr_val * (period - 1) + true_ranges[i]) / period
        smoothed_plus_dm = (smoothed_plus_dm * (period - 1) + plus_dm[i]) / period
        smoothed_minus_dm = (smoothed_minus_dm * (period - 1) + minus_dm[i]) / period

        if atr_val == 0:
            dx_values.append(0)
        else:
            plus_di = (smoothed_plus_dm / atr_val) * 100
            minus_di = (smoothed_minus_dm / atr_val) * 100
            di_sum = plus_di + minus_di
            dx = abs(plus_di - minus_di) / di_sum * 100 if di_sum > 0 else 0
            dx_values.append(dx)

    # ADX = smoothed DX
    if not dx_values:
        return 0.0
    adx = sum(dx_values[:period]) / period if len(dx_values) >= period else sum(dx_values) / len(dx_values)
    for i in range(period, len(dx_values)):
        adx = (adx * (period - 1) + dx_values[i]) / period

    return adx


def calc_vwap(candles: List[Dict]) -> float:
    """计算 Volume-Weighted Average Price (VWAP)。
    从第一根K线累积计算，返回最新的VWAP值。
    """
    if not candles:
        return 0.0

    cumulative_pv = 0.0
    cumulative_vol = 0.0

    for c in candles:
        typical_price = (c["high"] + c["low"] + c["close"]) / 3
        volume = c.get("volume", 0)
        cumulative_pv += typical_price * volume
        cumulative_vol += volume

    if cumulative_vol == 0:
        return 0.0
    return cumulative_pv / cumulative_vol


def calc_ema(data: List[float], period: int) -> List[float]:
    """计算 Exponential Moving Average"""
    if len(data) < period:
        return [data[-1]] * len(data) if data else []

    k = 2.0 / (period + 1)
    result = [sum(data[:period]) / period]  # SMA as first value
    for i in range(period, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))

    # Pad beginning with the first EMA value
    padding = [result[0]] * (len(data) - len(result))
    return padding + result


def check_volume_breakout(
    candles: List[Dict],
    support: float,
    resistance: float,
    vol_threshold_mult: float = 1.5,
    price_proximity_pct: float = 3.0,
) -> Dict:
    """检测成交量突破信号。

    检测最近K线的成交量是否放量，以及价格是否接近箱体边界。
    返回:
        {
            "volume_surge": bool,       # 是否有成交量放量
            "vol_ratio": float,         # 最近量/平均量的比值
            "near_boundary": bool,      # 是否接近边界
            "boundary_side": str,       # "support" / "resistance" / "none"
            "breakout_warning": bool,   # 是否发出突破预警
            "direction": str,           # "up" / "down" / "none"
        }
    """
    n = len(candles)
    if n < 5:
        return {
            "volume_surge": False, "vol_ratio": 1.0,
            "near_boundary": False, "boundary_side": "none",
            "breakout_warning": False, "direction": "none",
        }

    recent_vols = [c.get("volume", 0) for c in candles[-3:]]
    prev_vols = [c.get("volume", 0) for c in candles[-8:-3]]

    avg_recent_vol = sum(recent_vols) / max(len(recent_vols), 1)
    avg_prev_vol = sum(prev_vols) / max(len(prev_vols), 1)

    vol_ratio = avg_recent_vol / avg_prev_vol if avg_prev_vol > 0 else 1.0
    volume_surge = vol_ratio >= vol_threshold_mult

    # Check price proximity to boundaries
    current_price = candles[-1]["close"]
    support_zone = support * (1 + price_proximity_pct / 100)
    resistance_zone = resistance * (1 - price_proximity_pct / 100)

    near_boundary = False
    boundary_side = "none"
    if current_price >= resistance_zone:
        near_boundary = True
        boundary_side = "resistance"
    elif current_price <= support_zone:
        near_boundary = True
        boundary_side = "support"

    # Breakout warning: volume surge + near boundary
    breakout_warning = volume_surge and near_boundary
    direction = "up" if boundary_side == "resistance" else ("down" if boundary_side == "support" else "none")

    return {
        "volume_surge": volume_surge,
        "vol_ratio": round(vol_ratio, 2),
        "near_boundary": near_boundary,
        "boundary_side": boundary_side,
        "breakout_warning": breakout_warning,
        "direction": direction,
    }


def detect_box_multi_tf(
    symbol: str,
    kline_data: Dict[str, List[Dict]],
    params: Optional[Dict] = None,
) -> Optional[Dict]:
    """多时间框架箱体嵌套检测。

    在不同周期(1H/4H/1D)分别检测箱体，进行共振评分叠加。

    参数:
        kline_data: {"1h": [candles], "4h": [candles], "1d": [candles]}
    返回:
        综合检测结果，包含各周期详情和共振评分
    """
    results_by_tf = {}
    tf_weights = {"1h": 0.3, "4h": 0.35, "1d": 0.35}

    for tf_key, candles in kline_data.items():
        if candles and len(candles) >= 20:
            result = detect_box_range(symbol, candles)
            if result:
                results_by_tf[tf_key] = result

    if not results_by_tf:
        return None

    # Calculate resonance score
    resonance_score = 0
    total_weight = 0
    tf_details = {}

    for tf_key, weight in tf_weights.items():
        if tf_key in results_by_tf:
            r = results_by_tf[tf_key]
            resonance_score += r["confidence"] * weight
            total_weight += weight
            tf_details[tf_key] = {
                "confidence": r["confidence"],
                "support": r["support"],
                "resistance": r["resistance"],
                "range_pct": r["range_pct"],
                "position_pct": r["position_pct"],
            }

    if total_weight > 0:
        resonance_score /= total_weight
    else:
        resonance_score = 0

    # Use 1d result as primary if available, else first available
    primary_tf = "1d" if "1d" in results_by_tf else list(results_by_tf.keys())[0]
    primary = results_by_tf[primary_tf]

    resonance_bonus = min((len(results_by_tf) - 1) * 10, 20)  # Up to 20 bonus for multi-TF resonance
    adjusted_confidence = min(round(resonance_score + resonance_bonus), 100)

    return {
        "symbol": symbol,
        "support": primary["support"],
        "resistance": primary["resistance"],
        "range_pct": primary["range_pct"],
        "current_price": primary["current_price"],
        "position_pct": primary["position_pct"],
        "confidence": adjusted_confidence,
        "containment_ratio": primary["containment_ratio"],
        "resistance_touches": primary["resistance_touches"],
        "support_touches": primary["support_touches"],
        "normalized_slope": primary["normalized_slope"],
        "candle_count": primary["candle_count"],
        "multi_tf_resonance": len(results_by_tf),
        "tf_details": tf_details,
        "resonance_score": round(resonance_score, 1),
    }


def fmt_price(price: float) -> str:
    """智能格式化价格显示"""
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


def fmt_pct(value: float) -> str:
    """格式化百分比"""
    return f"{value:.1f}%"


# ============================================================
# HTTP 请求层
# ============================================================
def _get_proxy() -> Optional[Dict[str, str]]:
    """获取代理配置，优先级: 脚本配置 > 环境变量 > Windows系统代理"""
    if PROXY:
        return {"http": PROXY, "https": PROXY}
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        val = os.environ.get(var, "")
        if val:
            return {"http": val, "https": val}
    # 检测Windows系统代理
    try:
        import urllib.request
        proxies = urllib.request.getproxies()
        http_proxy = proxies.get("http") or proxies.get("https")
        if http_proxy:
            return {"http": http_proxy, "https": http_proxy}
    except Exception:
        pass
    return None


def _create_session() -> requests.Session:
    """创建带连接池的 requests Session"""
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=5,
        pool_maxsize=10,
        max_retries=0,
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    proxy = _get_proxy()
    if proxy:
        session.proxies = proxy

    session.headers.update({
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "CryptoBoxScanner/1.0",
    })
    return session


def _http_get(
    session: requests.Session,
    url: str,
    params: Optional[Dict] = None,
    timeout: int = REQUEST_TIMEOUT,
    retries: int = MAX_RETRIES,
) -> Optional[dict]:
    """通用 HTTP GET 请求，带重试逻辑"""
    params = params or {}
    last_error = None

    for attempt in range(retries + 1):
        try:
            resp = session.get(url, params=params, timeout=timeout)

            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 5))
                print(f"  ⚠ 频率限制，等待 {retry_after}s...")
                time.sleep(retry_after)
                continue
            elif resp.status_code in (400, 404, 403):
                return None
            else:
                last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            last_error = "超时"
        except requests.exceptions.ConnectionError:
            last_error = "连接失败"
        except Exception as e:
            last_error = str(e)

        if attempt < retries:
            time.sleep(1.5)

    if last_error:
        print(f"  ✗ 请求失败 [{url[:60]}]: {last_error}")
    return None


# ============================================================
# 数据源: Binance
# ============================================================
BINANCE_URLS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api3.binance.com",
    "https://api.binance.us",
]


def _binance_request(session: requests.Session, path: str, params: Optional[Dict] = None) -> Optional[dict]:
    """向 Binance API 发起请求，自动尝试备用域名"""
    for base_url in BINANCE_URLS:
        url = f"{base_url}{path}"
        result = _http_get(session, url, params, retries=1)  # 每个域名只试1次，快速切换
        if result is not None:
            return result
        time.sleep(0.2)
    return None


def binance_fetch_symbols(session: requests.Session) -> List[str]:
    """获取 Binance 上所有可用的 USDT 交易对"""
    print("[1/4] 获取交易对列表 (Binance)...", end=" ", flush=True)
    data = _binance_request(session, "/api/v3/exchangeInfo")
    if not data or "symbols" not in data:
        print("失败！")
        return []

    symbols = []
    excluded_updown = 0
    excluded_stable = 0
    excluded_status = 0

    for s in data["symbols"]:
        symbol = s["symbol"]
        if not symbol.endswith("USDT"):
            continue
        if s.get("status") != "TRADING":
            excluded_status += 1
            continue

        base_asset = symbol.replace("USDT", "")
        # 排除 UP/DOWN 杠杆代币
        if base_asset.endswith("UP") or base_asset.endswith("DOWN"):
            excluded_updown += 1
            continue
        # 排除数字+L/S 杠杆代币 (如 BTC5LUSDT)
        is_leveraged = False
        for i, ch in enumerate(base_asset):
            if ch.isdigit() and i + 1 < len(base_asset) and base_asset[i + 1] in "LS":
                remainder = base_asset[i + 1:]
                if remainder in ("L", "S"):
                    is_leveraged = True
                    break
        if is_leveraged:
            excluded_updown += 1
            continue

        if symbol in STABLECOINS:
            excluded_stable += 1
            continue

        symbols.append(symbol)

    print(f"共 {len(symbols)} 个交易对")
    if excluded_updown or excluded_stable or excluded_status:
        details = []
        if excluded_status:
            details.append(f"{excluded_status} 非TRADING")
        if excluded_updown:
            details.append(f"{excluded_updown} 杠杆代币")
        if excluded_stable:
            details.append(f"{excluded_stable} 稳定币")
        print(f"  已排除: {', '.join(details)}")
    return symbols


def binance_fetch_volumes(session: requests.Session) -> Dict[str, float]:
    """批量获取 Binance 24h 成交量"""
    print("[2/4] 获取24h成交量数据 (Binance)...", end=" ", flush=True)
    data = _binance_request(session, "/api/v3/ticker/24hr")
    if not data:
        print("失败！")
        return {}

    volumes = {}
    for ticker in data:
        symbol = ticker.get("symbol", "")
        if symbol.endswith("USDT"):
            try:
                vol = float(ticker.get("quoteVolume", 0))
                volumes[symbol] = vol
            except (ValueError, TypeError):
                volumes[symbol] = 0.0

    print(f"获得 {len(volumes)} 个交易对数据")
    return volumes


def binance_fetch_klines(
    session: requests.Session,
    symbol: str,
    interval: str = KLINE_INTERVAL,
    limit: int = KLINE_LIMIT,
) -> Optional[List[Dict]]:
    """获取 Binance 单个交易对的K线数据"""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    data = _binance_request(session, "/api/v3/klines", params=params)

    if not data or not isinstance(data, list):
        return None

    candles = []
    for candle in data:
        if len(candle) < 5:
            continue
        try:
            c = {
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]),
            }
            if c["high"] < c["low"] or c["close"] <= 0:
                continue
            candles.append(c)
        except (ValueError, IndexError):
            continue

    if len(candles) < limit:
        return None

    return candles


# ============================================================
# 数据源: CoinGecko（免费，无需 API Key，无需代理也能访问）
# ============================================================
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
COINGECKO_PRO_BASE = "https://pro-api.coingecko.com/api/v3"  # 付费版备选


def _coingecko_request(session: requests.Session, path: str, params: Optional[Dict] = None) -> Optional[dict]:
    """向 CoinGecko API 发起请求"""
    url = f"{COINGECKO_BASE}{path}"
    return _http_get(session, url, params)


def coingecko_fetch_coins(session: requests.Session) -> List[Dict]:
    """
    获取 CoinGecko 上所有币种列表（包含 symbol, id, market_cap_rank）
    返回: [{"id": "bitcoin", "symbol": "btc", "name": "Bitcoin"}, ...]
    """
    print("[1/4] 获取币种列表 (CoinGecko)...", end=" ", flush=True)
    data = _coingecko_request(session, "/coins/list")
    if not data:
        print("失败！")
        return []
    print(f"共 {len(data)} 个币种")
    return data


def coingecko_fetch_markets(
    session: requests.Session,
    page: int = 1,
    per_page: int = 250,
) -> List[Dict]:
    """
    获取 CoinGecko 市场数据（含价格、成交量等）
    每次最多250条，需要分页
    """
    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": per_page,
        "page": page,
        "sparkline": "false",
        "price_change_percentage": "24h",
    }
    data = _coingecko_request(session, "/coins/markets", params=params)
    if not data:
        return []
    return data


def coingecko_fetch_all_markets(session: requests.Session, max_pages: int = 4) -> Dict[str, Dict]:
    """
    批量获取 CoinGecko 市场数据（多页）
    返回: {symbol_upper: market_data}
    """
    print("[2/4] 获取市场数据 (CoinGecko)...", end=" ", flush=True)
    all_markets = {}
    for page in range(1, max_pages + 1):
        markets = coingecko_fetch_markets(session, page=page, per_page=250)
        if not markets:
            break
        for m in markets:
            sym = m.get("symbol", "").upper()
            all_markets[sym] = m
        time.sleep(1.5)  # CoinGecko 免费版限速严格

    print(f"获得 {len(all_markets)} 个币种数据")
    return all_markets


def coingecko_fetch_ohlc(
    session: requests.Session,
    coin_id: str,
    days: int = 30,
) -> Optional[List[Dict]]:
    """
    获取 CoinGecko 单个币种的OHLC数据（日线）
    返回: [{"open": ..., "high": ..., "low": ..., "close": ...}, ...]
    """
    params = {"vs_currency": "usd", "days": str(days)}
    data = _coingecko_request(session, f"/coins/{coin_id}/ohlc", params=params)

    if not data or not isinstance(data, list):
        return None

    candles = []
    for candle in data:
        if len(candle) >= 5:
            try:
                c = {
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": 0,  # CoinGecko OHLC 不含成交量
                }
                if c["high"] >= c["low"] and c["close"] > 0:
                    candles.append(c)
            except (ValueError, IndexError):
                continue

    if len(candles) < min(days, KLINE_LIMIT):
        return None

    return candles[-KLINE_LIMIT:]  # 只取最近 KLINE_LIMIT 根


# ============================================================
# 数据源: Gate.io（国内可直接访问，推荐首选）
# ============================================================
GATEIO_BASE = "https://api.gateio.ws/api/v4"


def gateio_fetch_symbols(session: requests.Session) -> List[str]:
    """获取 Gate.io 上所有可用的 USDT 交易对"""
    print("[1/4] 获取交易对列表 (Gate.io)...", end=" ", flush=True)
    data = _http_get(session, f"{GATEIO_BASE}/spot/currency_pairs")
    if not data:
        print("失败！")
        return []

    symbols = []
    excluded_updown = 0
    excluded_stable = 0

    for pair in data:
        pid = pair.get("id", "")
        if not pid.endswith("_USDT"):
            continue
        if pair.get("trade_status") != "tradable":
            continue

        # 排除杠杆代币 (如 BTC5L_USDT, BTC5S_USDT)
        base = pid.replace("_USDT", "")
        is_leveraged = False
        for i, ch in enumerate(base):
            if ch.isdigit() and i + 1 < len(base) and base[i + 1] in "LS":
                remainder = base[i + 1:]
                if remainder in ("L", "S"):
                    is_leveraged = True
                    break
        if is_leveraged:
            excluded_updown += 1
            continue

        # 排除 UP/DOWN 型杠杆代币 (Gate.io 也有)
        if base.endswith("UP") or base.endswith("DOWN"):
            excluded_updown += 1
            continue

        # 排除稳定币
        raw_symbol = pid.replace("_", "")
        if raw_symbol in STABLECOINS:
            excluded_stable += 1
            continue

        symbols.append(pid)  # 保持 BTC_USDT 格式

    print(f"共 {len(symbols)} 个交易对")
    if excluded_updown or excluded_stable:
        details = []
        if excluded_updown:
            details.append(f"{excluded_updown} 杠杆代币")
        if excluded_stable:
            details.append(f"{excluded_stable} 稳定币")
        print(f"  已排除: {', '.join(details)}")
    return symbols


def gateio_fetch_volumes(session: requests.Session) -> Dict[str, float]:
    """批量获取 Gate.io 24h 成交量（使用 tickers 接口）"""
    print("[2/4] 获取24h成交量数据 (Gate.io)...", end=" ", flush=True)
    data = _http_get(session, f"{GATEIO_BASE}/spot/tickers")
    if not data:
        print("失败！")
        return {}

    volumes = {}
    for ticker in data:
        pid = ticker.get("currency_pair", "")
        if pid.endswith("_USDT"):
            try:
                # quote_volume 是以 USDT 计价的成交量
                vol = float(ticker.get("quote_volume", 0))
                volumes[pid] = vol
            except (ValueError, TypeError):
                volumes[pid] = 0.0

    print(f"获得 {len(volumes)} 个交易对数据")
    return volumes


def gateio_fetch_klines(
    session: requests.Session,
    symbol: str,
    interval: str = KLINE_INTERVAL,
    limit: int = KLINE_LIMIT,
) -> Optional[List[Dict]]:
    """
    获取 Gate.io 单个交易对的K线数据。
    Gate.io K线格式: [timestamp_s, volume_quote, close, high, low, open, volume_base]
    """
    params = {
        "currency_pair": symbol,
        "interval": interval,
        "limit": limit,
    }
    data = _http_get(session, f"{GATEIO_BASE}/spot/candlesticks", params=params)

    if not data or not isinstance(data, list):
        return None

    candles = []
    for candle in data:
        if len(candle) < 7:
            continue
        try:
            # Gate.io 格式: [ts, vol_quote, close, high, low, open, vol_base]
            c = {
                "open": float(candle[5]),
                "high": float(candle[3]),
                "low": float(candle[4]),
                "close": float(candle[2]),
                "volume": float(candle[1]),
            }
            if c["high"] < c["low"] or c["close"] <= 0:
                continue
            candles.append(c)
        except (ValueError, IndexError):
            continue

    if len(candles) < limit:
        return None

    return candles


def gateio_get_display_name(symbol: str) -> str:
    """BTC_USDT -> BTCUSDT"""
    return symbol.replace("_", "")

def gateio_get_test_symbols() -> List[str]:
    """Gate.io 格式的测试币种列表"""
    return [
        "BTC_USDT", "ETH_USDT", "BNB_USDT", "SOL_USDT", "XRP_USDT",
        "ADA_USDT", "DOGE_USDT", "AVAX_USDT", "DOT_USDT", "LINK_USDT",
        "MATIC_USDT", "UNI_USDT", "ATOM_USDT", "LTC_USDT", "FIL_USDT",
        "APT_USDT", "ARB_USDT", "OP_USDT", "NEAR_USDT", "INJ_USDT",
    ]


# ============================================================
# 箱体震荡检测算法
# ============================================================
def detect_box_range(
    symbol: str,
    candles: List[Dict],
) -> Optional[Dict]:
    """
    检测一个币种是否处于箱体震荡形态。

    六步检测法：
    1. 计算支撑位（底部N根最低价均值）和阻力位（顶部N根最高价均值）
    2. 振幅必须在 MIN_RANGE_PCT ~ MAX_RANGE_PCT 之间
    3. 支撑位和阻力位各自至少有 MIN_TOUCHES 次触及
    4. 收盘价线性回归斜率接近零（无趋势）
    5. 至少 MIN_CONTAINMENT 比例的收盘价落在箱体内
    6. 当前价格必须在箱体区间内
    """
    n = len(candles)

    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    # ---- 步骤1: 计算支撑位和阻力位 ----
    sorted_highs = sorted(highs, reverse=True)
    sorted_lows = sorted(lows)

    resistance = sum(sorted_highs[:TOP_BOTTOM_N]) / TOP_BOTTOM_N
    support = sum(sorted_lows[:TOP_BOTTOM_N]) / TOP_BOTTOM_N

    if support <= 0:
        return None

    # ---- 步骤2: 振幅检查 ----
    range_pct = (resistance - support) / support * 100
    if range_pct < MIN_RANGE_PCT or range_pct > MAX_RANGE_PCT:
        return None

    # ---- 步骤3: 触及次数检查 ----
    resistance_lower = resistance * (1 - TOUCH_THRESHOLD_PCT / 100)
    support_upper = support * (1 + TOUCH_THRESHOLD_PCT / 100)

    resistance_touches = sum(1 for h in highs if h >= resistance_lower)
    support_touches = sum(1 for l in lows if l <= support_upper)

    if resistance_touches < MIN_TOUCHES or support_touches < MIN_TOUCHES:
        return None

    # ---- 步骤4: 趋势平坦度检查 ----
    slope = linear_regression_slope(closes)
    mean_close = sum(closes) / len(closes)
    if mean_close <= 0:
        return None
    normalized_slope = abs(slope) / mean_close
    if normalized_slope > MAX_NORMALIZED_SLOPE:
        return None

    # ---- 步骤5: 包含率检查 ----
    contained = sum(1 for c in closes if support <= c <= resistance)
    containment_ratio = contained / n
    if containment_ratio < MIN_CONTAINMENT:
        return None

    # ---- 步骤6: 当前位置检查 ----
    current_price = closes[-1]
    if current_price < support or current_price > resistance:
        return None

    # ---- 计算位置百分比 ----
    position_pct = (current_price - support) / (resistance - support) * 100

    # ---- 步骤7: 计算 ATR（动态止损止盈） ----
    atr_value = calc_atr(candles, 14)
    atr_pct = (atr_value / current_price * 100) if current_price > 0 else 0

    # 做多止损：支撑位下方 N×ATR
    long_stop_loss = support - ATR_STOP_MULT * atr_value
    # 做空止损：阻力位上方 N×ATR
    short_stop_loss = resistance + ATR_STOP_MULT * atr_value
    # 做多止盈：阻力位（或阻力位+0.3×ATR作为突破缓冲）
    long_take_profit = resistance
    # 做空止盈：支撑位
    short_take_profit = support
    # 建议入场
    suggested_entry = support * 1.005 if position_pct <= 50 else resistance * 0.995

    # ---- 步骤8: 计算 ADX（趋势强度过滤） ----
    adx = calc_adx(candles, 14)

    # ---- 步骤9: 成交量突破检测 ----
    vol_breakout = check_volume_breakout(
        candles, support, resistance,
        vol_threshold_mult=VOL_BREAKOUT_MULT,
    )

    # ---- 计算置信度评分 ----
    confidence = _calculate_confidence(
        resistance_touches, support_touches,
        containment_ratio, normalized_slope,
        range_pct, position_pct,
        adx=adx,
    )

    return {
        "symbol": symbol,
        "support": round(support, 8),
        "resistance": round(resistance, 8),
        "range_pct": round(range_pct, 2),
        "current_price": round(current_price, 8),
        "position_pct": round(position_pct, 1),
        "confidence": confidence,
        "containment_ratio": round(containment_ratio, 3),
        "resistance_touches": resistance_touches,
        "support_touches": support_touches,
        "normalized_slope": round(normalized_slope, 4),
        "candle_count": n,
        # 新增字段
        "atr_value": round(atr_value, 8),
        "atr_pct": round(atr_pct, 2),
        "adx": round(adx, 1),
        "trend_strength": _adx_label(adx),
        "suggested_entry": round(suggested_entry, 8),
        "long_stop_loss": round(max(long_stop_loss, support * 0.92), 8),
        "short_stop_loss": round(min(short_stop_loss, resistance * 1.08), 8),
        "long_take_profit": round(long_take_profit, 8),
        "short_take_profit": round(short_take_profit, 8),
        "volume_breakout": vol_breakout,
    }


def _calculate_confidence(
    resistance_touches: int,
    support_touches: int,
    containment_ratio: float,
    normalized_slope: float,
    range_pct: float,
    position_pct: float,
    adx: float = 0.0,
) -> int:
    """置信度评分（0-100分），新增ADX趋势强度调整"""
    score = 0.0

    # 1. 触及质量 (max 30)
    score += min(resistance_touches, 5) / 5 * 15
    score += min(support_touches, 5) / 5 * 15

    # 2. 包含率 (max 25)
    score += containment_ratio * 25

    # 3. 趋势平坦度 (max 20)
    slope_score = max(0, 1 - normalized_slope / MAX_NORMALIZED_SLOPE)
    score += slope_score * 20

    # 4. 箱体宽度 (max 15)
    if 5 <= range_pct <= 15:
        range_score = 1.0
    elif range_pct < 5:
        range_score = range_pct / 5.0
    else:
        range_score = max(0, 1 - (range_pct - 15) / 10)
    score += range_score * 15

    # 5. 当前位置 (max 10)
    if position_pct <= 30:
        score += 10
    elif position_pct <= 70:
        score += 5

    # 6. ADX 趋势强度调整 (max ±10)
    # 基于 ADX_THRESHOLD 做动态调整
    if adx > 0:
        if adx < ADX_THRESHOLD - 5:
            score += 10  # 明确横盘，加分
        elif adx < ADX_THRESHOLD:
            score += 5   # 偏横盘
        elif adx < ADX_THRESHOLD + 10:
            score -= 5   # 趋势形成，减分
        else:
            score -= 10  # 强趋势，不适合箱体

    return round(max(0, min(score, 100)))


def _adx_label(adx: float) -> str:
    """ADX 趋势强度标签"""
    if adx <= 0:
        return "未计算"
    elif adx < 20:
        return "横盘/无趋势"
    elif adx < 25:
        return "趋势形成中"
    elif adx < 35:
        return "温和趋势"
    elif adx < 50:
        return "强趋势"
    else:
        return "极强趋势"


# ============================================================
# 扫描主流程
# ============================================================
def scan_all_binance(session: requests.Session) -> Tuple[List[Dict], Dict]:
    """使用 Binance 数据源扫描所有币种"""
    results = []
    meta = {
        "scan_time": datetime.now().isoformat(),
        "data_source": "Binance",
        "total_pairs_found": 0,
        "total_filtered_by_volume": 0,
        "total_klines_fetched": 0,
        "total_errors": 0,
        "filters_passed": 0,
        "parameters": {
            "kline_interval": KLINE_INTERVAL,
            "kline_limit": KLINE_LIMIT,
            "min_range_pct": MIN_RANGE_PCT,
            "max_range_pct": MAX_RANGE_PCT,
            "min_volume_usdt": MIN_VOLUME_USDT,
            "min_containment": MIN_CONTAINMENT,
            "max_normalized_slope": MAX_NORMALIZED_SLOPE,
            "min_touches": MIN_TOUCHES,
        },
    }

    # 步骤1: 获取交易对
    symbols = binance_fetch_symbols(session)
    if not symbols:
        print("\n✗ 无法获取交易对列表。")
        _print_network_help()
        return [], meta
    meta["total_pairs_found"] = len(symbols)

    # 步骤2: 获取成交量
    volumes = binance_fetch_volumes(session)
    if not volumes:
        print("\n✗ 无法获取成交量数据。")
        _print_network_help()
        return [], meta

    # 步骤3: 过滤 + 检测
    print("[3/4] 按成交量过滤并检测箱体...")
    candidates = [sym for sym in symbols if volumes.get(sym, 0) >= MIN_VOLUME_USDT]
    meta["total_filtered_by_volume"] = len(symbols) - len(candidates)
    print(f"  成交量达标 (≥{MIN_VOLUME_USDT//10000}万 USDT): {len(candidates)} 个")

    results = _scan_candidates(session, candidates, meta, fetcher=binance_fetch_klines)
    return results, meta


def scan_all_coingecko(session: requests.Session) -> Tuple[List[Dict], Dict]:
    """使用 CoinGecko 数据源扫描（限制在成交量前500的币种）"""
    results = []
    meta = {
        "scan_time": datetime.now().isoformat(),
        "data_source": "CoinGecko",
        "total_pairs_found": 0,
        "total_filtered_by_volume": 0,
        "total_klines_fetched": 0,
        "total_errors": 0,
        "filters_passed": 0,
        "parameters": {
            "kline_interval": KLINE_INTERVAL,
            "kline_limit": KLINE_LIMIT,
            "min_range_pct": MIN_RANGE_PCT,
            "max_range_pct": MAX_RANGE_PCT,
            "min_volume_usdt": MIN_VOLUME_USDT,
            "min_containment": MIN_CONTAINMENT,
            "max_normalized_slope": MAX_NORMALIZED_SLOPE,
            "min_touches": MIN_TOUCHES,
        },
    }

    # 步骤1: 获取市场数据（含成交量，按成交量排序）
    markets = coingecko_fetch_all_markets(session, max_pages=3)  # 取前750个

    if not markets:
        print("\n✗ 无法获取市场数据。")
        _print_network_help()
        return [], meta

    meta["total_pairs_found"] = len(markets)

    # 步骤2: 按成交量过滤并构建候选列表
    candidates = []
    for sym, m in markets.items():
        vol = m.get("total_volume", 0) or 0
        if vol >= MIN_VOLUME_USDT:
            coin_id = m.get("id", "")
            if coin_id:
                candidates.append((sym, coin_id, vol))

    meta["total_filtered_by_volume"] = len(markets) - len(candidates)
    print("[2/4] 按成交量过滤...")
    print(f"  成交量达标 (≥{MIN_VOLUME_USDT//10000}万 USD): {len(candidates)} 个")

    # 步骤3: 逐个获取OHLC并检测
    print("[3/4] 获取OHLC数据并检测箱体...")
    total = len(candidates)
    progress_every = max(1, total // 20)

    for i, (sym, coin_id, vol) in enumerate(candidates):
        if i % progress_every == 0 or i == total - 1:
            pct = (i + 1) / total * 100
            print(f"  [{i+1}/{total}] {pct:.0f}%  |  已发现 {len(results)} 个箱体", end="\r")

        candles = coingecko_fetch_ohlc(session, coin_id, days=KLINE_LIMIT + 5)
        meta["total_klines_fetched"] += 1

        if candles is None:
            meta["total_errors"] += 1
            time.sleep(1.2)  # CoinGecko 限速 ~30次/分钟
            continue

        result = detect_box_range(sym, candles)
        if result is not None:
            results.append(result)

        # CoinGecko 限速更严格
        time.sleep(1.2)

    print(f"\n  扫描完成！共检测 {total} 个币种，发现 {len(results)} 个箱体震荡形态")
    meta["filters_passed"] = len(results)
    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results, meta


def scan_all_gateio(session: requests.Session) -> Tuple[List[Dict], Dict]:
    """使用 Gate.io 数据源扫描所有币种（国内可直接访问）"""
    results = []
    meta = {
        "scan_time": datetime.now().isoformat(),
        "data_source": "Gate.io",
        "total_pairs_found": 0,
        "total_filtered_by_volume": 0,
        "total_klines_fetched": 0,
        "total_errors": 0,
        "filters_passed": 0,
        "parameters": {
            "kline_interval": KLINE_INTERVAL,
            "kline_limit": KLINE_LIMIT,
            "min_range_pct": MIN_RANGE_PCT,
            "max_range_pct": MAX_RANGE_PCT,
            "min_volume_usdt": MIN_VOLUME_USDT,
            "min_containment": MIN_CONTAINMENT,
            "max_normalized_slope": MAX_NORMALIZED_SLOPE,
            "min_touches": MIN_TOUCHES,
        },
    }

    # 步骤1: 获取交易对
    symbols = gateio_fetch_symbols(session)
    if not symbols:
        print("\n✗ 无法获取交易对列表。")
        _print_network_help()
        return [], meta
    meta["total_pairs_found"] = len(symbols)

    # 步骤2: 获取成交量
    volumes = gateio_fetch_volumes(session)
    if not volumes:
        print("\n✗ 无法获取成交量数据。")
        _print_network_help()
        return [], meta

    # 步骤3: 过滤 + 检测
    print("[3/4] 按成交量过滤并检测箱体...")
    candidates = [sym for sym in symbols if volumes.get(sym, 0) >= MIN_VOLUME_USDT]
    meta["total_filtered_by_volume"] = len(symbols) - len(candidates)
    print(f"  成交量达标 (≥{MIN_VOLUME_USDT//10000}万 USDT): {len(candidates)} 个")

    total = len(candidates)
    progress_every = max(1, total // 20)

    for i, symbol in enumerate(candidates):
        if i % progress_every == 0 or i == total - 1:
            pct = (i + 1) / total * 100
            print(f"  [{i+1}/{total}] {pct:.0f}%  |  已发现 {len(results)} 个箱体", end="\r")

        candles = gateio_fetch_klines(session, symbol)
        meta["total_klines_fetched"] += 1

        if candles is None:
            meta["total_errors"] += 1
            time.sleep(REQUEST_DELAY)
            continue

        # 转换显示名称（BTC_USDT -> BTCUSDT）
        display_name = gateio_get_display_name(symbol)
        result = detect_box_range(display_name, candles)
        if result is not None:
            results.append(result)

        time.sleep(REQUEST_DELAY)

    print(f"\n  扫描完成！共检测 {total} 个币种，发现 {len(results)} 个箱体震荡形态")
    meta["filters_passed"] = len(results)
    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results, meta


def _scan_candidates(
    session: requests.Session,
    candidates: List[str],
    meta: Dict,
    fetcher,
) -> List[Dict]:
    """通用扫描候选币种"""
    results = []
    total = len(candidates)
    progress_every = max(1, total // 20)

    for i, symbol in enumerate(candidates):
        if i % progress_every == 0 or i == total - 1:
            pct = (i + 1) / total * 100
            print(f"  [{i+1}/{total}] {pct:.0f}%  |  已发现 {len(results)} 个箱体", end="\r")

        candles = fetcher(session, symbol)
        meta["total_klines_fetched"] += 1

        if candles is None:
            meta["total_errors"] += 1
            time.sleep(REQUEST_DELAY)
            continue

        result = detect_box_range(symbol, candles)
        if result is not None:
            results.append(result)

        time.sleep(REQUEST_DELAY)

    print(f"\n  扫描完成！共检测 {total} 个币种，发现 {len(results)} 个箱体震荡形态")
    meta["filters_passed"] = len(results)
    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


def _print_network_help():
    """打印网络连接帮助信息"""
    print()
    print("  ╔══════════════════════════════════════════════════════╗")
    print("  ║  网络连接失败，可能的原因和解决方案：                ║")
    print("  ║                                                      ║")
    print("  ║  1. 需要代理（中国大陆用户）                        ║")
    print("  ║     设置代理后重试：                                ║")
    print("  ║     set HTTPS_PROXY=http://127.0.0.1:7890           ║")
    print("  ║     python crypto_box_scanner.py                    ║")
    print("  ║                                                      ║")
    print("  ║     或者在脚本顶部修改 PROXY 变量：                  ║")
    print("  ║     PROXY = \"http://127.0.0.1:7890\"                ║")
    print("  ║                                                      ║")
    print("  ║  2. 尝试 CoinGecko 数据源（可能不需代理）           ║")
    print("  ║     python crypto_box_scanner.py --source coingecko ║")
    print("  ║                                                      ║")
    print("  ║  3. 检查防火墙/网络设置                             ║")
    print("  ╚══════════════════════════════════════════════════════╝")
    print()


# ============================================================
# 输出格式化
# ============================================================
def print_results(results: List[Dict], meta: Dict):
    """在控制台打印格式化的扫描结果表格"""
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = meta.get("total_pairs_found", 0)
    passed = len(results)
    source = meta.get("data_source", "Unknown")

    print()
    print("=" * 95)
    print(f"  加密货币箱体震荡扫描结果 - {scan_time}")
    print(f"  数据源: {source}  |  扫描: {total} 个  |  符合条件: {passed} 个")
    print("=" * 95)

    if not results:
        print("\n  当前没有检测到处于箱体震荡形态的币种。")
        print("  可能原因：市场处于强趋势中，或参数过于严格。")
        print("=" * 95)
        return

    header = (
        f"  {'Symbol':<16}"
        f"{'支撑位':>14}"
        f"{'阻力位':>14}"
        f"{'振幅':>8}"
        f"{'当前价':>14}"
        f"{'位置':>7}"
        f"{'置信度':>8}"
    )
    sep = "  " + "─" * (len(header) - 2)
    print(sep)
    print(header)
    print(sep)

    for r in results:
        conf = r["confidence"]
        if conf >= 80:
            conf_str = f"★ {conf}"
        elif conf >= 65:
            conf_str = f"☆ {conf}"
        else:
            conf_str = f"  {conf}"

        print(
            f"  {r['symbol']:<16}"
            f"{fmt_price(r['support']):>14}"
            f"{fmt_price(r['resistance']):>14}"
            f"{fmt_pct(r['range_pct']):>8}"
            f"{fmt_price(r['current_price']):>14}"
            f"{fmt_pct(r['position_pct']):>7}"
            f"{conf_str:>8}"
        )

    print(sep)
    print()

    avg_conf = sum(r["confidence"] for r in results) / len(results) if results else 0
    best = results[0] if results else None

    dist = {"3-5%": 0, "5-10%": 0, "10-15%": 0, "15-25%": 0}
    for r in results:
        rp = r["range_pct"]
        if rp <= 5:
            dist["3-5%"] += 1
        elif rp <= 10:
            dist["5-10%"] += 1
        elif rp <= 15:
            dist["10-15%"] += 1
        else:
            dist["15-25%"] += 1
    dist_str = ",  ".join(f"{k}: {v}" for k, v in dist.items() if v > 0)

    print("  统计摘要:")
    print(f"    总扫描币种: {total}")
    print(f"    符合箱体条件: {passed}")
    print(f"    检测率: {passed/total*100:.1f}%" if total > 0 else "    检测率: N/A")
    print(f"    平均置信度: {avg_conf:.1f}")
    if best:
        print(f"    最佳: {best['symbol']} (置信度 {best['confidence']}, "
              f"支撑 {fmt_price(best['support'])}, 阻力 {fmt_price(best['resistance'])})")
    print(f"    箱体宽度分布: {dist_str}")

    print("=" * 95)


def save_results(results: List[Dict], meta: Dict):
    """保存结果到 JSON 文件"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    avg_conf = sum(r["confidence"] for r in results) / len(results) if results else 0

    dist = {"3-5%": 0, "5-10%": 0, "10-15%": 0, "15-25%": 0}
    for r in results:
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
        "meta": meta,
        "results": results,
        "summary": {
            "avg_confidence": round(avg_conf, 1),
            "range_distribution": dist,
        },
    }

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"box_scan_{timestamp}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)
    latest_path = os.path.join(OUTPUT_DIR, "box_scan_latest.json")

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  结果已保存至: {filepath}")
    print(f"  最新结果副本: {latest_path}")


# ============================================================
# 测试模式
# ============================================================
def scan_test(source: str = "binance"):
    """测试模式：仅扫描主流币种，快速验证算法"""
    print("=" * 80)
    print(f"  🔧 测试模式：扫描主流币种验证算法 (数据源: {source})")
    print("=" * 80)

    test_binance = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
        "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
        "MATICUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "FILUSDT",
        "APTUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT", "INJUSDT",
    ]

    test_coingecko = {
        "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
        "SOL": "solana", "XRP": "ripple", "ADA": "cardano",
        "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
        "LINK": "chainlink", "MATIC": "matic-network", "UNI": "uniswap",
        "ATOM": "cosmos", "LTC": "litecoin", "FIL": "filecoin",
        "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
        "NEAR": "near", "INJ": "injective-protocol",
    }

    session = _create_session()
    results = []

    if source == "coingecko":
        # CoinGecko 测试
        print(f"\n检测 {len(test_coingecko)} 个主流币种...\n")
        for i, (sym, coin_id) in enumerate(test_coingecko.items()):
            print(f"  [{i+1}/{len(test_coingecko)}] 检测 {sym}...", end=" ", flush=True)
            candles = coingecko_fetch_ohlc(session, coin_id, days=KLINE_LIMIT + 5)
            if candles is None:
                print("数据获取失败")
                time.sleep(1.2)
                continue

            result = detect_box_range(sym, candles)
            if result:
                results.append(result)
                print(f"✓ 箱体! 支撑={fmt_price(result['support'])} "
                      f"阻力={fmt_price(result['resistance'])} "
                      f"振幅={fmt_pct(result['range_pct'])} "
                      f"置信度={result['confidence']}")
            else:
                print("✗ 非箱体形态")
            time.sleep(1.2)
    elif source == "gateio":
        # Gate.io 测试
        test_symbols_gateio = gateio_get_test_symbols()
        print(f"\n检测 {len(test_symbols_gateio)} 个主流币种...\n")
        for i, symbol in enumerate(test_symbols_gateio):
            print(f"  [{i+1}/{len(test_symbols_gateio)}] 检测 {symbol}...", end=" ", flush=True)
            candles = gateio_fetch_klines(session, symbol)
            if candles is None:
                print("数据获取失败")
                time.sleep(REQUEST_DELAY)
                continue

            display_name = gateio_get_display_name(symbol)
            result = detect_box_range(display_name, candles)
            if result:
                results.append(result)
                print(f"✓ 箱体! 支撑={fmt_price(result['support'])} "
                      f"阻力={fmt_price(result['resistance'])} "
                      f"振幅={fmt_pct(result['range_pct'])} "
                      f"置信度={result['confidence']}")
            else:
                print("✗ 非箱体形态")
            time.sleep(REQUEST_DELAY)
    else:
        # Binance 测试
        print(f"\n检测 {len(test_binance)} 个主流币种...\n")
        for i, symbol in enumerate(test_binance):
            print(f"  [{i+1}/{len(test_binance)}] 检测 {symbol}...", end=" ", flush=True)
            candles = binance_fetch_klines(session, symbol)
            if candles is None:
                print("数据获取失败")
                time.sleep(REQUEST_DELAY)
                continue

            result = detect_box_range(symbol, candles)
            if result:
                results.append(result)
                print(f"✓ 箱体! 支撑={fmt_price(result['support'])} "
                      f"阻力={fmt_price(result['resistance'])} "
                      f"振幅={fmt_pct(result['range_pct'])} "
                      f"置信度={result['confidence']}")
            else:
                print("✗ 非箱体形态")
            time.sleep(REQUEST_DELAY)

    results.sort(key=lambda r: r["confidence"], reverse=True)

    meta = {
        "scan_time": datetime.now().isoformat(),
        "data_source": source.title(),
        "total_pairs_found": len(test_binance),
        "total_klines_fetched": len(test_binance),
        "filters_passed": len(results),
        "parameters": {
            "kline_interval": KLINE_INTERVAL,
            "kline_limit": KLINE_LIMIT,
            "min_range_pct": MIN_RANGE_PCT,
            "max_range_pct": MAX_RANGE_PCT,
        },
    }

    print(f"\n{'=' * 80}")
    print(f"  测试结果: {len(results)} 个币种处于箱体震荡")
    print(f"{'=' * 80}")

    if results:
        print(f"  {'Symbol':<12} {'支撑':>12} {'阻力':>12} {'振幅':>8} {'置信度':>8}")
        print(f"  {'─'*12} {'─'*12} {'─'*12} {'─'*8} {'─'*8}")
        for r in results:
            print(f"  {r['symbol']:<12} {fmt_price(r['support']):>12} "
                  f"{fmt_price(r['resistance']):>12} {fmt_pct(r['range_pct']):>8} "
                  f"{r['confidence']:>8}")

    save_results(results, meta)
    print()
    return results, meta


# ============================================================
# 主入口
# ============================================================
def main():
    """主入口"""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║     虚拟货币箱体震荡选币软件  v1.0               ║")
    print("║     Crypto Box Range Scanner                     ║")
    print("╚══════════════════════════════════════════════════╝")
    print()
    print(f"  参数: {KLINE_LIMIT}根{KLINE_INTERVAL}线 | "
          f"振幅 {MIN_RANGE_PCT}%-{MAX_RANGE_PCT}% | "
          f"成交量≥{MIN_VOLUME_USDT//10000}万USDT")

    proxy = _get_proxy()
    if proxy:
        print(f"  代理: {list(proxy.values())[0]}")
    else:
        print(f"  代理: 未设置（如网络不通请设置 HTTPS_PROXY 环境变量或修改脚本 PROXY 变量）")
    print()

    # 解析命令行参数
    source = DEFAULT_SOURCE
    is_test = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("--test", "-t"):
            is_test = True
        elif arg in ("--source", "-s"):
            if i + 1 < len(args):
                source = args[i + 1].lower()
                i += 1
            else:
                print("⚠ --source 需要指定 gateio, binance 或 coingecko")
                return
        elif arg in ("--help", "-h"):
            print("用法: python crypto_box_scanner.py [选项]")
            print()
            print("选项:")
            print("  --test, -t         测试模式（仅扫描20个主流币种）")
            print("  --source, -s SRC   数据源: gateio (默认,国内可用) / binance / coingecko")
            print("  --help, -h         显示帮助")
            print()
            print("代理设置:")
            print("  set HTTPS_PROXY=http://127.0.0.1:7890")
            print("  python crypto_box_scanner.py")
            print()
            print("  或在脚本顶部修改 PROXY 变量")
            print()
            print("示例:")
            print("  python crypto_box_scanner.py                        # 全量扫描 (Gate.io)")
            print("  python crypto_box_scanner.py --test                 # 快速测试")
            print("  python crypto_box_scanner.py --source gateio --test # 指定数据源测试")
            return
        else:
            print(f"⚠ 未知参数: {arg}，使用 --help 查看帮助")
            return
        i += 1

    if source not in ("gateio", "binance", "coingecko"):
        print(f"⚠ 不支持的数据源: {source}，使用默认 gateio")
        source = "gateio"

    start_time = time.time()

    try:
        if is_test:
            scan_test(source)
            return

        session = _create_session()

        # 检测网络连通性
        print("[0/4] 检测网络连通性...", end=" ", flush=True)
        if source == "gateio":
            test_urls = ["https://api.gateio.ws/api/v4/spot/time"]
        elif source == "binance":
            test_urls = ["https://api.binance.com/api/v3/ping", "https://api1.binance.com/api/v3/ping"]
        else:
            test_urls = ["https://api.coingecko.com/api/v3/ping"]

        connected = False
        for test_url in test_urls:
            try:
                r = session.get(test_url, timeout=10)
                if r.status_code == 200:
                    connected = True
                    break
            except Exception:
                continue

        if not connected:
            print("失败！")
            _print_network_help()
            return
        print("OK")

        if source == "gateio":
            results, meta = scan_all_gateio(session)
        elif source == "coingecko":
            results, meta = scan_all_coingecko(session)
        else:
            results, meta = scan_all_binance(session)

    except KeyboardInterrupt:
        print("\n\n⚠ 用户中断。")
        return
    except Exception as e:
        print(f"\n✗ 扫描过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return

    elapsed = time.time() - start_time

    print_results(results, meta)

    if results:
        save_results(results, meta)
    else:
        os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n  总耗时: {elapsed:.0f} 秒")
    print()


# ============================================================
# 市场情绪分析 (Fear & Greed Index)
# ============================================================
_fgi_cache: Optional[Dict] = None
_fgi_cache_time: float = 0
_FGI_CACHE_TTL = 600  # 10分钟


def fetch_fear_greed_index(limit: int = 1, session: Optional[requests.Session] = None) -> Optional[Dict]:
    """获取最新的恐惧贪婪指数 (alternative.me API)
    优先使用urllib(原生支持系统代理)，回退到requests session"""
    global _fgi_cache, _fgi_cache_time
    now = time.time()
    if _fgi_cache is not None and (now - _fgi_cache_time) < _FGI_CACHE_TTL:
        return _fgi_cache

    import json as _json
    url = f"https://api.alternative.me/fng/?limit={limit}"

    # 方法1: urllib (原生Windows系统代理, 无SSL证书问题)
    try:
        import urllib.request
        import ssl
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, headers={"User-Agent": "CryptoBoxScanner/2.0"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
            if "data" in data and len(data["data"]) > 0:
                _fgi_cache = data["data"][0]
                _fgi_cache_time = now
                return _fgi_cache
    except Exception:
        pass

    # 方法2: requests session (如果传入了session)
    if session:
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and len(data["data"]) > 0:
                    _fgi_cache = data["data"][0]
                    _fgi_cache_time = now
                    return _fgi_cache
        except Exception:
            pass

    return _fgi_cache


def get_fgi_adjustment(fgi_value: int) -> Dict:
    """根据恐惧贪婪指数计算置信度调整因子"""
    if fgi_value <= 20:
        return {"multiplier": 1.15, "bias": "bullish",
                "classification": "极度恐惧",
                "suggestion": "极度恐惧 → 市场恐慌，历史性买入窗口（逆向投资）"}
    elif fgi_value <= 40:
        return {"multiplier": 1.05, "bias": "bullish",
                "classification": "恐惧",
                "suggestion": "恐惧 → 市场偏悲观，逢低关注买入机会"}
    elif fgi_value <= 60:
        return {"multiplier": 1.00, "bias": "neutral",
                "classification": "中性",
                "suggestion": "中性 → 市场情绪正常，按技术信号操作"}
    elif fgi_value <= 80:
        return {"multiplier": 0.90, "bias": "bearish",
                "classification": "贪婪",
                "suggestion": "贪婪 → 市场偏乐观，注意控制仓"}
    else:
        return {"multiplier": 0.80, "bias": "bearish",
                "classification": "极度贪婪",
                "suggestion": "极度贪婪 → 警惕见顶风险，建议减仓"}


# ============================================================
# 资金费率扫描
# ============================================================
def _fetch_gateio_funding_rates(session: Optional[requests.Session] = None) -> Dict[str, float]:
    """从Gate.io获取全部USDT永续合约资金费率"""
    import json as _json
    url = "https://api.gateio.ws/api/v4/futures/usdt/contracts"
    headers = {"Accept": "application/json", "User-Agent": "CryptoBoxScanner/2.0"}

    # 方法1: requests session (自带certifi证书，SSL兼容性最好)
    if session:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 200:
                return _parse_funding_response(resp.json())
        except Exception:
            pass
    else:
        try:
            s = _create_session()
            resp = s.get(url, timeout=15)
            if resp.status_code == 200:
                return _parse_funding_response(resp.json())
            s.close()
        except Exception:
            pass

    # 方法2: urllib (不验证SSL - 公开数据)
    try:
        import urllib.request
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return _parse_funding_response(_json.loads(resp.read().decode("utf-8")))
    except Exception:
        pass

    return {}


def _parse_funding_response(data) -> Dict[str, float]:
    """解析资金费率API响应，提取USDT合约费率"""
    rates = {}
    for contract in data:
        name = contract.get("name", "")
        if name.endswith("_USDT"):
            try:
                rates[name] = float(contract.get("funding_rate", 0))
            except (ValueError, TypeError):
                pass
    return rates


def _fetch_binance_funding_rates(session: Optional[requests.Session] = None) -> Dict[str, float]:
    """从Binance获取全部USDT永续合约资金费率"""
    try:
        s = session or requests.Session()
        if not session:
            s.headers.update({
                "Accept": "application/json",
                "User-Agent": "CryptoBoxScanner/2.0",
            })
        resp = s.get("https://fapi.binance.com/fapi/v1/premiumIndex", timeout=15)
        if resp.status_code != 200:
            return {}
        rates = {}
        for item in resp.json():
            symbol = item.get("symbol", "")
            if symbol.endswith("USDT"):
                try:
                    rates[symbol] = float(item.get("lastFundingRate", 0))
                except (ValueError, TypeError):
                    pass
        return rates
    except Exception:
        return {}


def fetch_funding_rates(
    session: Optional[requests.Session] = None,
    source: str = "gateio",
) -> Dict[str, float]:
    """统一接口获取资金费率"""
    if source == "binance":
        return _fetch_binance_funding_rates(session)
    return _fetch_gateio_funding_rates(session)


def check_funding_risk(
    symbol: str,
    funding_rates: Dict[str, float],
) -> Dict:
    """检查单个币种的资金费率风险"""
    rate = funding_rates.get(symbol)
    if rate is None:
        rate = funding_rates.get(symbol.replace("USDT", "_USDT"))
    if rate is None:
        rate = funding_rates.get(symbol.replace("_USDT", "USDT"))

    if rate is None:
        return {
            "funding_rate": None, "rate_pct": 0, "annualized_pct": 0,
            "risk_level": "unknown", "crowd_side": "neutral", "warning": "",
        }

    rate_pct = rate * 100
    annualized_pct = abs(rate) * 3 * 365 * 100
    abs_rate = abs(rate)

    if abs_rate >= 0.001:
        risk_level = "extreme"
    elif abs_rate >= 0.0005:
        risk_level = "high"
    else:
        risk_level = "normal"

    if rate > 0:
        crowd_side = "long"
        warning = f"多头拥挤 (年化{annualized_pct:.1f}%)" if risk_level in ("high", "extreme") else ""
    elif rate < 0:
        crowd_side = "short"
        warning = f"空头拥挤 (年化{annualized_pct:.1f}%)" if risk_level in ("high", "extreme") else ""
    else:
        crowd_side = "neutral"
        warning = ""

    return {
        "funding_rate": round(rate, 6),
        "rate_pct": round(rate_pct, 4),
        "annualized_pct": round(annualized_pct, 1),
        "risk_level": risk_level,
        "crowd_side": crowd_side,
        "warning": warning,
    }


if __name__ == "__main__":
    main()
