import time
import requests
import pandas as pd
from datetime import datetime
from collections import deque

# 🔧 CONFIGURATION (EDIT THESE!)
BOT_TOKEN = "8087555275:AAEn-ECydLhkVz2asdusbHpdwnsTI9p6Sd8"
CHAT_ID = "5904047020"
MIN_VOLUME = 100_000_000  # Lowered to $100M minimum 24h volume
TIMEZONE = "UTC+3"        
SCAN_INTERVAL = 900        # 15 minutes between scans

MAX_COINS_PER_SCAN = 50       
REQUEST_DELAY = 6.1          
MAX_RETRIES = 3               

stablecoins = {
    'usdt', 'usdc', 'dai', 'busd', 'tusd', 'usdp', 'usdd', 'gusd', 'lusd', 'susd', 
    'eurt', 'usdn', 'mim', 'fei', 'alusd', 'husd', 'cusd', 'vust', 'xaut', 'vai', 'binance usd'
}

def send_alert(message):
    for attempt in range(3):
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    'chat_id': CHAT_ID,
                    'text': message,
                    'parse_mode': 'Markdown',
                    'disable_notification': True
                },
                timeout=5
            )
            return True
        except Exception as e:
            if attempt == 2:
                print(f"💢 Telegram failed after 3 attempts: {e}")
            time.sleep(5)
    return False

def get_top_coins():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 150,
        "page": 1
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()

def get_15m_ohlc(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc?vs_currency=usd&days=0.0104167"
    for attempt in range(MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return [x[4] for x in response.json()]
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait = (attempt + 1) * 30
                print(f"⏳ Rate limited. Waiting {wait}s (attempt {attempt + 1})")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            print(f"⚠️ OHLC failed for {coin_id}: {str(e)[:80]}")
            return []
    return []

def calculate_rsi(prices, period=14):
    series = pd.Series(prices)
    delta = series.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

def check_cross(prices):
    if len(prices) < 50:
        return False

    try:
        ema25 = pd.Series(prices).ewm(span=25, adjust=False).mean().iloc[-1]
        ssma50 = pd.Series(prices).rolling(50).mean().ewm(alpha=1/50, adjust=False).mean().iloc[-1]
        return ema25 > ssma50
    except Exception as e:
        print(f"⚠️ Calculation error: {e}")
        return False

def filter_and_group_coins():
    top_coins = get_top_coins()
    filtered = []

    for coin in top_coins:
        if coin["symbol"].lower() in stablecoins:
            continue
        if coin["total_volume"] > MIN_VOLUME:
            print(f"[{datetime.now()}] {coin['symbol'].upper()} passed volume filter (${coin['total_volume']:,.0f})")
            filtered.append(coin)

    group_size = max(10, len(filtered) // 3)
    scan_groups = [filtered[i:i + group_size] for i in range(0, len(filtered), group_size)]
    return scan_groups

def scan_coin_batch(coins):
    alerts_sent = 0
    for coin in coins:
        prices = get_15m_ohlc(coin['id'])
        if prices and check_cross(prices):
            rsi = calculate_rsi(prices)
            alert_msg = (
                f"🚨 *{coin['symbol'].upper()} 15m ALERT* ({TIMEZONE})\n"
                f"• Price: ${prices[-1]:,.2f}\n"
                f"• RSI: {rsi:.1f} 📉\n"
                f"• Volume: ${coin['total_volume']/1e6:.1f}M\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
            if send_alert(alert_msg):
                alerts_sent += 1
                time.sleep(1)
    return alerts_sent

def main():
    scan_groups = deque(filter_and_group_coins())
    current_group = 0

    while True:
        start_time = time.time()

        if not scan_groups:
            scan_groups = deque(filter_and_group_coins())
            print(f"🔄 New scan groups created")

        print(f"\n🔍 Scanning Group {current_group + 1} at {datetime.now().strftime('%H:%M:%S')}")
        alerts = scan_coin_batch(scan_groups[current_group])
        print(f"📢 Sent {alerts} alerts from this batch")

        current_group = (current_group + 1) % len(scan_groups)
        elapsed = time.time() - start_time
        sleep_time = max(0, SCAN_INTERVAL - elapsed)
        print(f"⏳ Next scan in {sleep_time:.1f}s (Group {current_group + 1})")
        time.sleep(sleep_time)

if __name__ == "__main__":
    send_alert(
        f"🤖 *Max Coverage Bot Activated*\n"
        f"• Strategy: Rotating groups\n"
        f"• Max coins: {MAX_COINS_PER_SCAN}\n"
        f"• Min Volume: >${MIN_VOLUME/1e6:.0f}M\n"
        f"• 15m scans\n"
        f"• Timezone: {TIMEZONE}"
    )

    try:
        main()
    except KeyboardInterrupt:
        send_alert("🛑 Bot manually stopped")
    except Exception as e:
        send_alert(f"💢 Critical error: {str(e)[:200]}")
