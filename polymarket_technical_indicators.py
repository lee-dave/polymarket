#!/usr/bin/env python3
"""
Technical Indicators using real OHLCV from Coinbase via CCXT
Feeds TBO Trend and TBT Divergence strategies
"""

import ccxt
from typing import Dict, List, Optional
import statistics

class TechnicalIndicators:
    """Calculate real technical indicators from Coinbase OHLCV"""
    
    def __init__(self):
        self.exchange = ccxt.coinbase()
        self.pairs = {
            "BTC": "BTC/USD",
            "ETH": "ETH/USD",
            "SOL": "SOL/USD",
            "XRP": "XRP/USD"
        }
        self.ohlcv_cache = {}  # Cache OHLCV to avoid redundant calls
    
    def batch_fetch_ohlcv(self, symbols: list = None, timeframe: str = "6h", limit: int = 50) -> dict:
        """Fetch OHLCV for multiple symbols at once (more efficient than individual calls)"""
        if symbols is None:
            symbols = ["BTC", "ETH", "SOL", "XRP"]
        
        results = {}
        for symbol in symbols:
            results[symbol] = self.get_ohlcv(symbol, timeframe, limit)
        
        return results
    
    def get_ohlcv(self, symbol: str, timeframe: str = "6h", limit: int = 50) -> Optional[List]:
        """Fetch OHLCV candles from Coinbase"""
        try:
            pair = self.pairs.get(symbol, f"{symbol}/USD")
            # Coinbase supports: 1m, 5m, 15m, 30m, 1h, 2h, 6h, 1d
            # Use 6h which is closest to 4h
            candles = self.exchange.fetch_ohlcv(pair, timeframe="6h", limit=limit)
            return candles
        except Exception as e:
            print(f"❌ Error fetching {symbol}: {e}")
            return None
    
    def calculate_adx(self, candles: List) -> float:
        """Calculate ADX (Average Directional Index) - trend strength 0-100"""
        if not candles or len(candles) < 14:
            return 50  # Neutral
        
        # Extract high, low, close
        highs = [c[2] for c in candles]
        lows = [c[3] for c in candles]
        closes = [c[4] for c in candles]
        
        # Calculate True Range
        tr_list = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr_list.append(tr)
        
        # Calculate Directional Movements
        plus_dm = []
        minus_dm = []
        for i in range(1, len(highs)):
            up = highs[i] - highs[i-1]
            down = lows[i-1] - lows[i]
            
            if up > down and up > 0:
                plus_dm.append(up)
                minus_dm.append(0)
            elif down > up and down > 0:
                plus_dm.append(0)
                minus_dm.append(down)
            else:
                plus_dm.append(0)
                minus_dm.append(0)
        
        # Calculate 14-period averages
        atr = statistics.mean(tr_list[-14:])
        plus_di = (statistics.mean(plus_dm[-14:]) / atr * 100) if atr > 0 else 0
        minus_di = (statistics.mean(minus_dm[-14:]) / atr * 100) if atr > 0 else 0
        
        # Calculate ADX
        di_diff = abs(plus_di - minus_di)
        di_sum = plus_di + minus_di
        
        di_ratio = (di_diff / di_sum * 100) if di_sum > 0 else 0
        adx = min(100, di_ratio)
        
        return adx
    
    def calculate_rsi(self, candles: List, period: int = 14) -> float:
        """Calculate RSI (Relative Strength Index)"""
        if not candles or len(candles) < period:
            return 50  # Neutral
        
        closes = [c[4] for c in candles]
        
        # Calculate deltas
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        
        # Separate gains and losses
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        
        avg_gain = statistics.mean(gains[-period:]) if gains else 0
        avg_loss = statistics.mean(losses[-period:]) if losses else 0
        
        # Calculate RS
        rs = (avg_gain / avg_loss) if avg_loss > 0 else 0
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_macd(self, candles: List) -> Dict:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        if not candles or len(candles) < 26:
            return {"macd": 0, "signal": 0, "histogram": 0, "direction": "NEUTRAL"}
        
        closes = [c[4] for c in candles]
        
        # Calculate EMAs
        ema12 = self._calculate_ema(closes, 12)
        ema26 = self._calculate_ema(closes, 26)
        
        # MACD line
        macd = ema12 - ema26
        
        # Signal line (9-period EMA of MACD)
        macd_line = [self._calculate_ema(closes[:i+1], 12) - self._calculate_ema(closes[:i+1], 26) 
                     for i in range(len(closes))]
        signal = self._calculate_ema(macd_line[-9:], 9) if len(macd_line) >= 9 else macd
        
        # Histogram
        histogram = macd - signal
        
        return {
            "macd": round(macd, 8),
            "signal": round(signal, 8),
            "histogram": round(histogram, 8),
            "direction": "BULLISH" if histogram > 0 else "BEARISH"
        }
    
    def detect_rsi_divergence(self, candles: List) -> bool:
        """Detect RSI divergence (price lower but RSI higher = bullish)"""
        if not candles or len(candles) < 28:
            return False
        
        closes = [c[4] for c in candles]
        
        # Compare recent and older periods
        recent_close = closes[-1]
        older_close = closes[-14]
        
        recent_rsi = self.calculate_rsi(candles)
        older_rsi = self.calculate_rsi(candles[:-7])  # RSI 7 candles ago
        
        # Bullish divergence: price lower but RSI higher
        return recent_close < older_close and recent_rsi > older_rsi and recent_rsi < 40
    
    def detect_macd_divergence(self, candles: List) -> bool:
        """Detect MACD divergence"""
        if not candles or len(candles) < 30:
            return False
        
        closes = [c[4] for c in candles]
        
        recent_close = closes[-1]
        older_close = closes[-15]
        
        recent_macd = self.calculate_macd(candles)
        older_macd = self.calculate_macd(candles[:-7])
        
        # Bullish divergence: price lower but MACD higher
        return (recent_close < older_close and 
                recent_macd["macd"] > older_macd["macd"] and 
                recent_macd["direction"] == "BULLISH")
    
    def _calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculate single EMA value"""
        if not prices or len(prices) < period:
            return prices[-1] if prices else 0
        
        sma = statistics.mean(prices[-period:])
        multiplier = 2 / (period + 1)
        ema = prices[-1] * multiplier + sma * (1 - multiplier)
        
        return ema
    
    def get_tbo_signal(self, symbol: str) -> Optional[Dict]:
        """TBO Trend: ADX > 25 + price strong = BUY"""
        candles = self.get_ohlcv(symbol, timeframe="6h")
        if not candles:
            return None
        
        adx = self.calculate_adx(candles)
        close = candles[-1][4]
        
        if adx > 25 and close > 0.45:
            return {
                "strategy": "TBO Trend",
                "symbol": symbol,
                "signal": "BUY",
                "adx": round(adx, 2),
                "confidence": min(adx / 100, 0.95)
            }
        
        return None
    
    def get_tbt_signal(self, symbol: str) -> Optional[Dict]:
        """TBT Divergence: RSI or MACD divergence = BUY"""
        candles = self.get_ohlcv(symbol, timeframe="6h")
        if not candles:
            return None
        
        rsi_div = self.detect_rsi_divergence(candles)
        macd_div = self.detect_macd_divergence(candles)
        
        if rsi_div or macd_div:
            return {
                "strategy": "TBT Divergence",
                "symbol": symbol,
                "signal": "BUY",
                "rsi_divergence": rsi_div,
                "macd_divergence": macd_div,
                "confidence": 0.75 if rsi_div else 0.65
            }
        
        return None


if __name__ == "__main__":
    ti = TechnicalIndicators()
    
    # Test
    btc_candles = ti.get_ohlcv("BTC")
    if btc_candles:
        adx = ti.calculate_adx(btc_candles)
        rsi = ti.calculate_rsi(btc_candles)
        macd = ti.calculate_macd(btc_candles)
        
        print(f"BTC 6h Analysis:")
        print(f"  ADX: {adx:.2f}")
        print(f"  RSI: {rsi:.2f}")
        print(f"  MACD: {macd['direction']}")
