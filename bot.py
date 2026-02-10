import ccxt
import time
import sys
import requests

# استخدام KuCoin لضمان استقرار الاتصال وتجنب القيود الجغرافية
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت متصل الآن بلوحة تحكم التكروري ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات لتجنب أخطاء التعريف (NameError)
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0
    
    # استبدل هذا الرابط برابط ملف الـ PHP على سيرفرك الخاص (مثلاً في InfinityFree)
    API_ENDPOINT = "https://your-domain.com/update_bot.php"

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            # منطق تداول وهمي بسيط للبدء
            if btc_held == 0:
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                action = "شراء"
            else:
                action = "مراقبة السوق"

            # تجهيز البيانات للإرسال إلى الواجهة
            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + btc_held * current_price):,.2f}",
                'action': action
            }

            # إرسال البيانات إلى واجهتك
            try:
                requests.post(API_ENDPOINT, data=payload, timeout=5)
            except:
                pass # استمرار العمل حتى لو تعذر الوصول للموقع مؤقتاً

            print(f"تم تحديث الواجهة بالسعر: {current_price}")
            sys.stdout.flush()
            time.sleep(15) # تحديث كل 15 ثانية

        except Exception as e:
            print(f"تنبيه تقني: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
