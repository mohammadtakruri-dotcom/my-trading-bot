import ccxt
import time
import sys
import requests

exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- محاولة الاتصال بلوحة تحكم التكروري ---")
    sys.stdout.flush()
    
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0
    
    API_ENDPOINT = "https://3rood.gt.tc/update_bot.php"
    
    # إضافة Headers لجعل الطلب يبدو طبيعياً للسيرفر
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
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
                # إرسال الطلب مع التحقق من الاتصال
                response = requests.post(API_ENDPOINT, data=payload, headers=headers, timeout=15)
                print(f"استجابة السيرفر ({response.status_code}): {response.text}")
            except Exception as e:
                print(f"عطل في الاتصال مع السيرفر: {e}")

            sys.stdout.flush()
            time.sleep(20)

        except Exception as e:
            print(f"خطأ تقني: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
