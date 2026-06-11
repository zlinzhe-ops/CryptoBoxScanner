"""
Background scan worker for the Crypto Box Scanner GUI.
Runs scan operations in a QThread to keep the UI responsive.
"""

import sys
import os
import time
import io
from datetime import datetime
from typing import Optional, List, Dict

from PySide6.QtCore import QObject, Signal, Slot

# Ensure the parent directory is in path for imports
# In PyInstaller bundle, data files are extracted to sys._MEIPASS
if getattr(sys, 'frozen', False):
    _bundle_dir = sys._MEIPASS
else:
    _bundle_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if _bundle_dir not in sys.path:
    sys.path.insert(0, _bundle_dir)

# Import from the existing scanner module
from gui.trend_engine import detect_uptrend
# (suppress its print output during import)
_old_stdout = sys.stdout
sys.stdout = io.StringIO()
try:
    import crypto_box_scanner as scanner
finally:
    sys.stdout = _old_stdout

# Sentiment & Funding Rate functions are now built into crypto_box_scanner.
# No separate module imports needed — always available.

# ── Version check: verify crypto_box_scanner has the new functions ──
_SCANNER_VERSION = "v2.1"
_SCANNER_HAS_ATR = hasattr(scanner, "calc_atr")
_SCANNER_HAS_ADX = hasattr(scanner, "calc_adx")
_SCANNER_HAS_FGI = hasattr(scanner, "fetch_fear_greed_index")
_SCANNER_HAS_FUNDING = hasattr(scanner, "fetch_funding_rates")
_SCANNER_HAS_VWAP = hasattr(scanner, "calc_vwap")
_SCANNER_FUNCTIONS = [
    n for n in ["calc_atr","calc_adx","calc_vwap","check_volume_breakout",
    "detect_box_multi_tf","fetch_fear_greed_index","get_fgi_adjustment",
    "fetch_funding_rates","check_funding_risk"]
    if hasattr(scanner, n)
]


class EmittingStream(QObject):
    """A file-like object that emits Qt signals for each line written."""
    text_written = Signal(str)

    def __init__(self):
        super().__init__()
        self._buffer = ""

    def write(self, text: str):
        self._buffer += text
        if "\n" in self._buffer:
            lines = self._buffer.split("\n")
            self._buffer = lines[-1]
            for line in lines[:-1]:
                stripped = line.strip()
                if stripped:
                    self.text_written.emit(stripped)

    def flush(self):
        if self._buffer:
            stripped = self._buffer.strip()
            if stripped:
                self.text_written.emit(stripped)
            self._buffer = ""


class ScanWorker(QObject):
    """Worker object that performs cryptocurrency box range scanning in a background thread."""

    # Signals
    progress = Signal(int, int, str)       # current, total, current_symbol
    result_found = Signal(object)           # single box range result dict
    finished = Signal(object, object)       # results list, meta dict
    error_occurred = Signal(str)            # error message
    log_message = Signal(str)               # log line
    status_update = Signal(str)             # status bar message
    scan_complete = Signal()                # emitted when scan finishes (success or error)

    def __init__(
        self,
        source: str = "gateio",
        is_test: bool = False,
        params: Optional[Dict] = None,
        scan_mode: str = "box",  # "box" or "trend"
    ):
        super().__init__()
        self._source = source
        self._is_test = is_test
        self._params = params or {}
        self._scan_mode = scan_mode
        self._stop_requested = False
        self._session = None

    def request_stop(self):
        """Request the scan to stop gracefully."""
        self._stop_requested = True
        self.log_message.emit("[!] 正在停止扫描...")

    def _apply_params(self):
        """Apply user-configured parameters to the scanner module."""
        p = self._params
        if "kline_interval" in p:
            scanner.KLINE_INTERVAL = p["kline_interval"]
        if "kline_limit" in p:
            scanner.KLINE_LIMIT = p["kline_limit"]
        if "top_bottom_n" in p:
            scanner.TOP_BOTTOM_N = p["top_bottom_n"]
        if "touch_threshold_pct" in p:
            scanner.TOUCH_THRESHOLD_PCT = p["touch_threshold_pct"]
        if "min_touches" in p:
            scanner.MIN_TOUCHES = p["min_touches"]
        if "min_containment" in p:
            scanner.MIN_CONTAINMENT = p["min_containment"]
        if "max_normalized_slope" in p:
            scanner.MAX_NORMALIZED_SLOPE = p["max_normalized_slope"]
        if "min_range_pct" in p:
            scanner.MIN_RANGE_PCT = p["min_range_pct"]
        if "max_range_pct" in p:
            scanner.MAX_RANGE_PCT = p["max_range_pct"]
        if "min_volume_usdt" in p:
            scanner.MIN_VOLUME_USDT = p["min_volume_usdt"]
        if "request_delay" in p:
            scanner.REQUEST_DELAY = p["request_delay"]
        if "proxy" in p:
            scanner.PROXY = p["proxy"]
        # Advanced params
        if "vol_breakout_mult" in p:
            scanner.VOL_BREAKOUT_MULT = p["vol_breakout_mult"]
        if "atr_stop_mult" in p:
            scanner.ATR_STOP_MULT = p["atr_stop_mult"]
        if "adx_threshold" in p:
            scanner.ADX_THRESHOLD = p["adx_threshold"]

        # Store FGI/funding rate toggle for post-scan
        self._enable_fgi = p.get("enable_fgi", True)
        self._enable_funding_rate = p.get("enable_funding_rate", True)

    @Slot()
    def run(self):
        """Main entry point for the worker thread. Performs the scan."""
        try:
            self._apply_params()
            self._session = scanner._create_session()

            # Diagnostic: log scanner capabilities
            self.log_message.emit(f"[版本] Scanner v2.1, 已加载功能: {_SCANNER_FUNCTIONS}")
            self.log_message.emit(f"[版本] ATR={_SCANNER_HAS_ATR} ADX={_SCANNER_HAS_ADX} FGI={_SCANNER_HAS_FGI} Funding={_SCANNER_HAS_FUNDING}")

            if self._is_test:
                self._run_test_scan()
            elif self._source == "gateio":
                self._run_gateio_scan()
            elif self._source == "binance":
                self._run_binance_scan()
            elif self._source == "coingecko":
                self._run_coingecko_scan()
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.error_occurred.emit(f"扫描异常: {e}\n{tb}")
        finally:
            if self._session:
                try:
                    self._session.close()
                except Exception:
                    pass
            self.scan_complete.emit()

    def _detect(self, candles, symbol):
        """Dispatch to the correct detection function based on scan_mode."""
        if self._scan_mode == "trend":
            result = detect_uptrend(candles)
            if result:
                result["symbol"] = symbol
            return result
        else:
            return scanner.detect_box_range(symbol, candles)

    # ── Gate.io scan ──────────────────────────────────────────

    def _run_gateio_scan(self):
        self.status_update.emit("正在获取 Gate.io 交易对列表...")
        self.log_message.emit(f"[1/4] 获取交易对列表 (Gate.io, {scanner.KLINE_INTERVAL} K线)...")

        symbols = scanner.gateio_fetch_symbols(self._session)
        if self._stop_requested:
            return
        if not symbols:
            self.error_occurred.emit("无法获取 Gate.io 交易对列表，请检查网络连接。")
            return

        self.status_update.emit("正在获取24h成交量数据...")
        self.log_message.emit("[2/4] 获取24h成交量数据 (Gate.io)...")

        volumes = scanner.gateio_fetch_volumes(self._session)
        if self._stop_requested:
            return
        if not volumes:
            self.error_occurred.emit("无法获取成交量数据，请检查网络连接。")
            return

        candidates = [s for s in symbols if volumes.get(s, 0) >= scanner.MIN_VOLUME_USDT]
        self.log_message.emit(
            f"  成交量达标 (≥{scanner.MIN_VOLUME_USDT // 10000}万 USDT): {len(candidates)} 个"
        )

        self._scan_candidates_gateio(candidates)

    def _scan_candidates_gateio(self, candidates: List[str]):
        results = []
        total = len(candidates)
        errors = 0
        self.log_message.emit(f"[3/4] 开始扫描 {total} 个币种...")

        for i, symbol in enumerate(candidates):
            if self._stop_requested:
                self.log_message.emit(f"  扫描已停止，已发现 {len(results)} 个箱体")
                break

            # Fetch klines
            candles = scanner.gateio_fetch_klines(self._session, symbol)
            if candles is None:
                errors += 1
                time.sleep(scanner.REQUEST_DELAY)
                self.progress.emit(i + 1, total, symbol)
                continue

            # Detect box range
            display_name = scanner.gateio_get_display_name(symbol)
            result = self._detect(candles, display_name)
            if result is not None:
                results.append(result)
                self.result_found.emit(result)

            self.progress.emit(i + 1, total, display_name)

            # Log progress periodically
            if (i + 1) % 50 == 0 or i == total - 1:
                pct = (i + 1) / total * 100
                self.log_message.emit(
                    f"  [{i + 1}/{total}] {pct:.0f}%  |  已发现 {len(results)} 个箱体"
                )

            time.sleep(scanner.REQUEST_DELAY)

        results.sort(key=lambda r: r.get("confidence", r.get("score", 0)), reverse=True)

        # Apply post-scan enhancements (sentiment + funding rates)
        results = self._apply_post_scan_enhancements(results)

        meta = self._build_meta(len(candidates), len(candidates) - len(candidates), errors, len(results))
        self.log_message.emit(f"  扫描完成！发现 {len(results)} 个箱体震荡形态")
        self.finished.emit(results, meta)

    # ── Binance scan ──────────────────────────────────────────

    def _run_binance_scan(self):
        self.status_update.emit("正在获取 Binance 交易对列表...")
        self.log_message.emit("[1/4] 获取交易对列表 (Binance)...")

        symbols = scanner.binance_fetch_symbols(self._session)
        if self._stop_requested:
            return
        if not symbols:
            proxy_info = ""
            if not scanner.PROXY:
                proxy_info = (
                    "\n\n[HINT] Binance API 在国内无法直接访问，需要设置代理。\n"
                    "请在 设置 → 网络与过滤 → 代理地址 中填入代理，例如：\n"
                    "  http://127.0.0.1:7890  (Clash 默认)\n"
                    "  http://127.0.0.1:10809 (V2Ray 默认)\n\n"
                    "或者使用 Gate.io 数据源（国内可直接访问）。"
                )
            self.error_occurred.emit("无法获取 Binance 交易对列表，请检查网络连接。" + proxy_info)
            return

        self.status_update.emit("正在获取24h成交量数据...")
        self.log_message.emit("[2/4] 获取24h成交量数据 (Binance)...")

        volumes = scanner.binance_fetch_volumes(self._session)
        if self._stop_requested:
            return

        candidates = [s for s in symbols if volumes.get(s, 0) >= scanner.MIN_VOLUME_USDT]
        self.log_message.emit(
            f"  成交量达标 (≥{scanner.MIN_VOLUME_USDT // 10000}万 USDT): {len(candidates)} 个"
        )

        self._scan_candidates_binance(candidates)

    def _scan_candidates_binance(self, candidates: List[str]):
        results = []
        total = len(candidates)
        errors = 0
        self.log_message.emit(f"[3/4] 开始扫描 {total} 个币种...")

        for i, symbol in enumerate(candidates):
            if self._stop_requested:
                self.log_message.emit(f"  扫描已停止，已发现 {len(results)} 个箱体")
                break

            candles = scanner.binance_fetch_klines(self._session, symbol)
            if candles is None:
                errors += 1
                self.progress.emit(i + 1, total, symbol)
                time.sleep(scanner.REQUEST_DELAY)
                continue

            result = self._detect(candles, symbol)
            if result is not None:
                results.append(result)
                self.result_found.emit(result)

            self.progress.emit(i + 1, total, symbol)

            if (i + 1) % 50 == 0 or i == total - 1:
                pct = (i + 1) / total * 100
                self.log_message.emit(
                    f"  [{i + 1}/{total}] {pct:.0f}%  |  已发现 {len(results)} 个箱体"
                )

            time.sleep(scanner.REQUEST_DELAY)

        results.sort(key=lambda r: r.get("confidence", r.get("score", 0)), reverse=True)

        # Apply post-scan enhancements (sentiment + funding rates)
        results = self._apply_post_scan_enhancements(results)

        meta = self._build_meta(len(candidates), 0, errors, len(results))
        self.log_message.emit(f"  扫描完成！发现 {len(results)} 个箱体震荡形态")
        self.finished.emit(results, meta)

    # ── CoinGecko scan ────────────────────────────────────────

    def _run_coingecko_scan(self):
        self.status_update.emit("正在获取 CoinGecko 市场数据...")
        self.log_message.emit("[1/4] 获取市场数据 (CoinGecko)...")

        markets = scanner.coingecko_fetch_all_markets(self._session, max_pages=3)
        if self._stop_requested:
            return
        if not markets:
            self.error_occurred.emit("无法获取 CoinGecko 市场数据，请检查网络连接。")
            return

        candidates = []
        for sym, m in markets.items():
            vol = m.get("total_volume", 0) or 0
            if vol >= scanner.MIN_VOLUME_USDT:
                coin_id = m.get("id", "")
                if coin_id:
                    candidates.append((sym, coin_id, vol))

        self.log_message.emit(
            f"  成交量达标 (≥{scanner.MIN_VOLUME_USDT // 10000}万 USD): {len(candidates)} 个"
        )

        self._scan_candidates_coingecko(candidates)

    def _scan_candidates_coingecko(self, candidates):
        results = []
        total = len(candidates)
        errors = 0
        self.log_message.emit(f"[3/4] 开始扫描 {total} 个币种...")

        for i, (sym, coin_id, vol) in enumerate(candidates):
            if self._stop_requested:
                self.log_message.emit(f"  扫描已停止，已发现 {len(results)} 个箱体")
                break

            candles = scanner.coingecko_fetch_ohlc(self._session, coin_id, days=scanner.KLINE_LIMIT + 5)
            if candles is None:
                errors += 1
                self.progress.emit(i + 1, total, sym)
                time.sleep(1.2)
                continue

            result = scanner.detect_box_range(sym, candles)
            if result is not None:
                results.append(result)
                self.result_found.emit(result)

            self.progress.emit(i + 1, total, sym)

            if (i + 1) % 50 == 0 or i == total - 1:
                pct = (i + 1) / total * 100
                self.log_message.emit(
                    f"  [{i + 1}/{total}] {pct:.0f}%  |  已发现 {len(results)} 个箱体"
                )

            time.sleep(1.2)

        results.sort(key=lambda r: r.get("confidence", r.get("score", 0)), reverse=True)

        # Apply post-scan enhancements (sentiment + funding rates)
        results = self._apply_post_scan_enhancements(results)

        meta = self._build_meta(len(candidates), 0, errors, len(results))
        self.log_message.emit(f"  扫描完成！发现 {len(results)} 个箱体震荡形态")
        self.finished.emit(results, meta)

    # ── Test scan ─────────────────────────────────────────────

    def _run_test_scan(self):
        self.status_update.emit("正在运行测试扫描...")
        self.log_message.emit(f"[TEST] 测试模式：扫描主流币种 (数据源: {self._source})")

        results = []

        if self._source == "coingecko":
            test_coins = {
                "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
                "SOL": "solana", "XRP": "ripple", "ADA": "cardano",
                "DOGE": "dogecoin", "AVAX": "avalanche-2", "DOT": "polkadot",
                "LINK": "chainlink", "MATIC": "matic-network", "UNI": "uniswap",
                "ATOM": "cosmos", "LTC": "litecoin", "FIL": "filecoin",
                "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
                "NEAR": "near", "INJ": "injective-protocol",
            }
            total = len(test_coins)
            for i, (sym, coin_id) in enumerate(test_coins.items()):
                if self._stop_requested:
                    break
                self.progress.emit(i + 1, total, sym)
                candles = scanner.coingecko_fetch_ohlc(self._session, coin_id, days=scanner.KLINE_LIMIT + 5)
                if candles is None:
                    time.sleep(1.2)
                    continue
                result = scanner.detect_box_range(sym, candles)
                if result is not None:
                    results.append(result)
                    self.result_found.emit(result)
                time.sleep(1.2)

        elif self._source == "gateio":
            test_symbols = scanner.gateio_get_test_symbols()
            total = len(test_symbols)
            for i, symbol in enumerate(test_symbols):
                if self._stop_requested:
                    break
                self.progress.emit(i + 1, total, symbol)
                candles = scanner.gateio_fetch_klines(self._session, symbol)
                if candles is None:
                    time.sleep(scanner.REQUEST_DELAY)
                    continue
                display_name = scanner.gateio_get_display_name(symbol)
                result = scanner.detect_box_range(display_name, candles)
                if result is not None:
                    results.append(result)
                    self.result_found.emit(result)
                time.sleep(scanner.REQUEST_DELAY)

        else:  # binance
            test_binance = [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
                "MATICUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "FILUSDT",
                "APTUSDT", "ARBUSDT", "OPUSDT", "NEARUSDT", "INJUSDT",
            ]
            total = len(test_binance)
            for i, symbol in enumerate(test_binance):
                if self._stop_requested:
                    break
                self.progress.emit(i + 1, total, symbol)
                candles = scanner.binance_fetch_klines(self._session, symbol)
                if candles is None:
                    time.sleep(scanner.REQUEST_DELAY)
                    continue
                result = self._detect(candles, symbol)
                if result is not None:
                    results.append(result)
                    self.result_found.emit(result)
                time.sleep(scanner.REQUEST_DELAY)

        results.sort(key=lambda r: r.get("confidence", r.get("score", 0)), reverse=True)

        # Apply post-scan enhancements (sentiment + funding rates)
        results = self._apply_post_scan_enhancements(results)

        meta = self._build_meta(total, 0, 0, len(results))
        meta["data_source"] = f"{self._source.title()} (Test Mode)"
        self.log_message.emit(f"  测试完成！发现 {len(results)} 个箱体震荡形态")
        self.finished.emit(results, meta)

    # ── Helpers ───────────────────────────────────────────────

    def _apply_post_scan_enhancements(self, results: List[Dict]) -> List[Dict]:
        """Apply sentiment adjustment and funding rate risk to scan results.
        Works for both box range and trend mode results."""
        if not results:
            return results

        # 1. Fetch Fear & Greed Index and adjust confidence/score
        if getattr(self, "_enable_fgi", True):
            try:
                fgi_data = scanner.fetch_fear_greed_index()
                if fgi_data:
                    fgi_value = int(fgi_data.get("value", 50))
                    sentiment_adj = scanner.get_fgi_adjustment(fgi_value)

                    for r in results:
                        # Support both "confidence" (box mode) and "score" (trend mode)
                        original = r.get("confidence", r.get("score", 0))
                        r["confidence_original"] = original
                        r["fgi_value"] = fgi_value
                        r["fgi_classification"] = sentiment_adj["classification"]
                        r["fgi_suggestion"] = sentiment_adj["suggestion"]
                        adjusted = round(original * sentiment_adj["multiplier"])
                        adjusted = max(0, min(100, adjusted))
                        # Update whichever field the mode uses
                        if "confidence" in r:
                            r["confidence"] = adjusted
                        if "score" in r:
                            r["score"] = adjusted
                        r["sentiment_multiplier"] = sentiment_adj["multiplier"]

                    # Sort by appropriate field
                    sort_key = "confidence" if "confidence" in results[0] else "score"
                    results.sort(key=lambda r: r.get(sort_key, 0), reverse=True)
                    self.log_message.emit(
                        f"  [FGI] FGI={fgi_value} ({sentiment_adj['classification']}), "
                        f"x{sentiment_adj['multiplier']}"
                    )
                else:
                    self.log_message.emit("  [FGI] API返回空")
            except Exception as e:
                self.log_message.emit(f"  [FGI] 失败: {e}")

        # 2. Fetch funding rates and attach risk warnings
        if getattr(self, "_enable_funding_rate", True):
            try:
                funding_rates = scanner.fetch_funding_rates(
                    session=getattr(self, "_session", None),
                    source=self._source,
                )
                if funding_rates:
                    risk_count = 0
                    for r in results:
                        sym = r.get("symbol", "")
                        risk = scanner.check_funding_risk(sym, funding_rates)
                        r["funding_risk"] = risk
                        if risk.get("risk_level") in ("high", "extreme"):
                            risk_count += 1
                    self.log_message.emit(
                        f"  [费率] {len(funding_rates)}个, {risk_count}个有风险"
                    )
                else:
                    self.log_message.emit("  [费率] API返回空")
            except Exception as e:
                self.log_message.emit(f"  [费率] 失败: {e}")

        return results

    def _build_meta(
        self,
        total_found: int,
        filtered_by_volume: int,
        errors: int,
        filters_passed: int,
    ) -> Dict:
        return {
            "scan_time": datetime.now().isoformat(),
            "data_source": self._source.title(),
            "scan_mode": self._scan_mode,
            "total_pairs_found": total_found,
            "total_filtered_by_volume": filtered_by_volume,
            "total_errors": errors,
            "filters_passed": filters_passed,
            "parameters": {
                "kline_interval": scanner.KLINE_INTERVAL,
                "kline_limit": scanner.KLINE_LIMIT,
                "min_range_pct": scanner.MIN_RANGE_PCT,
                "max_range_pct": scanner.MAX_RANGE_PCT,
                "min_volume_usdt": scanner.MIN_VOLUME_USDT,
                "min_containment": scanner.MIN_CONTAINMENT,
                "max_normalized_slope": scanner.MAX_NORMALIZED_SLOPE,
                "min_touches": scanner.MIN_TOUCHES,
            },
        }
