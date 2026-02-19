#!/usr/bin/env python3
"""
Polymarket Trader v4 - Multi-Strategy with Capital Management & Scaling
Strategies: AI Contrarian, Late Entry, TBO Trend, TBT Divergence, Execution Confidence
"""

import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import uuid
import subprocess
import sys

sys.path.insert(0, '/Users/claudbot')
try:
    from polymarket_contrarian_v3 import SmartContrarian
except ImportError:
    SmartContrarian = None

try:
    from polymarket_technical_indicators import TechnicalIndicators
except ImportError:
    TechnicalIndicators = None

POLYMARKET_API = "https://gamma-api.polymarket.com"
TRADES_FILE = "/Users/claudbot/trades.json"
CIRCUIT_BREAKER_FILE = "/Users/claudbot/circuit_breaker_state.json"
MARKETS_FILE = "/Users/claudbot/polymarket_markets.json"
MARKET_HISTORY_FILE = "/Users/claudbot/market_history.json"
CAPITAL_FILE = "/Users/claudbot/capital_state.json"

class PolymarketTraderV4:
    """Multi-strategy trader with intelligent capital management"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.session.timeout = 10
        
        # Strategy starting capital: $100 each
        self.initial_capital = {
            "AI Contrarian": 100.00,
            "Late Entry": 100.00,
            "TBO Trend": 100.00,
            "TBT Divergence": 100.00,
            "Execution Confidence": 100.00
        }
        
        # Scaling parameters
        self.min_position = 5.00
        self.max_position = 500.00
        self.risk_per_trade = 0.05  # 5% of strategy capital
        self.profit_threshold_scale_up = 10  # Scale up after 10 wins
        self.loss_threshold_scale_down = 3   # Scale down after 3 losses
        
        # Technical thresholds
        self.adx_trend_threshold = 25  # ADX > 25 = strong trend
        self.rsi_divergence_threshold = 30  # RSI < 30 = oversold divergence
        
        self.trades = self.load_trades()
        self.capital_state = self.load_capital_state()
        self.circuit_breaker_state = self.load_circuit_breaker()
        self.market_history = self.load_market_history()
        self.contrarian = SmartContrarian() if SmartContrarian else None
        self.indicators = TechnicalIndicators() if TechnicalIndicators else None
    
    def load_trades(self) -> List[Dict]:
        """Load trades"""
        try:
            with open(TRADES_FILE, "r") as f:
                data = json.load(f)
                return data if isinstance(data, list) else data.get("trades", [])
        except FileNotFoundError:
            return []
    
    def save_trades(self):
        """Save trades"""
        with open(TRADES_FILE, "w") as f:
            json.dump(self.trades, f, indent=2, default=str)
    
    def load_capital_state(self) -> Dict:
        """Load capital state for each strategy"""
        try:
            with open(CAPITAL_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                strategy: {
                    "initial": self.initial_capital[strategy],
                    "current": self.initial_capital[strategy],
                    "cumulative_pnl": 0.0,
                    "consecutive_wins": 0,
                    "consecutive_losses": 0
                }
                for strategy in self.initial_capital
            }
    
    def save_capital_state(self):
        """Save capital state"""
        with open(CAPITAL_FILE, "w") as f:
            json.dump(self.capital_state, f, indent=2, default=str)
    
    def get_position_size(self, strategy: str) -> float:
        """Calculate position size based on capital and scaling rules"""
        state = self.capital_state.get(strategy, {})
        current_capital = state.get("current", self.initial_capital.get(strategy, 100))
        
        # Base: 5% of strategy capital
        base_size = current_capital * self.risk_per_trade
        
        # Scale up if winning
        if state.get("consecutive_wins", 0) >= self.profit_threshold_scale_up:
            base_size *= 1.5  # 1.5x position on winning streak
        
        # Scale down if losing
        if state.get("consecutive_losses", 0) >= self.loss_threshold_scale_down:
            base_size *= 0.5  # 0.5x position after losses
        
        return max(self.min_position, min(self.max_position, base_size))
    
    def load_circuit_breaker(self) -> Dict:
        """Load circuit breaker (per-strategy, 24h reset)"""
        try:
            with open(CIRCUIT_BREAKER_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                strategy: {"consecutive_losses": 0, "circuit_broken": False, "broken_until": None}
                for strategy in self.initial_capital
            }
    
    def save_circuit_breaker(self):
        """Save circuit breaker"""
        with open(CIRCUIT_BREAKER_FILE, "w") as f:
            json.dump(self.circuit_breaker_state, f, indent=2, default=str)
    
    def check_circuit_breaker_expired(self, strategy: str) -> bool:
        """Check if CB expired (24h auto-reset)"""
        if strategy not in self.circuit_breaker_state:
            self.circuit_breaker_state[strategy] = {"consecutive_losses": 0, "circuit_broken": False, "broken_until": None}
        
        state = self.circuit_breaker_state[strategy]
        
        if not state.get("circuit_broken"):
            return False
        
        try:
            broken_time = datetime.fromisoformat(state.get("broken_until", ""))
            if datetime.now() > broken_time:
                state["consecutive_losses"] = 0
                state["circuit_broken"] = False
                state["broken_until"] = None
                self.save_circuit_breaker()
                return False
        except:
            pass
        
        return state.get("circuit_broken", False)
    
    def load_market_history(self) -> Dict:
        """Load market history"""
        try:
            with open(MARKET_HISTORY_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_market_history(self):
        """Save market history"""
        with open(MARKET_HISTORY_FILE, "w") as f:
            json.dump(self.market_history, f, indent=2, default=str)
    
    def update_market_history(self, market_id: str, yes_price: float):
        """Track price history"""
        if market_id not in self.market_history:
            self.market_history[market_id] = {"prices": [], "timestamps": []}
        
        self.market_history[market_id]["prices"].append(yes_price)
        self.market_history[market_id]["timestamps"].append(datetime.now().isoformat())
        
        if len(self.market_history[market_id]["prices"]) > 20:
            self.market_history[market_id]["prices"].pop(0)
            self.market_history[market_id]["timestamps"].pop(0)
        
        self.save_market_history()
    
    def get_market_price(self, market_id: str) -> Optional[float]:
        """Fetch YES price"""
        try:
            response = self.session.get(f"{POLYMARKET_API}/markets/{market_id}", timeout=10)
            response.raise_for_status()
            market = response.json()
            outcome_prices_str = market.get("outcomePrices", "[]")
            outcome_prices = json.loads(outcome_prices_str) if isinstance(outcome_prices_str, str) else outcome_prices_str
            return float(outcome_prices[0]) if outcome_prices else None
        except:
            return None
    
    def open_position(self, market_id: str, yes_price: float, strategy: str, question: str) -> Dict:
        """Open a position"""
        position_size = self.get_position_size(strategy)
        
        position = {
            "id": str(uuid.uuid4())[:8],
            "market_id": market_id,
            "question": question,
            "strategy": strategy,
            "entry_price": yes_price,
            "entry_time": datetime.now().isoformat(),
            "position_size": position_size,
            "exit_price": None,
            "exit_time": None,
            "pnl": None,
            "status": "OPEN"
        }
        
        self.trades.append(position)
        self.save_trades()
        return position
    
    def close_position(self, trade_id: str, exit_price: float) -> Optional[Dict]:
        """Close a position and update capital"""
        for trade in self.trades:
            if trade.get("id") == trade_id and trade.get("status") == "OPEN":
                entry = trade["entry_price"]
                size = trade["position_size"]
                profit = (exit_price - entry) * (size / entry)
                strategy = trade.get("strategy", "Unknown")
                
                trade["exit_price"] = exit_price
                trade["exit_time"] = datetime.now().isoformat()
                trade["pnl"] = profit
                trade["status"] = "CLOSED"
                
                self.save_trades()
                
                # Update capital
                state = self.capital_state.get(strategy, {})
                state["current"] = state.get("current", 100) + profit
                state["cumulative_pnl"] = state.get("cumulative_pnl", 0) + profit
                
                if profit < 0:
                    state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
                    state["consecutive_wins"] = 0
                    self.record_loss(strategy)
                else:
                    state["consecutive_wins"] = state.get("consecutive_wins", 0) + 1
                    state["consecutive_losses"] = 0
                    self.record_win(strategy)
                
                self.capital_state[strategy] = state
                self.save_capital_state()
                
                return trade
        
        return None
    
    def record_loss(self, strategy: str):
        """Record loss for circuit breaker"""
        if strategy not in self.circuit_breaker_state:
            self.circuit_breaker_state[strategy] = {"consecutive_losses": 0, "circuit_broken": False, "broken_until": None}
        
        state = self.circuit_breaker_state[strategy]
        state["consecutive_losses"] += 1
        
        if state["consecutive_losses"] >= 3:
            state["circuit_broken"] = True
            state["broken_until"] = (datetime.now() + timedelta(hours=24)).isoformat()
            self.send_circuit_breaker_alert(strategy, state["consecutive_losses"])
        
        self.save_circuit_breaker()
    
    def record_win(self, strategy: str):
        """Record win for circuit breaker"""
        if strategy not in self.circuit_breaker_state:
            self.circuit_breaker_state[strategy] = {"consecutive_losses": 0, "circuit_broken": False, "broken_until": None}
        
        state = self.circuit_breaker_state[strategy]
        state["consecutive_losses"] = 0
        state["circuit_broken"] = False
        state["broken_until"] = None
        
        self.save_circuit_breaker()
    
    def send_circuit_breaker_alert(self, strategy: str, loss_count: int):
        """Send Telegram alert"""
        try:
            strat_trades = [t for t in self.trades if t.get("strategy") == strategy and t.get("status") == "CLOSED"]
            recent_losses = [t for t in strat_trades[-loss_count:] if t.get("pnl", 0) < 0]
            total_loss = sum(t.get("pnl", 0) for t in recent_losses)
            
            message = f"""
⛔ CIRCUIT BREAKER TRIGGERED

Strategy: {strategy}
Consecutive Losses: {loss_count}
Total Loss: ${total_loss:.2f}
Status: 🔴 LOCKED for 24 hours
            """.strip()
            
            subprocess.run([
                "openclaw", "message",
                "--action", "send",
                "--channel", "telegram",
                "--to", "2119792198",
                "--message", message
            ], capture_output=True)
        except:
            pass
    
    def find_signals(self, markets: List[Dict]) -> Dict:
        """Find trading signals from all strategies"""
        signals = {
            "AI Contrarian": [],
            "Late Entry": [],
            "TBO Trend": [],
            "TBT Divergence": [],
            "Execution Confidence": []
        }
        
        for market in markets:
            market_id = market.get("market_id")
            yes_price = market.get("yes_price")
            question = market.get("question", "")
            
            if not yes_price:
                yes_price = self.get_market_price(market_id)
            
            if not yes_price or "4h" not in question.lower():
                continue
            
            self.update_market_history(market_id, yes_price)
            price_hist = self.market_history.get(market_id, {}).get("prices", [])
            
            # AI Contrarian v3 (panic detection)
            if self.contrarian and len(price_hist) > 5:
                panic = self.contrarian.detect_crowd_panic(market_id, yes_price, 100, 
                    [{"price": p, "timestamp": self.market_history[market_id]["timestamps"][i]} 
                     for i, p in enumerate(price_hist)])
                if panic:
                    signals["AI Contrarian"].append({
                        "market_id": market_id,
                        "yes_price": yes_price,
                        "confidence": panic["confidence"],
                        "reason": panic["reasoning"]
                    })
            
            # Late Entry (reversal confirmation)
            if yes_price < 0.35 and len(price_hist) >= 3:
                if all(price_hist[i] <= price_hist[i+1] for i in range(-3, -1)):
                    signals["Late Entry"].append({
                        "market_id": market_id,
                        "yes_price": yes_price,
                        "confidence": 0.75
                    })
            
            # TBO Trend - Real CCXT Coinbase OHLCV indicators
            if self.indicators and "BTC" in question.upper():
                tbo_sig = self.indicators.get_tbo_signal("BTC")
                if tbo_sig:
                    signals["TBO Trend"].append({
                        "market_id": market_id,
                        "yes_price": yes_price,
                        "confidence": tbo_sig["confidence"],
                        "adx": tbo_sig["adx"]
                    })
            elif self.indicators and "ETH" in question.upper():
                tbo_sig = self.indicators.get_tbo_signal("ETH")
                if tbo_sig:
                    signals["TBO Trend"].append({
                        "market_id": market_id,
                        "yes_price": yes_price,
                        "confidence": tbo_sig["confidence"],
                        "adx": tbo_sig["adx"]
                    })
            
            # TBT Divergence - Real CCXT Coinbase OHLCV indicators
            if self.indicators and "BTC" in question.upper():
                tbt_sig = self.indicators.get_tbt_signal("BTC")
                if tbt_sig:
                    signals["TBT Divergence"].append({
                        "market_id": market_id,
                        "yes_price": yes_price,
                        "confidence": tbt_sig["confidence"],
                        "rsi_div": tbt_sig["rsi_divergence"],
                        "macd_div": tbt_sig["macd_divergence"]
                    })
            elif self.indicators and "ETH" in question.upper():
                tbt_sig = self.indicators.get_tbt_signal("ETH")
                if tbt_sig:
                    signals["TBT Divergence"].append({
                        "market_id": market_id,
                        "yes_price": yes_price,
                        "confidence": tbt_sig["confidence"],
                        "rsi_div": tbt_sig["rsi_divergence"],
                        "macd_div": tbt_sig["macd_divergence"]
                    })
        
        return signals
    
    def run_trading_cycle(self):
        """Execute trading cycle"""
        print("\n" + "=" * 80)
        print("🤖 POLYMARKET TRADER v4 - MULTI-STRATEGY")
        print("=" * 80)
        
        try:
            with open(MARKETS_FILE, "r") as f:
                markets = json.load(f).get("markets", [])
        except:
            print("❌ No market data")
            return
        
        signals = self.find_signals(markets)
        
        for strategy, signal_list in signals.items():
            if not self.check_circuit_breaker_expired(strategy):
                continue
            
            if signal_list:
                pos_size = self.get_position_size(strategy)
                print(f"\n{strategy}: {len(signal_list)} signals | Capital: ${self.capital_state[strategy]['current']:.2f} | Position: ${pos_size:.2f}")


if __name__ == "__main__":
    trader = PolymarketTraderV4()
    trader.run_trading_cycle()
    
    # Auto-commit
    try:
        subprocess.run(["git", "-C", "/Users/claudbot", "add", "trades.json", "capital_state.json"], check=True)
        subprocess.run([
            "git", "-C", "/Users/claudbot", "commit",
            "-m", f"[{datetime.now().strftime('%H:%M')}] Polymarket v4 - multi-strategy update"
        ], check=False)
        subprocess.run(["git", "-C", "/Users/claudbot", "push", "origin", "main"], check=True)
    except Exception as e:
        print(f"⚠️ Git sync failed: {e}")
