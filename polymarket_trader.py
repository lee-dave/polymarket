#!/usr/bin/env python3
"""
Polymarket Paper Trading Engine v2 - Advanced Multi-Strategy with Smart AI Contrarian v3
"""

import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import uuid
from math import sqrt
import subprocess
import sys

# Import smart contrarian
sys.path.insert(0, '/Users/claudbot')
try:
    from polymarket_contrarian_v3 import SmartContrarian
except ImportError:
    SmartContrarian = None

POLYMARKET_API = "https://gamma-api.polymarket.com"
TRADES_FILE = "/Users/claudbot/trades.json"
CIRCUIT_BREAKER_FILE = "/Users/claudbot/circuit_breaker_state.json"
MARKETS_FILE = "/Users/claudbot/polymarket_markets.json"
MARKET_HISTORY_FILE = "/Users/claudbot/market_history.json"

class PolymarketTraderV2:
    """Advanced trading engine with timing filters, dynamic sizing, arbitrage"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})
        self.session.timeout = 10
        
        # Dynamic position sizing based on win rate
        self.base_position_size = 10.00
        self.max_position_size = 100.00
        self.min_position_size = 5.00
        
        # Strategy 1: AI Contrarian
        self.contrarian_buy_threshold = 0.30
        self.contrarian_sell_threshold = 0.70
        
        # Strategy 2: Late Entry
        self.late_entry_buy_threshold = 0.35
        self.late_entry_sell_threshold = 0.65
        self.late_entry_min_confirmations = 2
        
        # Strategy 3: Arbitrage - Cross-market correlation and spread plays
        self.arbitrage_min_spread = 0.20  # Spreads > 0.20 are exploitable
        self.arbitrage_correlation_threshold = 0.85  # BTC/ETH correlation
        
        # Timing filters - Only trade during optimal windows
        self.optimal_windows = [
            (14, 16),   # 14:00-16:00 EST (peak volume, tight spreads)
            (22, 2)     # 22:00-02:00 EST (low liquidity, high edge 55-58%)
        ]
        self.avoid_hours = [6, 7]  # Avoid 06:00-07:00 (illiquid)
        
        # Market type filter - focus on 4-hour markets
        self.target_timeframes = ["4h", "4hour", "4-hour", "4H"]
        
        self.circuit_breaker_threshold = 3
        
        self.trades = self.load_trades()
        self.circuit_breaker_state = self.load_circuit_breaker()
        self.market_history = self.load_market_history()
        self.win_rate = self.calculate_win_rate()
        
        # Smart AI Contrarian v3
        self.contrarian = SmartContrarian() if SmartContrarian else None
        self.correlation_data = {}
    
    def calculate_win_rate(self) -> float:
        """Calculate current win rate for position sizing"""
        closed = [t for t in self.trades if t.get("status") == "CLOSED"]
        if not closed:
            return 0.5
        wins = sum(1 for t in closed if t.get("pnl", 0) > 0)
        return wins / len(closed) if closed else 0.5
    
    def calculate_position_size(self, strategy: str) -> float:
        """Scale position size based on win rate (Kelly Criterion simplified)"""
        # Base: 50% win rate = $10
        # 55% win rate = $50
        # 60% win rate = $100
        win_rate_bonus = (self.win_rate - 0.50) * 10
        size = self.base_position_size + (win_rate_bonus * self.base_position_size)
        return max(self.min_position_size, min(self.max_position_size, size))
    
    def is_trading_allowed(self) -> bool:
        """Check if current time is in optimal trading window"""
        now = datetime.now()
        hour = now.hour
        
        # Avoid illiquid hours
        if hour in self.avoid_hours:
            return False
        
        # Check if in optimal window
        for start, end in self.optimal_windows:
            if start < end:  # Normal range like 14-16
                if start <= hour < end:
                    return True
            else:  # Wrap around midnight like 22-02
                if hour >= start or hour < end:
                    return True
        
        return False
    
    def get_market_timeframe(self, market_question: str) -> Optional[str]:
        """Extract timeframe from market question"""
        question_lower = market_question.lower()
        for tf in self.target_timeframes:
            if tf in question_lower:
                return tf
        
        # Check for time-based keywords
        if "1 hour" in question_lower or "1h" in question_lower:
            return "1h"
        if "4 hour" in question_lower or "4h" in question_lower:
            return "4h"
        if "24 hour" in question_lower or "daily" in question_lower:
            return "daily"
        
        return None
    
    def load_trades(self) -> List[Dict]:
        """Load existing trades from file"""
        try:
            with open(TRADES_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                else:
                    return data.get("trades", [])
        except FileNotFoundError:
            return []
    
    def save_trades(self):
        """Save trades to file"""
        with open(TRADES_FILE, "w") as f:
            json.dump(self.trades, f, indent=2, default=str)
    
    def load_circuit_breaker(self) -> Dict:
        """Load circuit breaker state (per-strategy)"""
        try:
            with open(CIRCUIT_BREAKER_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "AI Contrarian": {"consecutive_losses": 0, "circuit_broken": False, "broken_until": None},
                "Late Entry": {"consecutive_losses": 0, "circuit_broken": False, "broken_until": None},
                "Arbitrage": {"consecutive_losses": 0, "circuit_broken": False, "broken_until": None}
            }
    
    def save_circuit_breaker(self):
        """Save circuit breaker state"""
        with open(CIRCUIT_BREAKER_FILE, "w") as f:
            json.dump(self.circuit_breaker_state, f, indent=2, default=str)
    
    def check_circuit_breaker_expired(self, strategy: str):
        """Check if circuit breaker has expired (24h)"""
        if strategy not in self.circuit_breaker_state:
            return False
        
        state = self.circuit_breaker_state[strategy]
        if not state.get("circuit_broken"):
            return False
        
        broken_until = state.get("broken_until")
        if not broken_until:
            return False
        
        try:
            broken_time = datetime.fromisoformat(broken_until)
            if datetime.now() > broken_time:
                # Reset circuit breaker
                state["consecutive_losses"] = 0
                state["circuit_broken"] = False
                state["broken_until"] = None
                self.save_circuit_breaker()
                return False
        except:
            pass
        
        return state.get("circuit_broken", False)
    
    def load_market_history(self) -> Dict:
        """Load market price history"""
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
        """Track price history for reversal confirmation"""
        if market_id not in self.market_history:
            self.market_history[market_id] = {"prices": [], "timestamps": []}
        
        self.market_history[market_id]["prices"].append(yes_price)
        self.market_history[market_id]["timestamps"].append(datetime.now().isoformat())
        
        # Keep last 10 prices
        if len(self.market_history[market_id]["prices"]) > 10:
            self.market_history[market_id]["prices"].pop(0)
            self.market_history[market_id]["timestamps"].pop(0)
        
        self.save_market_history()
    
    def check_circuit_breaker(self, strategy: str) -> bool:
        """Check if strategy is allowed to trade"""
        return not self.check_circuit_breaker_expired(strategy)
    
    def record_loss(self, strategy: str):
        """Record a loss for strategy"""
        if strategy not in self.circuit_breaker_state:
            self.circuit_breaker_state[strategy] = {
                "consecutive_losses": 0,
                "circuit_broken": False,
                "broken_until": None
            }
        
        state = self.circuit_breaker_state[strategy]
        state["consecutive_losses"] += 1
        
        if state["consecutive_losses"] >= self.circuit_breaker_threshold:
            state["circuit_broken"] = True
            # 24 hour lockout
            broken_until = datetime.now() + timedelta(hours=24)
            state["broken_until"] = broken_until.isoformat()
            
            # Alert user
            self.send_circuit_breaker_alert(strategy, state["consecutive_losses"])
        
        self.save_circuit_breaker()
    
    def send_circuit_breaker_alert(self, strategy: str, loss_count: int):
        """Send Telegram alert when circuit breaker triggers"""
        try:
            # Get strategy stats
            strat_trades = [t for t in self.trades if t.get("strategy") == strategy and t.get("status") == "CLOSED"]
            recent_losses = [t for t in strat_trades[-loss_count:] if t.get("pnl", 0) < 0]
            total_loss = sum(t.get("pnl", 0) for t in recent_losses)
            
            message = f"""
⛔ CIRCUIT BREAKER TRIGGERED

Strategy: {strategy}
Consecutive Losses: {loss_count}
Total Loss: ${total_loss:.2f}
Status: 🔴 LOCKED for 24 hours

Trading will resume automatically after 24 hours.
            """.strip()
            
            # Send via message tool to Telegram
            subprocess.run([
                "openclaw", "message",
                "--action", "send",
                "--channel", "telegram",
                "--to", "2119792198",
                "--message", message
            ], capture_output=True)
        except Exception as e:
            print(f"⚠️ Failed to send Telegram alert: {e}")
    
    def record_win(self, strategy: str):
        """Record a win for strategy - reset losses"""
        if strategy not in self.circuit_breaker_state:
            self.circuit_breaker_state[strategy] = {
                "consecutive_losses": 0,
                "circuit_broken": False,
                "broken_until": None
            }
        
        state = self.circuit_breaker_state[strategy]
        state["consecutive_losses"] = 0
        state["circuit_broken"] = False
        state["broken_until"] = None
        
        self.save_circuit_breaker()
    
    def get_market_price(self, market_id: str) -> Optional[float]:
        """Fetch current YES price"""
        try:
            response = self.session.get(
                f"{POLYMARKET_API}/markets/{market_id}",
                timeout=10
            )
            response.raise_for_status()
            market = response.json()
            
            outcome_prices_str = market.get("outcomePrices", "[]")
            if isinstance(outcome_prices_str, str):
                outcome_prices = json.loads(outcome_prices_str)
            else:
                outcome_prices = outcome_prices_str
            
            if len(outcome_prices) > 0:
                return float(outcome_prices[0])
            return None
        except:
            return None
    
    def check_arbitrage_opportunity(self, market1: Dict, market2: Dict) -> Optional[Dict]:
        """Check for arbitrage between related markets (BTC/ETH correlation)"""
        m1_id = market1.get("market_id")
        m2_id = market2.get("market_id")
        
        m1_price = market1.get("yes_price")
        m2_price = market2.get("yes_price")
        
        if not m1_price or not m2_price:
            return None
        
        # Calculate spread
        spread = abs(m1_price - m2_price)
        
        # If spread > 0.20, there's an arbitrage opportunity
        if spread > self.arbitrage_min_spread:
            return {
                "market_1": m1_id,
                "market_2": m2_id,
                "spread": spread,
                "action": "ARBITRAGE",
                "long": m1_id if m1_price < m2_price else m2_id,
                "short": m2_id if m1_price < m2_price else m1_id,
                "entry_price": min(m1_price, m2_price),
                "exit_price": max(m1_price, m2_price),
                "expected_pnl": spread * 10  # Per $10 position
            }
        
        return None
    
    def find_buy_opportunities(self, markets: List[Dict]) -> Dict:
        """Find signals from all three strategies"""
        contrarian_ops = []
        late_entry_ops = []
        arbitrage_ops = []
        
        for market in markets:
            market_id = market.get("market_id")
            yes_price = market.get("yes_price")
            question = market.get("question", "")
            
            if yes_price is None:
                yes_price = self.get_market_price(market_id)
            
            if not yes_price:
                continue
            
            # Filter for 4-hour markets
            timeframe = self.get_market_timeframe(question)
            if timeframe not in ["4h", "4hour", "4-hour", "4H"]:
                continue
            
            self.update_market_history(market_id, yes_price)
            
            # Strategy 1: AI Contrarian v3 - Smart panic detection
            if self.contrarian and market_id in self.market_history:
                price_hist = [
                    {"price": p, "timestamp": ts}
                    for p, ts in zip(
                        self.market_history[market_id]["prices"],
                        self.market_history[market_id]["timestamps"]
                    )
                ]
                
                panic_signal = self.contrarian.detect_crowd_panic(market_id, yes_price, 100, price_hist)
                
                if panic_signal:
                    contrarian_ops.append({
                        "market_id": market_id,
                        "question": question,
                        "yes_price": yes_price,
                        "strategy": "AI Contrarian",
                        "signal_strength": panic_signal["confidence"],
                        "timeframe": timeframe,
                        "panic_reason": panic_signal["reasoning"],
                        "volume_spike": panic_signal.get("volume_spike_ratio", 0)
                    })
            
            # Strategy 2: Late Entry (YES < 0.35 + reversal)
            if yes_price < self.late_entry_buy_threshold:
                if market_id in self.market_history and len(self.market_history[market_id]["prices"]) >= 2:
                    prices = self.market_history[market_id]["prices"]
                    is_reversing = all(prices[i] <= prices[i+1] for i in range(-2, 0))
                    
                    if is_reversing:
                        late_entry_ops.append({
                            "market_id": market_id,
                            "question": question,
                            "yes_price": yes_price,
                            "strategy": "Late Entry",
                            "signal_strength": yes_price,
                            "timeframe": timeframe
                        })
        
        # Check for arbitrage (BTC vs ETH markets)
        for i, m1 in enumerate(markets):
            for m2 in markets[i+1:]:
                if "bitcoin" in m1.get("question", "").lower() and "ethereum" in m2.get("question", "").lower():
                    arb = self.check_arbitrage_opportunity(m1, m2)
                    if arb:
                        arbitrage_ops.append(arb)
        
        return {
            "contrarian": sorted(contrarian_ops, key=lambda x: x["signal_strength"], reverse=True),
            "late_entry": sorted(late_entry_ops, key=lambda x: x["signal_strength"]),
            "arbitrage": arbitrage_ops
        }
    
    def open_position(self, market_id: str, yes_price: float, question: str, strategy: str) -> Dict:
        """Open a position with dynamically sized"""
        position_size = self.calculate_position_size(strategy)
        
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
        """Close a position"""
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
                
                if profit < 0:
                    self.record_loss(strategy)
                else:
                    self.record_win(strategy)
                
                # Recalculate win rate for next cycle
                self.win_rate = self.calculate_win_rate()
                
                return trade
        
        return None
    
    def check_sell_signals(self):
        """Check for exits on all open positions"""
        for trade in self.trades:
            if trade.get("status") != "OPEN":
                continue
            
            market_id = trade.get("market_id")
            strategy = trade.get("strategy")
            yes_price = self.get_market_price(market_id)
            
            if not yes_price:
                continue
            
            sell_threshold = 0.70 if strategy == "AI Contrarian" else 0.65
            
            if yes_price > sell_threshold:
                self.close_position(trade.get("id"), yes_price)
    
    def run_trading_cycle(self):
        """Execute complete trading cycle"""
        print("\n" + "=" * 80)
        print("🤖 POLYMARKET ADVANCED TRADING CYCLE v2")
        print("=" * 80)
        
        # Check timing filter
        if not self.is_trading_allowed():
            now = datetime.now()
            print(f"\n⏰ Outside optimal trading window ({now.strftime('%H:%M')} EST)")
            print(f"   Next optimal: 14:00-16:00 or 22:00-02:00 EST")
            return
        
        # Check per-strategy circuit breakers
        breakers_active = []
        for strategy in ["AI Contrarian", "Late Entry", "Arbitrage"]:
            if self.check_circuit_breaker_expired(strategy):
                breakers_active.append(strategy)
        
        if breakers_active:
            print(f"\n⛔ Circuit breaker ON for: {', '.join(breakers_active)}")
            print(f"   Remaining strategies: {', '.join([s for s in ['AI Contrarian', 'Late Entry', 'Arbitrage'] if s not in breakers_active])}")
            if not [s for s in ['AI Contrarian', 'Late Entry', 'Arbitrage'] if s not in breakers_active]:
                return
        
        # Load markets
        try:
            with open(MARKETS_FILE, "r") as f:
                data = json.load(f)
                markets = data.get("markets", [])
        except FileNotFoundError:
            print("\n❌ No market data. Run polymarket_discovery.py first.")
            return
        
        # Find all opportunities
        all_ops = self.find_buy_opportunities(markets)
        contrarian_ops = all_ops["contrarian"]
        late_entry_ops = all_ops["late_entry"]
        arbitrage_ops = all_ops["arbitrage"]
        
        print(f"\n🔴 AI Contrarian: {len(contrarian_ops)} signals (4-hour markets only)")
        print(f"🟡 Late Entry: {len(late_entry_ops)} confirmed (4-hour markets only)")
        print(f"💱 Arbitrage: {len(arbitrage_ops)} spread opportunities")
        print(f"💰 Current win rate: {self.win_rate:.1%} | Position size scaling: ${self.calculate_position_size('AI Contrarian'):.2f}")
        
        # Execute contrarian (max 1) - check circuit breaker
        if not self.check_circuit_breaker_expired("AI Contrarian"):
            for opp in contrarian_ops[:1]:
                has_position = any(
                    t.get("market_id") == opp["market_id"] and t.get("status") == "OPEN"
                    for t in self.trades
                )
                if not has_position:
                    pos = self.open_position(opp["market_id"], opp["yes_price"], opp["question"], opp["strategy"])
                    print(f"\n✅ Contrarian: ${pos['position_size']:.2f} @ ${opp['yes_price']:.2f}")
                    print(f"   Panic detected: {opp.get('panic_reason', 'N/A')}")
                    print(f"   Confidence: {opp.get('signal_strength', 0):.1%}")
        
        # Execute late entry (max 2) - check circuit breaker
        if not self.check_circuit_breaker_expired("Late Entry"):
            for opp in late_entry_ops[:2]:
                has_position = any(
                    t.get("market_id") == opp["market_id"] and t.get("status") == "OPEN"
                    for t in self.trades
                )
                if not has_position:
                    pos = self.open_position(opp["market_id"], opp["yes_price"], opp["question"], opp["strategy"])
                    print(f"✅ Late Entry: ${pos['position_size']:.2f} @ ${opp['yes_price']:.2f}")
        
        # Execute arbitrage (max 1) - check circuit breaker
        if not self.check_circuit_breaker_expired("Arbitrage"):
            for arb in arbitrage_ops[:1]:
                pos = self.open_position(arb["long"], arb["entry_price"], f"Arb: {arb['market_1']} vs {arb['market_2']}", "Arbitrage")
                print(f"✅ Arbitrage: ${pos['position_size']:.2f} | Spread: {arb['spread']:.2f}")
        
        # Check exits
        print(f"\n🔍 Checking {len([t for t in self.trades if t.get('status') == 'OPEN'])} open positions...")
        self.check_sell_signals()
        
        # Print stats
        open_trades = [t for t in self.trades if t.get("status") == "OPEN"]
        closed_trades = [t for t in self.trades if t.get("status") == "CLOSED"]
        
        if closed_trades:
            pnl = sum(t.get("pnl", 0) for t in closed_trades)
            wins = sum(1 for t in closed_trades if t.get("pnl", 0) > 0)
            print(f"\n📈 CLOSED: {len(closed_trades)} trades | P/L: ${pnl:.2f} | Win rate: {wins}/{len(closed_trades)}")
        
        print(f"⏳ OPEN: {len(open_trades)} positions")
        print("=" * 80)


if __name__ == "__main__":
    trader = PolymarketTraderV2()
    trader.run_trading_cycle()
    
    # Auto-commit trades to git
    import subprocess
    try:
        subprocess.run(["git", "-C", "/Users/claudbot", "add", "trades.json"], check=True)
        subprocess.run([
            "git", "-C", "/Users/claudbot", "commit", 
            "-m", f"[{datetime.now().strftime('%H:%M')}] Polymarket trades updated"
        ], check=False)  # Don't fail if nothing changed
        subprocess.run(["git", "-C", "/Users/claudbot", "push", "origin", "main"], check=True)
    except Exception as e:
        print(f"⚠️ Git sync failed: {e}")
