import ccxt
import time
import sys
import requests # مكتبة لإرسال البيانات لصفحة الويب

exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت يعمل الآن ويرسل البيانات لصفحتك الاحترافية ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات لتجنب خطأ NameError تماماً
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0
    
    # رابط ملف PHP الخاص بك (استبدله بالرابط الحقيقي على استضافتك)
    api_url = "https://your-domain.com/update_bot.php"

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            # تنفيذ أول شراء وهمي لبدء الدورة
            if btc_held == 0:
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                action = "شراء أول"
            else:
                action = "مراقبة السوق"

            # إرسال البيانات لصفحة الويب الخاصة بك
            data = {
                'price': current_price,
                'total': balance_usd + (btc_held * current_price),
                'action': action
            }
            # محاولة إرسال البيانات (ستعمل بمجرد تجهيز ملف PHP)
            try:
                requests.post(api_url, data=data, timeout=5)
            except:
                pass

            print(f"تم تحديث البيانات: {current_price} USDT")
            sys.stdout.flush()
            time.sleep(15)

        except Exception as e:
            print(f"تنبيه: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
