import ccxt
import time

# إعداد البوت للعمل في وضع التجربة (بدون مال حقيقي)
exchange = ccxt.binance()
balance = 1000  # سنبدأ بـ 1000 دولار وهمية
btc_held = 0    # كمية البيتكوين التي نملكها حالياً
buy_price = 0

print(f"--- بدء التداول الوهمي برأس مال: {balance} دولار ---")

while True:
    try:
        ticker = exchange.fetch_ticker('BTC/USDT')
        current_price = ticker['last']
        
        # استراتيجية بسيطة جداً للتجربة:
        # إذا نزل السعر عن 95,000 دولار نشتري (مثال)
        if btc_held == 0 and current_price < 95000: 
            btc_held = balance / current_price
            buy_price = current_price
            balance = 0
            print(f"✅ تم الشراء وهمياً بسعر: {current_price}")

        # إذا ربحنا 2% نبيع فوراً
        elif btc_held > 0 and current_price > (buy_price * 1.02):
            balance = btc_held * current_price
            profit = balance - 1000
            print(f"💰 تم البيع بربح! السعر الحالي: {current_price} | الربح الإجمالي: {profit}$")
            btc_held = 0

        time.sleep(30) # فحص السعر كل 30 ثانية
    except Exception as e:
        print(f"خطأ في الاتصال: {e}")
        time.sleep(10)
