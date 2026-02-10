import ccxt
import time
import sys

# استخدام KuCoin لتجنب القيود الجغرافية
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- تم إطلاق الروبوت بنجاح: وضع التداول الوهمي المستقر ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات الأساسية لتجنب أخطاء التعريف
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0  # القيمة الابتدائية لتجنب الخطأ الذي ظهر عندك

    while True:
        try:
            # جلب سعر البيتكوين الحالي
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            timestamp = time.strftime('%H:%M:%S')
            
            print(f"[{timestamp}] السعر الحالي للبيتكوين: {current_price} USDT")
            sys.stdout.flush()
            
            # منطق التداول:
            if btc_held == 0:
                # إذا كنا لا نملك بيتكوين، نقوم بالشراء الوهمي فوراً للبدء
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                print(f"🚀 تم تنفيذ شراء وهمي للبدء بسعر: {buy_price}")
                sys.stdout.flush()

            elif btc_held > 0:
                # إذا كنا نملك بيتكوين، نتحقق من نسبة الربح (0.5% كمثال)
                if current_price > (buy_price * 1.005):
                    balance_usd = btc_held * current_price
                    profit = balance_usd - 1000
                    print(f"💰 تم البيع بربح! الرصيد الجديد: {balance_usd:.2f} | الربح: {profit:.2f}")
                    btc_held = 0
                    buy_price = 0.0
                    sys.stdout.flush()

            time.sleep(15) # فحص السعر كل 15 ثانية
            
        except Exception as e:
            print(f"تنبيه تقني: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
