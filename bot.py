import ccxt
import time
import sys
import requests

# استخدام KuCoin لتجنب الحظر الجغرافي
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت متصل الآن بلوحة تحكم التكروري ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات لتجنب خطأ NameError
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0
    
    # هام: استبدل الرابط أدناه برابط ملف update_bot.php على سيرفرك
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            # منطق تداول وهمي (شراء عند التشغيل)
            if btc_held == 0:
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                action = "شراء"
            else:
                action = "مراقبة السوق"

            # تجهيز البيانات للإرسال
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + btc_held * current_price):,.2f}",
                'action': action
            }

            # إرسال البيانات إلى موقعك
            try:
                response = requests.post(API_ENDPOINT, data=payload, timeout=10)
                print(f"استجابة السيرفر: {response.status_code}")
            except Exception as e:
                print(f"فشل الإرسال للموقع: {e}")

            print(f"تم جلب السعر: {current_price} USDT")
            sys.stdout.flush()
            time.sleep(20)

        except Exception as e:
            print(f"خطأ تقني: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
