#!/usr/bin/env python3
"""
AI Contrarian v3 - Smart crowd panic detection
Detects sentiment shifts using volume spikes, price momentum, and capitulation patterns
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class SmartContrarian:
    """Detect real crowd panic, not just price thresholds"""
    
    def __init__(self):
        self.volume_baseline_file = "/Users/claudbot/volume_baselines.json"
        self.volume_baselines = self.load_baselines()
        
        # Panic detection thresholds
        self.volume_spike_threshold = 1.5  # 150% above baseline = panic
        self.price_drop_threshold = 0.15  # 15% drop = confirmed panic
        self.capitulation_bounce_threshold = 0.05  # 5% bounce after panic = capitulation
        self.momentum_lookback_hours = 1  # Check last 1 hour for momentum
    
    def load_baselines(self) -> Dict:
        """Load 24h volume baseline"""
        try:
            with open(self.volume_baseline_file, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def save_baselines(self):
        """Save volume baselines"""
        with open(self.volume_baseline_file, "w") as f:
            json.dump(self.volume_baselines, f, indent=2, default=str)
    
    def detect_crowd_panic(self, market_id: str, yes_price: float, 
                          market_volume: float, price_history: List[Dict]) -> Optional[Dict]:
        """
        Detect crowd panic using multi-signal approach
        Returns panic signal if detected, None otherwise
        """
        
        if not price_history or len(price_history) < 5:
            return None
        
        # Signal 1: Volume spike (panic selling)
        baseline = self.volume_baselines.get(market_id, market_volume)
        volume_spike_ratio = market_volume / baseline if baseline > 0 else 1.0
        has_volume_spike = volume_spike_ratio > self.volume_spike_threshold
        
        # Signal 2: Price momentum (how fast did it drop)
        prices = [h["price"] for h in price_history[-10:]]
        if len(prices) < 2:
            return None
        
        price_change_pct = (prices[-1] - prices[0]) / prices[0] if prices[0] > 0 else 0
        has_sharp_drop = price_change_pct < -self.price_drop_threshold
        
        # Signal 3: Extreme yes price (far from fair value)
        is_extreme_low = yes_price < 0.25  # Very low = extreme panic
        
        # Signal 4: Order imbalance (more sells than buys - inferred from price drop + volume)
        has_order_imbalance = has_sharp_drop and has_volume_spike
        
        # Panic detection: need at least 2-3 signals
        panic_signals = sum([
            has_volume_spike,
            has_sharp_drop,
            is_extreme_low,
            has_order_imbalance
        ])
        
        if panic_signals >= 2:
            return {
                "market_id": market_id,
                "panic_detected": True,
                "yes_price": yes_price,
                "volume_spike_ratio": volume_spike_ratio,
                "price_drop_pct": price_change_pct * 100,
                "panic_signals": panic_signals,
                "confidence": min(panic_signals / 4.0, 1.0),  # 0-1 confidence
                "reasoning": self._generate_reasoning(
                    has_volume_spike, has_sharp_drop, is_extreme_low, has_order_imbalance
                )
            }
        
        return None
    
    def detect_capitulation_bottom(self, market_id: str, price_history: List[Dict]) -> Optional[Dict]:
        """
        Detect capitulation bottom (reversal signal)
        When panic sellers give up and price starts recovering
        """
        
        if len(price_history) < 5:
            return None
        
        prices = [h["price"] for h in price_history[-10:]]
        timestamps = [h["timestamp"] for h in price_history[-10:]]
        
        # Find the lowest point in recent history
        min_price = min(prices)
        min_idx = prices.index(min_price)
        
        # Check if price bounced after the low
        if min_idx < len(prices) - 1:
            bounce = (prices[-1] - prices[min_idx]) / prices[min_idx]
            has_recovery = bounce > self.capitulation_bounce_threshold
            
            if has_recovery:
                return {
                    "market_id": market_id,
                    "capitulation_detected": True,
                    "lowest_price": min_price,
                    "current_price": prices[-1],
                    "recovery_pct": bounce * 100,
                    "strength": "WEAK" if bounce < 0.10 else ("MEDIUM" if bounce < 0.20 else "STRONG"),
                    "entry_signal": "BUY_BOUNCE"
                }
        
        return None
    
    def _generate_reasoning(self, volume_spike: bool, price_drop: bool, 
                           extreme_low: bool, order_imbalance: bool) -> str:
        """Generate human-readable panic reason"""
        reasons = []
        if volume_spike:
            reasons.append("volume spike (panic selling)")
        if price_drop:
            reasons.append("sharp price drop")
        if extreme_low:
            reasons.append("extreme low price")
        if order_imbalance:
            reasons.append("order imbalance")
        
        return " + ".join(reasons)
    
    def calculate_entry_price(self, market_id: str, yes_price: float, 
                             panic_confidence: float) -> float:
        """
        Calculate optimal entry price
        More confident panic = buy at lower price
        """
        # Conservative: wait for 3-5% bounce
        if panic_confidence < 0.5:
            return yes_price + (yes_price * 0.05)
        # Moderate: wait for 2-3% bounce
        elif panic_confidence < 0.75:
            return yes_price + (yes_price * 0.03)
        # Aggressive: buy near the bottom
        else:
            return yes_price + (yes_price * 0.01)


if __name__ == "__main__":
    contrarian = SmartContrarian()
    print("AI Contrarian v3 loaded. Monitoring for crowd panic patterns.")
