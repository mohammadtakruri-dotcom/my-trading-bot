import ccxt
import time
import os
import requests
import threading
import pandas as pd
from flask import Flask

app = Flask(__name__)

# مفاتيح التداول والاتصال
API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {'adjustForTimeDifference': True, 'recvWindow': 60000}
})

TG_TOKEN = '8588741495:AAEYDfLoXnJVFbtMEdyjdNrZznwdSdJs0WQ'
TG_ID = '5429169001'

active_trades = {} 

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except: pass

def calculate_rsi(symbol, period=14):
    """دراسة قوة السوق: استنتاج هل العملة غالية جداً أم مناسبة"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=period + 1)
        df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'vol'])
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (10 + rs))
    except: return 50 # قيمة محايدة في حال الخطأ

@app.route('/')
def health_check():
    return "✅ رادار التكروري الذكي: RSI + Stop Loss مفعل"

def monitor_trades():
    """مراقبة ذكية: جني أرباح عند 10% أو وقف خسارة عند 5%"""
    while True:
        try:
            for symbol in list(active_trades.keys()):
                entry_price = active_trades[symbol]
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                change_pct = ((current_price - entry_price) / entry_price) * 100
                
                # 1. جني الأرباح (Take Profit)
                if change_pct >= 10.0:
                    sell_order(symbol, "جني أرباح", change_pct)
                
                # 2. وقف الخسارة (Stop Loss) - حماية المال
                elif change_pct <= -5.0:
                    sell_order(symbol, "وقف خسارة لحماية المحفظة", change_pct)
                    
        except Exception as e:
            print(f"⚠️ خطأ مراقبة: {str(e)[:50]}")
        time.sleep(30)

def sell_order(symbol, reason, pct):
    balance = exchange.fetch_balance()
    amount = balance.get(symbol.split('/')[0], {}).get('free', 0)
    if amount > 0:
        exchange.create_market_sell_order(symbol, amount)
        send_telegram(f"⚖️ <b>تنفيذ أمر بيع ({reason})</b>\nالعملة: {symbol}\nالنسبة: {pct:.2f}%")
        if symbol in active_trades: del active_trades[symbol]

def trading_engine():
    blacklist = ['WAVES/USDT', 'XMR/USDT', 'ANT/USDT', 'MULTI/USDT', 'FUN/USDT', 'REN/USDT']
    print("🚀 انطلاق الرادار الذكي (RSI + Protection)..", flush=True)
    
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            
            if usdt >= 30.5:
                tickers = exchange.fetch_tickers()
                for symbol, t in tickers.items():
                    if '/USDT' in symbol and symbol not in blacklist and symbol not in active_trades:
                        # دراسة السوق: هل السعر صاعد (أعلى من 5%) وهل RSI يسمح بالشراء (أقل من 70)؟
                        rsi = calculate_rsi(symbol)
                        if t['percentage'] > 5.0 and rsi < 70:
                            print(f"🎯 فرصة مدروسة: {symbol} | RSI: {rsi:.2f}")
                            exchange.create_market_buy_order(symbol, 30)
                            active_trades[symbol] = t['last']
                            send_telegram(f"🔔 <b>تم الشراء (بناءً على دراسة RSI)</b>\nالعملة: {symbol}\nالقوة النسبية: {rsi:.2f}")
                            break
        except Exception as e:
            print(f"⚠️ خطأ محرك: {str(e)[:100]}")
        time.sleep(60)

threading.Thread(target=trading_engine, daemon=True).start()
threading.Thread(target=monitor_trades, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
