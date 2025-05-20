from flask import Flask, render_template, jsonify, request
from datetime import datetime
from alpaca_trade_api.rest import REST
import yfinance as yf
import requests
from textblob import TextBlob
import time
import threading

# הגדרות API
ALPACA_API_KEY = "PK0TSAQC81V13TEVDE4R"
ALPACA_SECRET_KEY = "pKxTEyKtLdrJnwWsGiKFF7UHhWwKdWVDyDi5tR3v"
BASE_URL = "https://paper-api.alpaca.markets"
api = REST(ALPACA_API_KEY, ALPACA_SECRET_KEY, BASE_URL)

# יצירת אובייקט Flask
app = Flask(__name__)

# משתנים עבור נתונים שניתן להציג באפליקציה
scan_results = []

# פונקציות הרובוט (כפי שהגדרת קודם)

def fetch_technical_indicators(symbol):
    data = yf.download(symbol, period="1mo", interval="1d")
    if data.empty or len(data) < 26:
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

    latest_rsi = rsi.iloc[-1]
    macd_cross = macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]

    return {
        'rsi': latest_rsi,
        'macd_cross': macd_cross
    }

def analyze_sentiment(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={symbol}"
        r = requests.get(url)
        headlines = [item['title'] for item in r.json().get('news', []) if 'title' in item]
        sentiments = [TextBlob(title).sentiment.polarity for title in headlines]
        return sum(sentiments) / len(sentiments) if sentiments else 0
    except:
        return 0

def place_order(symbol, qty, action):
    try:
        if action == 'buy':
            api.submit_order(
                symbol=symbol,
                qty=qty,
                side='buy',
                type='market',
                time_in_force='gtc'
            )
            print(f"✅ Placed {action} order for {qty} shares of {symbol}")
        elif action == 'sell':
            api.submit_order(
                symbol=symbol,
                qty=qty,
                side='sell',
                type='market',
                time_in_force='gtc'
            )
            print(f"✅ Placed {action} order for {qty} shares of {symbol}")
    except Exception as e:
        print(f"⛔ Error placing {action} order for {symbol}: {e}")

def run_scan():
    print(f"\U0001F50D Running dynamic scan at {datetime.now()}")
    selected = []

    try:
        assets = api.list_assets(status='active')
        assets = [a for a in assets if a.tradable and a.easy_to_borrow]

        for asset in assets[:100]:
            symbol = asset.symbol
            try:
                info = yf.Ticker(symbol).info
                market_cap = info.get('marketCap', 0)
                avg_volume = info.get('averageVolume', 0)
                volume = info.get('volume', 0)

                if not (150e6 <= market_cap <= 2e9):
                    continue
                if volume < avg_volume * 0.7:
                    continue

                tech = fetch_technical_indicators(symbol)
                if not tech:
                    continue

                if tech['rsi'] < 50:
                    sentiment = analyze_sentiment(symbol)
                    if sentiment < 0.1:
                        continue
                    qty = 10
                    place_order(symbol, qty, 'buy')
                    selected.append(symbol)
                    print(f"✅ Selected for Buy: {symbol} | RSI: {tech['rsi']:.2f} | Sentiment: {sentiment:.2f}")
                elif tech['rsi'] > 60:
                    sentiment = analyze_sentiment(symbol)
                    if sentiment < 0.1:
                        continue
                    qty = 10
                    place_order(symbol, qty, 'sell')
                    selected.append(symbol)
                    print(f"✅ Selected for Sell: {symbol} | RSI: {tech['rsi']:.2f} | Sentiment: {sentiment:.2f}")

            except Exception as e:
                print(f"⛔ Error with {symbol}: {e}")

        return selected

    except Exception as e:
        print(f"ERROR: {e}")
        return []

def run_forever():
    while True:
        global scan_results
        scan_results = run_scan()
        time.sleep(300)

# Flask Routes

@app.route('/')
def home():
    return render_template('index.html', scan_results=scan_results)

@app.route('/start_scan')
def start_scan():
    threading.Thread(target=run_forever, daemon=True).start()
    return jsonify({"status": "Scan started!"})

@app.route('/stop_scan')
def stop_scan():
    global scan_results
    scan_results = []
    return jsonify({"status": "Scan stopped!"})

@app.route("/chart_data")
def chart_data():
    symbol = request.args.get("symbol")
    if not symbol:
        return jsonify({"error": "Missing symbol"}), 400

    try:
        data = yf.download(symbol, period="1mo", interval="1d")
        if data.empty:
            return jsonify({"error": "No data"}), 404

        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        ema12 = data['Close'].ewm(span=12, adjust=False).mean()
        ema26 = data['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        return jsonify({
            "dates": [str(d.date()) for d in data.index[-30:]],
            "rsi": list(rsi.dropna().values[-30:]),
            "macd": list(macd.dropna().values[-30:]),
            "signal": list(signal.dropna().values[-30:])
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)