import ccxt
import time
import sys

# استخدام KuCoin لتجنب قيود المواقع الجغرافية
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- الروبوت يعمل الآن ويرسل البيانات للواجهة ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات لتجنب خطأ NameError الذي ظهر في صورك
    balance_usd = 1000.0
    btc_held = 0.0
    last_action = "انتظار"
    buy_price = 0.0 

    while True:
        try:
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            
            # منطق بسيط للتداول الوهمي
            if btc_held == 0:
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                last_action = f"شراء بسعر {buy_price}"
            elif btc_held > 0 and current_price > (buy_price * 1.005):
                balance_usd = btc_held * current_price
                btc_held = 0
                last_action = f"بيع بربح عند {current_price}"

            # طباعة النتائج بشكل منظم للسيرفر
            print(f"STATUS|{current_price}|{balance_usd + (btc_held * current_price)}|{last_action}")
            sys.stdout.flush()

            time.sleep(15)
        except Exception as e:
            print(f"ERROR|{e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
