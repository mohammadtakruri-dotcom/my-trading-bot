import ccxt
import time
import sys

# استخدام KuCoin لتجنب قيود المواقع الجغرافية
exchange = ccxt.kucoin()

def run_trading_bot():
    print("--- تم إطلاق الروبوت بنجاح: وضع التداول الوهمي ---")
    sys.stdout.flush()
    
    # إعدادات المحفظة الوهمية
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0  # تعريف المتغير لتجنب الخطأ الذي ظهر عندك

    while True:
        try:
            # جلب سعر البيتكوين
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            timestamp = time.strftime('%H:%M:%S')
            
            print(f"[{timestamp}] السعر الحالي: {current_price} USDT")
            sys.stdout.flush()
            
            # منطق الشراء: إذا لم نكن نملك بيتكوين والسعر مناسب
            if btc_held == 0:
                # سنقوم بشراء وهمي فوراً لأول مرة لبدء الدورة
                btc_held = balance_usd / current_price
                buy_price = current_price
                balance_usd = 0
                print(f"🚀 تم تنفيذ شراء وهمي للبداية بسعر: {buy_price}")
                sys.stdout.flush()

            # منطق البيع: إذا كنا نملك بيتكوين وارتفع السعر بنسبة 0.5%
            elif btc_held > 0 and current_price > (buy_price * 1.005):
                balance_usd = btc_held * current_price
                profit = balance_usd - 1000
                print(f"💰 تم البيع بربح! الرصيد: {balance_usd:.2f} | الربح: {profit:.2f}")
                btc_held = 0
                buy_price = 0.0
                sys.stdout.flush()

            time.sleep(15) # فحص كل 15 ثانية
            
        except Exception as e:
            print(f"تنبيه: {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    run_trading_bot()
