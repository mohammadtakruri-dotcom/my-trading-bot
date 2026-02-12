import sys
import time
import threading
import os
from flask import Flask
import ccxt
import cloudscraper

# 1. إعداد خادم ويب بسيط جداً لإرضاء منصة Render ومنع خطأ الـ Port
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is Alive!", 200

def start_web_server():
    # Render يرسل رقم المنفذ في متغير بيئة يسمى PORT
    port = int(os.environ.get("PORT", 10000))
    # تشغيل السيرفر على 0.0.0.0 ليتمكن Render من رؤيته
    app.run(host='0.0.0.0', port=port)

# 2. وظيفة التداول والإرسال الأساسية
def run_trading_bot():
    print("--- الروبوت يعمل الآن مع محاكاة متصفح متقدمة ---")
    
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    exchange = ccxt.kucoin()
    
    # إنشاء scraper يحاكي متصفح كامل لتجاوز JS Challenge
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )

    balance_usd = 1000.0
    btc_held = 0.0

    while True:
        try:
            # جلب سعر البيتكوين
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + (btc_held * current_price)):,.2f}",
                'action': "مراقبة نشطة (تجاوز الحماية)"
            }

            # محاولة الإرسال باستخدام Scraper
            try:
                response = scraper.post(API_ENDPOINT, data=payload, timeout=30)
                
                # التحقق من نجاح التجاوز
                if "slowAES" in response.text:
                    print(f"[{time.strftime('%H:%M:%S')}] لا تزال الحماية قوية، نحاول مجدداً...")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] تم الإرسال بنجاح! الحالة: {response.status_code}")
            
            except Exception as e:
                print(f"خطأ في الاتصال: {e}")

            sys.stdout.flush()
            time.sleep(30) # فحص كل 30 ثانية

        except Exception as e:
            print(f"خطأ تقني: {e}")
            time.sleep(10)

if __name__ == "__main__":
    # تشغيل سيرفر الويب في الخلفية حتى لا يتوقف البوت
    web_thread = threading.Thread(target=start_web_server)
    web_thread.daemon = True
    web_thread.start()
    
    # تشغيل البوت الأساسي
    run_trading_bot()
