import sys
import time
import ccxt
import cloudscraper # مكتبة قوية لتجاوز حماية Cloudflare و JS Challenge

def run_trading_bot():
    print("--- بدء تشغيل البوت المطور لتجاوز الحماية ---")
    
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    exchange = ccxt.kucoin()
    
    # إنشاء مزيل حماية (Scraper) بدلاً من Session العادية
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
            # جلب السعر
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + (btc_held * current_price)):,.2f}",
                'action': "مراقبة السوق النشطة"
            }

            # الإرسال باستخدام scraper لتجاوز تحدي JS
            try:
                response = scraper.post(API_ENDPOINT, data=payload, timeout=30)
                
                if response.status_code == 200:
                    print(f"[{time.strftime('%H:%M:%S')}] تم التجاوز والإرسال بنجاح! | السعر: {current_price}")
                else:
                    print(f"[{time.strftime('%H:%M:%S')}] فشل الإرسال. كود الحالة: {response.status_code}")
                    
            except Exception as e:
                print(f"خطأ أثناء محاولة التجاوز: {e}")

            sys.stdout.flush()
            time.sleep(30)

        except Exception as e:
            print(f"خطأ في جلب البيانات: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
