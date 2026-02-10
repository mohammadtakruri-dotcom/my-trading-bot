import ccxt
import time
import sys
import requests

# استخدام KuCoin لضمان استقرار الاتصال السحابي وتجاوز الحظر الجغرافي
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت متصل الآن بلوحة تحكم التكروري: 3rood.gt.tc ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات لتجنب خطأ التعريف (NameError)
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0
    
    # الرابط الذي زودتني به لاستقبال البيانات
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            # دورة تداول وهمية بسيطة: شراء عند أول تشغيل
            if btc_held == 0:
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                action = "شراء"
            else:
                action = "مراقبة السوق"

            # تجهيز البيانات للإرسال إلى الواجهة الاحترافية
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + btc_held * current_price):,.2f}",
                'action': action
            }

            # إرسال البيانات (POST) إلى سيرفرك
            try:
                response = requests.post(API_ENDPOINT, data=payload, timeout=10)
                if response.status_code == 200:
                    print(f"تم التحديث بنجاح: {current_price} USDT")
                else:
                    print(f"فشل التحديث، كود الحالة: {response.status_code}")
            except Exception as e:
                print(f"فشل الإرسال لموقعك: {e}")

            sys.stdout.flush()
            time.sleep(20) # فحص وتحديث كل 20 ثانية

        except Exception as e:
            print(f"خطأ تقني: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
