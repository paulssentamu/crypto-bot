import time
import requests
import pandas as pd
from datetime import datetime, timedelta

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

def build_alert_message(symbol, price, rsi, volume, now):
    """Build the alert message with proper line breaks."""
    lines = [
        f"🚨 *{symbol} 15m Signal*",
        f"• Price: ${price:,.3f}",
        f"• RSI: {rsi:.2f} 📊",
        f"• Volume: ${volume/1e6:.1f}M",
        f"⏰ {now.strftime('%H:%M:%S')} (UTC+{TIMEZONE_OFFSET})"
    ]
    return "\n".join(lines)

def build_start_message():
    """Build the startup message."""
    lines = [
        "🤖 *Binance Scanner Started*",
        f"• Top: {TOP_SYMBOLS} pairs",
        f"• Volume > ${MIN_VOLUME/1e6:.0f}M",
        f"• Scan: 15m interval",
        f"• TZ: UTC+{TIMEZONE_OFFSET}"
    ]
    return "\n".join(lines)

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
        msg = build_alert_message(symbol, price, rsi, volume, now)
        
        if send_alert(msg):
            alerts += 1
            time.sleep(1)  # Rate limiting
    return alerts

def main():
    """Main bot loop."""
    send_alert(build_start_message())

    while True:
        print(f"[{datetime.now()}] Scanning...")
        alerts = scan_and_alert()
        print(f"Alerts sent: {alerts}")
        time.sleep(SCAN_INTERVAL)

# [Rest of your existing functions: get_symbols, get_ohlc, calculate_rsi, check_cross]
