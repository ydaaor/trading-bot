from alpaca_trade_api.rest import REST, TimeFrame
from datetime import datetime, timedelta
import pytz
import requests
import yfinance as yf
from textblob import TextBlob
import time

# הגדרות API בקוד
ALPACA_API_KEY = "PK0TSAQC81V13TEVDE4R"
ALPACA_SECRET_KEY = "pKxTEyKtLdrJnwWsGiKFF7UHhWwKdWVDyDi5tR3v"
BASE_URL = "https://paper-api.alpaca.markets"

api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL)

# פונקציית בדיקה לשעות פעילות שוק
def is_market_open_now():
    ny_time = datetime.now(pytz.timezone("America/New_York"))
    return ny_time.weekday() < 5 and ny_time.hour >= 9 and (ny_time.hour < 16 or (ny_time.hour == 16 and ny_time.minute == 0))

# טכני
def fetch_technical_indicators(symbol):
    data = yf.download(symbol, period="2mo", interval="1d")
    if data.empty or len(data) < 30:
        return None

    # RSI
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = data['Close'].ewm(span=12, adjust=False).mean()
    ema26 = data['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()

    # פריצה שבועית וחודשית
    recent_high_7 = data['High'][-7:].max()
    recent_high_30 = data['High'][-30:].max()
    current_price = data['Close'].iloc[-1]
    breakout_week = current_price > recent_high_7
    breakout_month = current_price > recent_high_30

    # מגמה: מחיר > ממוצע נע של 20 יום
    trend_up = current_price > data['Close'].rolling(window=20).mean().iloc[-1]

    return {
        'rsi': rsi.iloc[-1],
        'macd_cross': macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2],
        'breakout_week': breakout_week,
        'breakout_month': breakout_month,
        'trend_up': trend_up
    }

# רגשות
def analyze_sentiment(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
        r = requests.get(url)
        headlines = [item['title'] for item in r.json().get('news', []) if 'title' in item]
        sentiments = [TextBlob(title).sentiment.polarity for title in headlines]
        return sum(sentiments) / len(sentiments) if sentiments else 0
    except:
        return 0

# קנייה/מכירה
def place_order(symbol, qty, action):
    try:
        api.submit_order(
            symbol=symbol,
            qty=qty,
            side=action,
            type='market',
            time_in_force='gtc'
        )
        print(f"✅ Placed {action} order for {qty} shares of {symbol}")
    except Exception as e:
        print(f"⛔ Error placing {action} order for {symbol}: {e}")

# הסורק הראשי
def run_scan():
    if not is_market_open_now():
        print("⏰ Market is closed, skipping scan...")
        return

    print(f"\U0001F50D Running scan at {datetime.now()}")
    try:
        assets = api.list_assets(status='active')
        assets = [a for a in assets if a.tradable and a.exchange in ['NASDAQ', 'NYSE']]  # ✅ בורסות אמריקאיות
        selected = []

        for asset in assets[:150]:  # כדי להאיץ, אפשר לעלות/להוריד מספר
            symbol = asset.symbol
            try:
                info = yf.Ticker(symbol).info
                market_cap = info.get('marketCap', 0)
                avg_volume = info.get('averageVolume', 0)
                price = info.get('regularMarketPrice', 0)

                if not (300e6 <= market_cap <= 900e6):
                    continue
                if price < 5 or price > 150:
                    continue
                if avg_volume < 1_000_000:
                    continue

                tech = fetch_technical_indicators(symbol)
                if not tech or not tech['trend_up'] or not (tech['breakout_week'] or tech['breakout_month']):
                    continue

                sentiment = analyze_sentiment(symbol)
                if sentiment < 0.1:
                    continue

                if tech['rsi'] < 50:
                    place_order(symbol, 10, 'buy')
                    selected.append(symbol)
                    print(f"✅ BUY {symbol} | Price: {price:.2f} | RSI: {tech['rsi']:.2f}")
                elif tech['rsi'] > 60:
                    place_order(symbol, 10, 'sell')
                    selected.append(symbol)
                    print(f"✅ SELL {symbol} | Price: {price:.2f} | RSI: {tech['rsi']:.2f}")

            except Exception as e:
                print(f"⛔ Error with {symbol}: {e}")

        print(f"\nTotal selected: {len(selected)}")

    except Exception as e:
        print(f"ERROR: {e}")

# לולאה תמידית
def run_forever():
    while True:
        run_scan()
        print("\nWaiting 5 minutes...\n")
        time.sleep(300)

if __name__ == "__main__":
    run_forever()