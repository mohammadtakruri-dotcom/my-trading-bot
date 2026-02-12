import sys
import time
import threading
import os
from flask import Flask
import ccxt
import cloudscraper

# 1. إعداد خادم Flask لإرضاء Render ومنع إعادة تشغيل البوت
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is Active and Running!", 200

def start_web_server():
    # Render يخصص منفذ تلقائي، نحن نقرأه هنا
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# 2. وظيفة الروبوت الأساسية
def run_trading_bot():
    print("--- تم تشغيل محرك التداول المطور ---")
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    
    # استخدام محاكي متصفح متقدم
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    
    exchange = ccxt.kucoin()
    balance_usd = 1000.0
    btc_held = 0.0

    while True:
        try:
            # جلب البيانات
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + (btc_held * current_price)):,.2f}",
                'action': "تحديث تلقائي (Safe Mode)"
            }

            # محاولة الإرسال مع تجاوز الحماية
            try:
                response = scraper.post(API_ENDPOINT, data=payload, timeout=30)
                if response.status_code == 200:
                    print(f"[{time.strftime('%H:%M:%S')}] نجح الإرسال | السعر: {current_price}")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] السيرفر رد بكود: {response.status_code}")
            except Exception as e:
                print(f"فشل تجاوز الحماية: {e}")

            sys.stdout.flush()
            time.sleep(30)
            
        except Exception as e:
            print(f"خطأ في جلب السعر: {e}")
            time.sleep(15)

if __name__ == "__main__":
    # تشغيل خادم الويب في خيط (Thread) منفصل لتجنب Port Scan Timeout
    threading.Thread(target=start_web_server, daemon=True).start()
    
    # تشغيل البوت في الخيط الرئيسي
    run_trading_bot()
