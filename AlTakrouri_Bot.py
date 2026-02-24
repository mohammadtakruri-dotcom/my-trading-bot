import ccxt
import time
import os
import requests
import threading
import random
import pandas as pd
import mysql.connector
from flask import Flask

app = Flask(__name__)

# --- إعدادات الاتصال ببياناتك الحقيقية ---
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

DB_CONFIG = {
    'host': 'sql313.infinityfree.com',
    'user': 'if0_40995422',
    'password': 'Ta086020336MO', # كلمة سر MySQL الحقيقية
    'database': 'if0_40995422_database'
}

TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True}
})

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        print(f"⚠️ خطأ تيلجرام: {e}")

def execute_db_query(query, params):
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ خطأ SQL: {e}")
        return False

def calculate_rsi(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        delta = df['c'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        rs = up.ewm(com=13).mean() / down.ewm(com=13).mean()
        rsi = 100 - (100 / (1 + rs)).iloc[-1]
        return rsi if not pd.isna(rsi) else None # تجنب إرجاع NaN
    except:
        return None

def monitor_trades():
    while True:
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM trades WHERE status IN ('OPEN', 'PENDING_SELL')")
            trades = cursor.fetchall()
            conn.close()

            for trade in trades:
                ticker = exchange.fetch_ticker(trade['symbol'])
                current_p = ticker.get('last')
                
                if current_p is None: continue # حماية من القيم الفارغة

                change = ((current_p - trade['buy_price']) / trade['buy_price']) * 100
                
                # تنفيذ البيع التلقائي أو اليدوي من PHP
                if change >= 10.0 or change <= -5.0 or trade['status'] == 'PENDING_SELL':
                    balance = exchange.fetch_balance()
                    symbol_only = trade['symbol'].split('/')[0]
                    amount_to_sell = balance.get(symbol_only, {}).get('free', 0)
                    
                    if amount_to_sell > 0:
                        exchange.create_market_sell_order(trade['symbol'], amount_to_sell)
                        execute_db_query(
                            "UPDATE trades SET sell_price=%s, status='CLOSED', profit_pct=%s WHERE id=%s",
                            (current_p, round(change, 2), trade['id'])
                        )
                        send_telegram(f"💰 <b>تم البيع بنجاح!</b>\nالعملة: {trade['symbol']}\nالربح/الخسارة: {change:.2f}%")
        except:
            pass
        time.sleep(20)

def trading_engine():
    blacklist = ['WAVES/USDT', 'XMR/USDT', 'ANT/USDT']
    send_telegram("🚀 <b>محرك التكروري يعمل الآن بدون أخطاء!</b>")
    
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt_free = float(balance.get('USDT', {}).get('free', 0))
            
            # الشراء بحد أدنى 10.5$ (مرونة أكثر)
            if usdt_free >= 10.5:
                buy_amt = round(random.uniform(10.5, min(30.0, usdt_free)), 2)
                tickers = exchange.fetch_tickers()
                
                for sym, t in tickers.items():
                    # حماية من خطأ NoneType المكتشف في السجلات
                    change_24h = t.get('percentage')
                    last_p = t.get('last')

                    if '/USDT' in sym and change_24h is not None and last_p is not None:
                        if change_24h > 5.0 and sym not in blacklist:
                            rsi = calculate_rsi(sym)
                            # التأكد أن RSI قيمة عددية وآمنة
                            if rsi is not None and rsi < 70:
                                exchange.create_market_buy_order(sym, buy_amt)
                                execute_db_query(
                                    "INSERT INTO trades (symbol, buy_price, amount_usdt) VALUES (%s, %s, %s)",
                                    (sym, last_p, buy_amt)
                                )
                                send_telegram(f"🔔 <b>شراء ذكي جديد</b>\nالعملة: {sym}\nالمبلغ: {buy_amt}$\nقوة RSI: {rsi:.1f}")
                                break 
        except Exception as e:
            print(f"⚠️ خطأ محرك: {e}")
        time.sleep(60)

threading.Thread(target=trading_engine, daemon=True).start()
threading.Thread(target=monitor_trades, daemon=True).start()

@app.route('/')
def home():
    return "<h1>رادار التكروري: المحرك مستقر 100% ✅</h1>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
