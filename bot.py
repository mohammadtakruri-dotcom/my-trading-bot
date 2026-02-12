import sys
import time
import threading
from flask import Flask # مكتبة بسيطة لفتح المنفذ
import ccxt
import cloudscraper

# 1. إعداد خادم وهمي لإرضاء منصة Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running..."

def run_web_server():
    # Render يرسل رقم المنفذ عبر متغير بيئة يسمى PORT
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# 2. وظيفة البوت الأساسية
def run_trading_bot():
    print("--- بدأ تشغيل البوت مع تجاوز الحماية والمنفذ ---")
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    exchange = ccxt.kucoin()
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','desktop': True})

    balance_usd = 1000.0
    btc_held = 0.0

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + (btc_held * current_price)):,.2f}",
                'action': "مراقبة مستمرة"
            }
            
            # محاولة الإرسال
            try:
                response = scraper.post(API_ENDPOINT, data=payload, timeout=30)
                print(f"[{time.strftime('%H:%M:%S')}] الحالة: {response.status_code}")
            except Exception as e:
                print(f"خطأ إرسال: {e}")

            sys.stdout.flush()
            time.sleep(30)
        except Exception as e:
            print(f"خطأ في جلب البيانات: {e}")
            time.sleep(10)

if __name__ == "__main__":
    # تشغيل الخادم الوهمي في "خيط" منفصل (Thread) لكي لا يعطل البوت
    threading.Thread(target=run_web_server).start()
    
    # تشغيل البوت
    run_trading_bot()
