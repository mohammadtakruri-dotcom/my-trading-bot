import ccxt
import time
import sys

# استخدام منصة KuCoin لتجاوز القيود الجغرافية للسيرفرات السحابية
exchange = ccxt.kucoin()

def start_bot():
    print("--- تم إطلاق الروبوت بنجاح: تداول تجريبي مستقر ---")
    sys.stdout.flush() # لضمان ظهور النتائج فوراً في Render
    
    # تعريف المتغيرات الأساسية في بداية التشغيل لتجنب خطأ NameError
    balance_usd = 1000.0
    btc_held = 0.0
    buy_price = 0.0 

    while True:
        try:
            # جلب السعر الحالي للبيتكوين
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            timestamp = time.strftime('%H:%M:%S')
            
            print(f"[{timestamp}] السعر اللحظي: {current_price} USDT")
            sys.stdout.flush()
            
            # منطق التداول:
            if btc_held == 0:
                # إذا كانت المحفظة فارغة، نشتري وهمياً فوراً للبدء بمراقبة الربح
                buy_price = current_price
                btc_held = balance_usd / buy_price
                balance_usd = 0
                print(f"🚀 [شراء] تم الشراء وهمياً للبدء بسعر: {buy_price}")
                sys.stdout.flush()

            elif btc_held > 0:
                # إذا كنا نملك بيتكوين، ننتظر ربح 0.5% لكي نبيع
                if current_price > (buy_price * 1.005):
                    balance_usd = btc_held * current_price
                    profit = balance_usd - 1000
                    print(f"💰 [بيع] تم البيع بربح! الرصيد الحالي: {balance_usd:.2f} USDT | الربح: {profit:.2f}")
                    sys.stdout.flush()
                    btc_held = 0
                    buy_price = 0.0 # إعادة التصفير للدورة القادمة

            # فحص السعر كل 15 ثانية
            time.sleep(15)
            
        except Exception as e:
            print(f"تنبيه تقني (سيتم إعادة المحاولة): {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    start_bot()
