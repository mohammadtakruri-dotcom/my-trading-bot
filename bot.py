import ccxt
import time
import sys
import requests

exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت متصل الآن بلوحة تحكم التكروري ---")
    sys.stdout.flush()
    
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0
    
    # ضع رابطك الحقيقي هنا (مثال: https://mohammed.com/update_bot.php)
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            # منطق وهمي: شراء أول دورة
            if btc_held == 0:
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                action = "شراء"
            else:
                action = "مراقبة السوق"

            payload = {
                'price': f"${current_price:,.2f}",
                'total': f"${(balance_usd + btc_held * current_price):,.2f}",
                'action': action
            }

            try:
                # إرسال البيانات
                requests.post(API_ENDPOINT, data=payload, timeout=5)
            except Exception as req_err:
                print(f"خطأ في الإرسال للموقع: {req_err}")

            print(f"سعر البيتكوين: {current_price} USDT")
            sys.stdout.flush()
            time.sleep(15)

        except Exception as e:
            print(f"تنبيه: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
