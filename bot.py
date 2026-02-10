import ccxt
import time
import sys

# استخدام منصة KuCoin لتجنب قيود المواقع الجغرافية للسيرفرات السحابية
exchange = ccxt.kucoin()

def start_bot():
    print("--- تم إطلاق الروبوت بنجاح: وضع التداول الوهمي المستقر ---")
    sys.stdout.flush()
    
    # تعريف المتغيرات في البداية "خارج الحلقة" لضمان عدم ظهور NameError
    balance_usd = 1000.0
    btc_held = 0.0
    last_buy_price = 0.0 # قمت بتسميته بوضوح لتجنب أي تضارب

    while True:
        try:
            # جلب السعر الحالي
            ticker = exchange.fetch_ticker('BTC/USDT')
            current_price = ticker['last']
            timestamp = time.strftime('%H:%M:%S')
            
            print(f"[{timestamp}] السعر اللحظي للبيتكوين: {current_price} USDT")
            sys.stdout.flush()
            
            # منطق التداول
            if btc_held == 0:
                # إذا كانت المحفظة فارغة، نقوم بالشراء فوراً للبدء في المراقبة
                last_buy_price = current_price
                btc_held = balance_usd / last_buy_price
                balance_usd = 0
                print(f"🚀 [عملية شراء] تم الشراء وهمياً للبدء بسعر: {last_buy_price}")
                sys.stdout.flush()

            elif btc_held > 0:
                # إذا كنا نملك بيتكوين، ننتظر ربح 0.5% للبيع
                if current_price > (last_buy_price * 1.005):
                    balance_usd = btc_held * current_price
                    profit = balance_usd - 1000
                    print(f"💰 [عملية بيع] تم البيع بربح! الرصيد الحالي: {balance_usd:.2f} USDT | الربح: {profit:.2f}")
                    btc_held = 0
                    last_buy_price = 0.0
                    sys.stdout.flush()

            # فحص السعر كل 20 ثانية لتجنب الضغط على الـ API
            time.sleep(20)
            
        except Exception as e:
            print(f"تنبيه (سيتم إعادة المحاولة): {e}")
            sys.stdout.flush()
            time.sleep(10)

if __name__ == "__main__":
    start_bot()
