#!/usr/bin/env python3
"""
Altrady DCA Monitoring - Alert when prices hit support levels for adding more positions
"""

import ccxt
import json
from datetime import datetime

MONITOR_FILE = "/Users/claudbot/altrady_dca_state.json"

# Positions to monitor
POSITIONS = {
    "APT/USDC": {
        "entry": 1.28,
        "current": 0.86,
        "position_size_usdc": 203612.45,  # From your screenshot
        "dca_levels": [0.75, 0.60, 0.45, 0.30]  # DCA support levels (lowest first to highest)
    },
    "SNX/USDC": {
        "entry": 0.461,
        "current": 0.345,
        "position_size_usdc": 100012.50,  # From your screenshot
        "dca_levels": [0.300, 0.250, 0.200, 0.150]  # DCA support levels below current price
    }
}

def get_current_prices():
    """Fetch current prices from Coinbase"""
    exchange = ccxt.coinbase()
    prices = {}
    
    for pair in POSITIONS.keys():
        try:
            ticker = exchange.fetch_ticker(pair)
            prices[pair] = ticker['last']
        except Exception as e:
            print(f"Error fetching {pair}: {e}")
            prices[pair] = POSITIONS[pair]['current']  # Use cached value on error
    
    return prices

def calculate_alerts(current_prices):
    """Generate alerts for DCA levels hit"""
    alerts = []
    
    for pair, data in POSITIONS.items():
        current = current_prices.get(pair, data['current'])
        entry = data['entry']
        dca_levels = data['dca_levels']
        
        current_loss = ((current - entry) / entry) * 100
        
        # Check each DCA level
        for i, level in enumerate(dca_levels):
            if current <= level:
                alert = {
                    "pair": pair,
                    "current_price": current,
                    "entry_price": entry,
                    "current_loss": current_loss,
                    "dca_level": i + 1,
                    "dca_price": level,
                    "recommendation": f"Consider adding {i+1} position(s) here"
                }
                alerts.append(alert)
                break  # Only report the first level hit
    
    return alerts

def load_state():
    """Load last alert state to avoid duplicate messages"""
    try:
        with open(MONITOR_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"last_alerts": {}}

def save_state(alerts_sent):
    """Save which alerts have already been sent"""
    with open(MONITOR_FILE, "w") as f:
        json.dump({
            "last_alerts": alerts_sent,
            "last_check": datetime.now().isoformat()
        }, f)

def format_alert(alert):
    """Format alert for Telegram/Discord"""
    return f"""
🚨 DCA ALERT - {alert['pair']}

Current Price: ${alert['current_price']:.4f}
Entry Price: ${alert['entry_price']:.4f}
Current Loss: {alert['current_loss']:.2f}%

DCA Level {alert['dca_level']}: ${alert['dca_price']:.4f}
Status: ✅ PRICE HIT - Time to add position

{alert['recommendation']}
"""

def run_monitor():
    """Run the monitoring cycle"""
    print(f"\n⏰ DCA Monitor Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Get current prices
    prices = get_current_prices()
    
    print("Current Prices:")
    for pair, price in prices.items():
        entry = POSITIONS[pair]['entry']
        loss = ((price - entry) / entry) * 100
        print(f"  {pair}: ${price:.4f} (Entry: ${entry:.4f}, Loss: {loss:.2f}%)")
    
    # Check for alerts
    alerts = calculate_alerts(prices)
    
    if alerts:
        print(f"\n🚨 {len(alerts)} DCA LEVEL(S) HIT!")
        
        state = load_state()
        last_alerts = state.get("last_alerts", {})
        
        for alert in alerts:
            pair = alert['pair']
            level = alert['dca_level']
            
            # Check if we already alerted for this level
            key = f"{pair}_{level}"
            if key not in last_alerts or last_alerts[key] != alert['dca_price']:
                print(format_alert(alert))
                # Would send Telegram/Discord here
                last_alerts[key] = alert['dca_price']
        
        save_state(last_alerts)
    else:
        print("✅ No DCA levels hit yet. Waiting for price drops...")
        print(f"\nNext DCA Targets:")
        for pair, data in POSITIONS.items():
            current = prices[pair]
            next_level = None
            for level in data['dca_levels']:
                if current > level:
                    next_level = level
                    break
            
            if next_level:
                distance = ((next_level - current) / current) * 100
                print(f"  {pair}: ${next_level:.4f} ({distance:.2f}% down)")

if __name__ == "__main__":
    run_monitor()
