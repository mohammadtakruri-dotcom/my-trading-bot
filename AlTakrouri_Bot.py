import ccxt
import time
import os
import requests
import threading
from flask import Flask

app = Flask(__name__)

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

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": TG_ID, "text": msg, "parse_mode": "HTML"})
    except: pass

@app.route('/')
def health_check():
    return "✅ رادار التكروري: وضع الاستقرار مفعل (30 USDT)"

def trading_engine():
    # القائمة السوداء الشاملة للعملات المزعجة
    blacklist = ['WAVES/USDT', 'XMR/USDT', 'ANT/USDT', 'MULTI/USDT', 'FUN/USDT', 'REN/USDT', 'BTS/USDT'] 
    
    print("🚀 انطلاق الرادار المستقر..", flush=True)
    
    while True:
        try:
            balance = exchange.fetch_balance()
            usdt = float(balance.get('USDT', {}).get('free', 0))
            print(f"💰 الرصيد الحالي: {usdt:.2f} USDT", flush=True)

            if usdt >= 30.5:
                tickers = exchange.fetch_tickers()
                # ترتيب العملات حسب نسبة الصعود الأعلى أولاً
                sorted_tickers = sorted(tickers.items(), key=lambda x: x[1]['percentage'] or 0, reverse=True)
                
                for symbol, t in sorted_tickers:
                    if '/USDT' in symbol and symbol not in blacklist:
                        if t['percentage'] and t['percentage'] > 5.0:
                            try:
                                print(f"🎯 محاولة قنص: {symbol} (+{t['percentage']}%)")
                                exchange.create_market_buy_order(symbol, 30)
                                send_telegram(f"🔔 <b>تم تنفيذ صفقة ناجحة!</b>\nالعملة: {symbol}\nالمبلغ: 30 USDT")
                                break
                            except Exception as e:
                                # إذا كانت العملة مغلقة، أضفها للقائمة السوداء فوراً وتجاوزها
                                print(f"⚠️ تجاوز عملة مغلقة: {symbol}")
                                blacklist.append(symbol)
                                continue
        except Exception as e:
            print(f"⚠️ خطأ: {str(e)[:100]}", flush=True)
        time.sleep(60)

threading.Thread(target=trading_engine, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
