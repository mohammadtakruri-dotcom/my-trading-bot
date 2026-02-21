import ccxt, time, os
from dotenv import load_dotenv

# تحميل الإعدادات (إذا كنت تستخدم ملف .env محلياً)
load_dotenv()

# تهيئة الاتصال بمفاتيحك المفعّلة (robot)
exchange = ccxt.binance({
    'apiKey': 'NpU0M5UXBSptfwhaDCiV0fLVkcrjcU4Tvnu3delwEojasUY40P86f4woNJefqe6r',
    'secret': 'ATaA2II1KD6Y9wAUXaAudCbRULT9WnOqTiZ04PTj0sYTmdiebv4Ue9Wfi3lfxfn',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True, # حل مشكلة فارق التوقيت في السيرفرات
        'recvWindow': 15000              # توسيع نافذة القبول لضمان تنفيذ الأوامر
    }
})

# صمامات الأمان المالية
MIN_BALANCE_RESERVE = 10.0  # رصيد احتياطي (أمان)
TRADE_AMOUNT_USDT = 11.0    # الحد الأدنى لتجاوز فلتر NOTIONAL في باينانس

def get_account_balance():
    """جلب الرصيد والتأكد من صحة المفاتيح"""
    try:
        balance = exchange.fetch_balance()
        usdt_free = float(balance.get('USDT', {}).get('free', 0))
        # flush=True لضمان ظهور النتائج فوراً في سجلات DigitalOcean
        print(f"💰 الرصيد الحالي المكتشف في محفظتك: {usdt_free:.2f} USDT", flush=True)
        return usdt_free
    except Exception as e:
        # إذا ظهر خطأ Invalid API-Key هنا، تأكد من تحديث الـ IP في باينانس
        print(f"⚠️ تنبيه: فشل الاتصال، تأكد من إعدادات الـ IP في باينانس. الخطأ: {e}", flush=True)
        return None

def scan_market_opportunities():
    """رادار مسح العملات الصاعدة (أكثر من 5%)"""
    try:
        tickers = exchange.fetch_tickers()
        gainers = []
        for symbol, ticker in tickers.items():
            if '/USDT' in symbol and ticker['percentage'] is not None:
                # وضع المقامر: اقتناص العملات التي صعدت بأكثر من 5%
                if ticker['percentage'] > 5:  
                    gainers.append({'symbol': symbol, 'pct': ticker['percentage']})
        return sorted(gainers, key=lambda x: x['pct'], reverse=True)[:5]
    except Exception as e:
        print(f"❌ خطأ في مسح السوق: {e}", flush=True)
        return []

print("🚀 انطلق نظام رادار التكروري المضمون في السحابة...", flush=True)

while True:
    try:
        balance = get_account_balance()
        
        if balance is not None:
            # التحقق من توفر رصيد كافٍ (41.14 USDT)
            if balance > (TRADE_AMOUNT_USDT + MIN_BALANCE_RESERVE):
                opportunities = scan_market_opportunities()
                if not opportunities:
                    print("⚖️ السوق حالياً مستقر، الرادار يبحث عن عملات صاعدة...", flush=True)
                
                for opp in opportunities:
                    print(f"🔥 فرصة مكتشفة: {opp['symbol']} بصعود {opp['pct']:.2f}%", flush=True)
            else:
                print(f"🛑 الرصيد المتاح ({balance:.2f}) يقل عن حد الأمان، وضع المراقبة مفعل.", flush=True)
                
    except Exception as main_error:
        print(f"⚠️ خطأ في الدورة الحالية: {main_error}", flush=True)
            
    # انتظار دقيقة واحدة قبل الفحص القادم لضمان استمرارية العمل
    time.sleep(60)
