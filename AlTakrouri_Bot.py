import ccxt
import time
import os
import requests
import threading
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

# مخزن لمراقبة أسعار الشراء لجني الأرباح
active_trades = {} 

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except: pass

@app.route('/')
def health_check():
    return "✅ رادار التكروري: وضع التداول الكامل (شراء + بيع 10%)"

def monitor_selling():
    """دالة مراقبة العملات المشتراة لبيعها عند الربح"""
    while True:
        try:
            for symbol in list(active_trades.keys()):
                buy_price = active_trades[symbol]
                ticker = exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                # حساب نسبة الربح الحالي
                profit_pct = ((current_price - buy_price) / buy_price) * 100
                
                if profit_pct >= 10.0:  # هدف الربح 10%
                    print(f"💰 جني أرباح في {symbol}: {profit_pct:.2f}%")
                    balance = exchange.fetch_balance()
                    amount = balance.get(symbol.split('/')[0], {}).get('free', 0)
                    
                    if amount > 0:
                        exchange.create_market_sell_order(symbol, amount)
                        send_telegram(f"✅ <b>تم جني الأرباح!</b>\nالعملة: {symbol}\nالربح: {profit_pct:.2f}%")
                        del active_trades[symbol]
        except Exception as e:
            print(f"⚠️ خطأ في المراقبة: {str(e)[:50]}")
        time.sleep(30)

def trading_engine():
    blacklist = ['WAVES/USDT', 'XMR/USDT', 'ANT/USDT', 'MULTI/USDT', 'FUN/USDT', 'REN/USDT']
    print("🚀 انطلاق المحرك (شراء + بيع آلي 10%)..", flush=True)
    
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            
            if usdt >= 30.5:
                tickers = exchange.fetch_tickers()
                for symbol, t in tickers.items():
                    if '/USDT' in symbol and symbol not in blacklist and symbol not in active_trades:
                        if t['percentage'] and t['percentage'] > 5.0:
                            print(f"🎯 شراء فرصة: {symbol}")
                            order = exchange.create_market_buy_order(symbol, 30)
                            # تسجيل سعر الشراء الفعلي للمراقبة
                            active_trades[symbol] = t['last'] 
                            send_telegram(f"🔔 <b>تم الشراء!</b>\nالعملة: {symbol}\nالمبلغ: 30 USDT")
                            break
        except Exception as e:
            print(f"⚠️ خطأ: {str(e)[:100]}")
        time.sleep(60)

# تشغيل محركين: واحد للشراء وواحد للبيع
threading.Thread(target=trading_engine, daemon=True).start()
threading.Thread(target=monitor_selling, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
