import ccxt, time, os, requests, threading, random
import pandas as pd
import mysql.connector
from flask import Flask

app = Flask(__name__)

# إعدادات الاتصال ببيانات InfinityFree الحقيقية
DB_CONFIG = {
    'host': 'sql313.infinityfree.com',
    'user': 'if0_40995422',
    'password': 'Ta086020336MO',
    'database': 'if0_40995422_database'
}

exchange = ccxt.binance({
    'apiKey': os.getenv('BINANCE_API_KEY'),
    'secret': os.getenv('BINANCE_SECRET_KEY'),
    'enableRateLimit': True
})

def calculate_rsi(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        delta = df['c'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        rs = up.ewm(com=13).mean() / down.ewm(com=13).mean()
        return 100 - (100 / (1 + rs)).iloc[-1]
    except: return 50

def trading_engine():
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt_free = float(balance.get('USDT', {}).get('free', 0))
            
            # الشراء بحد أدنى 11 وحد أقصى 30
            if usdt_free >= 11.0:
                buy_amt = round(random.uniform(11.0, min(30.0, usdt_free)), 2)
                tickers = exchange.fetch_tickers()
                for sym, t in tickers.items():
                    if '/USDT' in sym and t['percentage'] > 5.0 and calculate_rsi(sym) < 70:
                        exchange.create_market_buy_order(sym, buy_amt)
                        conn = mysql.connector.connect(**DB_CONFIG)
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO trades (symbol, buy_price, amount_usdt) VALUES (%s, %s, %s)", (sym, t['last'], buy_amt))
                        conn.commit()
                        conn.close()
                        break
        except Exception as e: print(f"Error: {e}")
        time.sleep(60)

threading.Thread(target=trading_engine, daemon=True).start()

@app.route('/')
def home(): return "<h1>رادار التكروري: المحرك يعمل</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
