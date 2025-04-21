import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from collections import deque

# CONFIG
BOT_TOKEN = "8087555275:AAEn-ECydLhkVz2asdusbHpdwnsTI9p6Sd8"
CHAT_ID = "5904047020"
TIMEZONE_OFFSET = 3  # EAT (UTC+3)
SCAN_INTERVAL = 900  # 15 mins
MAX_RETRIES = 3
RETRY_DELAY = 5

STABLECOINS = {"USDT", "BUSD", "USDC", "DAI"}
MIN_VOLUME = 100_000_000
TOP_SYMBOLS = 100

BINANCE_BASE = "https://api.binance.com"
HEADERS = {"Accept": "application/json"}


def send_alert(msg):
    """Send alert via Telegram bot."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_notification": True
    }
    for i in range(MAX_RETRIES):
        try:
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code == 200:
                return True
        except Exception as e:
            print(f"Telegram error (attempt {i+1}): {e}")
        time.sleep(RETRY_DELAY)
    return False


def get_symbols():
    """Fetch top symbols by volume from Binance."""
    try:
        url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
        r = requests.get(url, timeout=10, headers=HEADERS)
        r.raise_for_status()
        data = r.json()
        filtered = [
            x for x in data 
            if x['symbol'].endswith('USDT')
            and not any(x['symbol'].startswith(st) for st in STABLECOINS)
            and float(x['quoteVolume']) > MIN_VOLUME
        ]
        return sorted(filtered, key=lambda x: -float(x['quoteVolume']))[:TOP_SYMBOLS]
    except Exception as e:
        print(f"Symbol fetch failed: {e}")
        return []


def get_ohlc(symbol):
    """Get OHLC data for a symbol."""
    url = f"{BINANCE_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": "15m", "limit": 100}
    for _ in range(MAX_RETRIES):
        try:
            r = requests.get(url, params=params, timeout=10, headers=HEADERS)
            r.raise_for_status()
            data = r.json()
            return [float(x[4]) for x in data]  # Close prices
        except Exception as e:
            print(f"OHLC fail {symbol}: {e}")
            time.sleep(RETRY_DELAY)
    return []


def calculate_rsi(prices, period=14):
    """Calculate RSI from price data."""
    if len(prices) < period:
        return None
    delta = pd.Series(prices).diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs)).iloc[-1]


def check_cross(prices):
    """Check EMA25 vs Smoothed SMA50 crossover."""
    if len(prices) < 50:
        return False
    prices_series = pd.Series(prices)
    ema25 = prices_series.ewm(span=25, adjust=False).mean().iloc[-1]
    ssma50 = prices_series.rolling(50).mean().ewm(alpha=1/50, adjust=False).mean().iloc[-1]
    return ema25 > ssma50


def scan_and_alert():
    """Scan symbols and send alerts for signals."""
    symbols = get_symbols()
    alerts = 0
    for symbol_data in symbols:
        symbol = symbol_data['symbol']
        price = float(symbol_data['lastPrice'])
        volume = float(symbol_data['quoteVolume'])

        prices = get_ohlc(symbol)
        if not prices or not check_cross(prices):
            continue

        rsi = calculate_rsi(prices)
        if rsi is None:
            continue

        now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
        msg = f"""🚨 *{symbol} 15m Signal*
• Price: ${price:,.3f}
• RSI: {rsi:.2f} 📊
• Volume: ${volume/1e6:.1f}M
⏰ {now.strftime('%H:%M:%S')} (UTC+{TIMEZONE_OFFSET})"""
        
        if send_alert(msg):
            alerts += 1
            time.sleep(1)  # Rate limiting
    return alerts


def main():
    """Main bot loop."""
    send_alert(f"""🤖 *Binance Scanner Started*
• Top: {TOP_SYMBOLS} pairs
• Volume > ${MIN_VOLUME/1e6:.0f}M
• Scan: 15m interval
• TZ: UTC+{TIMEZONE_OFFSET}""")

    while True:
        print(f"[{datetime.now()}] Scanning...")
        alerts = scan_and_alert()
        print(f"Alerts sent: {alerts}")
        time.sleep(SCAN_INTERVAL)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        send_alert("🛑 Bot manually stopped")
        print("Bot stopped by user")
    except Exception as e:
        send_alert(f"💥 Critical Error: {str(e)}")
        print(f"Error: {e}")
        raise
