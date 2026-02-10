import ccxt
import time
import sys

# استخدام KuCoin لتجنب القيود الجغرافية للسيرفرات السحابية
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- تم إطلاق الروبوت بنجاح: وضع التداول الوهمي المستقر ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات في البداية لتجنب خطأ NameError
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0 

    while True:
        try:
            # جلب السعر الحالي للبيتكوين
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            timestamp = time.strftime('%H:%M:%S')
            
            print(f"[{timestamp}] السعر الحالي: {current_price} USDT")
            sys.stdout.flush()
            
            # دورة التداول الوهمي
            if btc_held == 0:
                # شراء وهمي فوري للبدء
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                print(f"🚀 تم تنفيذ شراء وهمي للبداية بسعر: {buy_price}")
                sys.stdout.flush()

            elif btc_held > 0 and current_price > (buy_price * 1.005):
                # بيع وهمي عند ربح 0.5%
                balance_usd = btc_held * current_price
                profit = balance_usd - 1000
                print(f"💰 تم البيع بربح! الرصيد: {balance_usd:.2f} | الربح: {profit:.2f}")
                btc_held = 0
                buy_price = 0.0 # إعادة التصفير للدورة القادمة
                sys.stdout.flush()

            time.sleep(15) # فحص كل 15 ثانية
            
        except Exception as e:
            print(f"تنبيه: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
