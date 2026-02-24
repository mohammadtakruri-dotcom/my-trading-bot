import ccxt, time, os, threading, random, pandas as pd, mysql.connector
from flask import Flask

app = Flask(__name__)

# الربط ببيانات InfinityFree الحقيقية
DB_CONFIG = {'host': 'sql313.infinityfree.com', 'user': 'if0_40995422', 'password': 'Ta086020336MO', 'database': 'if0_40995422_database'}

exchange = ccxt.binance({'apiKey': os.getenv('BINANCE_API_KEY'), 'secret': os.getenv('BINANCE_SECRET_KEY'), 'enableRateLimit': True})

def trading_engine():
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            if usdt >= 11.0:
                # شراء بمبلغ مرن بين 11 و30
                buy_amt = round(random.uniform(11.0, min(30.0, usdt)), 2)
                tickers = exchange.fetch_tickers()
                for sym, t in tickers.items():
                    if '/USDT' in sym and t['percentage'] > 5.0:
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
def home(): return "<h1>رادار التكروري يعمل بنجاح</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
