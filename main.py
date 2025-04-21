import time
import requests
import pandas as pd
from datetime import datetime, timedelta

# CONFIG (with your actual credentials)
BOT_TOKEN = "8087555275:AAEn-ECydLhkVz2asdusbHpdwnsTI9p6Sd8"
CHAT_ID = "5904047020"
TIMEZONE_OFFSET = 3  # EAT (UTC+3)
SCAN_INTERVAL = 900  # 15 mins
MAX_RETRIES = 3
RETRY_DELAY = 5

STABLECOINS = {"USDT", "BUSD", "USDC", "DAI"}
MIN_VOLUME = 100_000_000  # $100M
TOP_SYMBOLS = 100

BINANCE_BASE = "https://api.binance.com"
HEADERS = {"Accept": "application/json"}

def send_alert(msg):
    """Enhanced Telegram alert with request timeout and retries"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_notification": True
    }
    for i in range(MAX_RETRIES):
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Telegram alert failed (attempt {i+1}): {str(e)}")
            time.sleep(RETRY_DELAY)
    return False

def get_symbols():
    """Fetch top symbols with volume validation"""
    try:
        url = f"{BINANCE_BASE}/api/v3/ticker/24hr"
        r = requests.get(url, timeout=15, headers=HEADERS)
        r.raise_for_status()
        
        valid_symbols = []
        for item in r.json():
            symbol = item['symbol']
            volume = float(item['quoteVolume'])
            
            # Strict validation
            if (symbol.endswith('USDT') and
                not any(symbol.startswith(coin) for coin in STABLECOINS) and
                volume >= MIN_VOLUME):
                valid_symbols.append({
                    'symbol': symbol,
                    'lastPrice': item['lastPrice'],
                    'quoteVolume': volume
                })
        
        # Sort by volume descending
        return sorted(valid_symbols, key=lambda x: -x['quoteVolume'])[:TOP_SYMBOLS]
    
    except Exception as e:
        print(f"🔴 Failed to fetch symbols: {str(e)}")
        return []

def get_ohlc(symbol):
    """Get OHLC data with strict validation"""
    params = {
        "symbol": symbol,
        "interval": "15m",
        "limit": 100  # Get enough data for reliable indicators
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(
                f"{BINANCE_BASE}/api/v3/klines",
                params=params,
                timeout=15,
                headers=HEADERS
            )
            r.raise_for_status()
            
            # Validate data structure
            if not isinstance(r.json(), list) or len(r.json()) < 50:
                raise ValueError("Insufficient data points")
                
            return [float(candle[4]) for candle in r.json()]  # Close prices
        
        except Exception as e:
            print(f"⚠️ Failed to get OHLC for {symbol} (attempt {attempt+1}): {str(e)}")
            time.sleep(RETRY_DELAY)
    
    return None

def calculate_indicators(prices):
    """Robust indicator calculation with validation"""
    if not prices or len(prices) < 50:
        return None, None
    
    try:
        series = pd.Series(prices)
        
        # EMA 25
        ema25 = series.ewm(
            span=25,
            adjust=False,
            min_periods=25
        ).mean().iloc[-1]
        
        # Smoothed SMA 50
        sma50 = series.rolling(
            window=50,
            min_periods=50
        ).mean()
        
        ssma50 = sma50.ewm(
            alpha=1/50,
            adjust=False,
            min_periods=50
        ).mean().iloc[-1]
        
        return ema25, ssma50
    
    except Exception as e:
        print(f"⚠️ Indicator calculation failed: {str(e)}")
        return None, None

def check_crossover(ema25, ssma50, prev_ema25, prev_ssma50):
    """Strict crossover confirmation"""
    return (
        ema25 is not None and
        ssma50 is not None and
        prev_ema25 is not None and
        prev_ssma50 is not None and
        prev_ema25 <= prev_ssma50 and  # Was below or equal
        ema25 > ssma50  # Now above
    )

def scan_and_alert():
    """Main scanning logic with enhanced validation"""
    symbols = get_symbols()
    if not symbols:
        print("🟠 No valid symbols found")
        return 0
    
    alerts_sent = 0
    for symbol_data in symbols:
        symbol = symbol_data['symbol']
        price = float(symbol_data['lastPrice'])
        volume = float(symbol_data['quoteVolume'])
        
        prices = get_ohlc(symbol)
        if not prices or len(prices) < 50:
            continue
        
        # Get current and previous values
        ema25, ssma50 = calculate_indicators(prices)
        prev_ema25, prev_ssma50 = calculate_indicators(prices[:-1])  # Previous candle
        
        # Debug output
        print(f"\n🔎 {symbol}:")
        print(f"Price: ${price:,.2f}")
        print(f"EMA25: {ema25:.8f}" if ema25 else "EMA25: None")
        print(f"SSMA50: {ssma50:.8f}" if ssma50 else "SSMA50: None")
        print(f"Prev EMA25: {prev_ema25:.8f}" if prev_ema25 else "Prev EMA25: None")
        print(f"Prev SSMA50: {prev_ssma50:.8f}" if prev_ssma50 else "Prev SSMA50: None")
        
        if check_crossover(ema25, ssma50, prev_ema25, prev_ssma50):
            now = datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)
            rsi = calculate_rsi(prices[-100:])  # Last 100 periods
            
            alert_msg = f"""🚨 *{symbol} 15m Signal*
• Price: ${price:,.2f}
• RSI: {rsi:.2f} 📊
• Volume: ${volume/1e6:.1f}M
• EMA25: {ema25:.2f}
• SSMA50: {ssma50:.2f}
⏰ {now.strftime('%H:%M:%S')} (UTC+{TIMEZONE_OFFSET})"""
            
            if send_alert(alert_msg):
                alerts_sent += 1
                time.sleep(1)  # Rate limiting
    
    return alerts_sent

def calculate_rsi(prices, period=14):
    """More accurate RSI calculation"""
    if len(prices) < period:
        return None
    
    try:
        delta = pd.Series(prices).diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs)).iloc[-1]
    except Exception as e:
        print(f"⚠️ RSI calculation failed: {str(e)}")
        return None

def main():
    """Main execution with crash protection"""
    startup_msg = f"""🤖 *Binance Scanner Started*
• Monitoring top {TOP_SYMBOLS} pairs
• Minimum volume: ${MIN_VOLUME/1e6:.0f}M
• Timeframe: 15 minutes
• Timezone: UTC+{TIMEZONE_OFFSET}"""
    
    send_alert(startup_msg)
    
    while True:
        try:
            print(f"\n🔄 Scanning at {datetime.now().isoformat()}")
            alerts = scan_and_alert()
            print(f"✅ Scan complete. Alerts sent: {alerts}")
            
            time.sleep(SCAN_INTERVAL)
            
        except KeyboardInterrupt:
            send_alert("🛑 Bot manually stopped by user")
            print("\n🛑 Received keyboard interrupt. Stopping...")
            break
            
        except Exception as e:
            error_msg = f"💥 Critical error: {str(e)}"
            print(error_msg)
            send_alert(error_msg)
            time.sleep(60)  # Wait before retrying

if __name__ == '__main__':
    main()
