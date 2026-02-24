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
    'password': 'Ta086020336MO', # كلمة سر MySQL الصحيحة
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

# --- دالة إرسال التنبيهات مع الحماية ---
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"}, timeout=5)
    except Exception as e:
        print(f"⚠️ خطأ تيلجرام: {e}")

# --- دالة الربط مع قاعدة البيانات (محاولة 3 مرات) ---
def execute_db_query(query, params):
    for i in range(3):
        try:
            conn = mysql.connector.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"⚠️ محاولة اتصال SQL فاشلة ({i+1}): {e}")
            time.sleep(2)
    return False

# --- دراسة القوة النسبية للسوق (RSI) ---
def calculate_rsi(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=50)
        df = pd.DataFrame(bars, columns=['t', 'o', 'h', 'l', 'c', 'v'])
        delta = df['c'].diff()
        up, down = delta.clip(lower=0), -1 * delta.clip(upper=0)
        rs = up.ewm(com=13).mean() / down.ewm(com=13).mean()
        return 100 - (100 / (1 + rs)).iloc[-1]
    except:
        return 50

# --- محرك المراقبة (البيع الآلي واليدوي) ---
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
                current_p = ticker['last']
                change = ((current_p - trade['buy_price']) / trade['buy_price']) * 100
                
                # تنفيذ البيع (ربح 10% أو خسارة 5% أو طلب يدوي من PHP)
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

# --- محرك التداول (الشراء الذكي المتغير) ---
def trading_engine():
    blacklist = ['WAVES/USDT', 'XMR/USDT', 'ANT/USDT']
    send_telegram("🚀 <b>رادار التكروري انطلق الآن!</b>")
    
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt_free = float(balance.get('USDT', {}).get('free', 0))
            
            # الشراء بحد أدنى 11$ وحد أقصى 30$
            if usdt_free >= 11.0:
                buy_amt = round(random.uniform(11.0, min(30.0, usdt_free)), 2)
                tickers = exchange.fetch_tickers()
                
                for sym, t in tickers.items():
                    if '/USDT' in sym and sym not in blacklist:
                        rsi = calculate_rsi(sym)
                        # شروط الشراء: صعود أكثر من 5% و RSI أقل من 70
                        if t['percentage'] > 5.0 and rsi < 70:
                            exchange.create_market_buy_order(sym, buy_amt)
                            execute_db_query(
                                "INSERT INTO trades (symbol, buy_price, amount_usdt) VALUES (%s, %s, %s)",
                                (sym, t['last'], buy_amt)
                            )
                            send_telegram(f"🔔 <b>عملية شراء جديدة</b>\nالعملة: {sym}\nالمبلغ: {buy_amt}$\nقوة RSI: {rsi:.1f}")
                            break # شراء عملة واحدة في كل دورة لتوزيع المخاطر
        except Exception as e:
            print(f"⚠️ خطأ محرك: {e}")
        time.sleep(60)

# --- تشغيل الخيوط (Threads) والموقع ---
threading.Thread(target=trading_engine, daemon=True).start()
threading.Thread(target=monitor_trades, daemon=True).start()

@app.route('/')
def home():
    return "<h1>رادار التكروري: المحرك والاتصال بقاعدة البيانات يعملان ✅</h1>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
