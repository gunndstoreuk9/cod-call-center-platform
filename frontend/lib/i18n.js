'use client'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'

const AR = {
  // AGENT_WORKSPACE_V2_AR
  "COD OPS · AGENT DESK":"COD OPS · مكتب الموظف",
  "Call customers, confirm orders and move ready orders to delivery.":"اتصل بالعملاء، أكد الطلبات، وحوّل الطلبات الجاهزة إلى التوصيل.",
  "Assigned":"المسندة إليّ",
  "My orders":"طلباتي",
  "New":"جديد",
  "Waiting":"في الانتظار",
  "Follow-up":"متابعة",
  "Need another call":"تحتاج اتصالاً آخر",
  "Confirmed":"مؤكد",
  "Accepted":"تم التأكيد",
  "Ready to Send":"جاهز للإرسال",
  "Sent":"تم الإرسال",
  "All":"الكل",
  "Blacklist":"القائمة السوداء",
  "Search customer, phone, city, order, product...":"ابحث باسم العميل أو الهاتف أو المدينة أو رقم الطلب أو المنتج...",
  "Select ready":"تحديد الطلبات الجاهزة",
  "Clear selection":"إلغاء التحديد",
  "orders in this view":"طلبات في هذا العرض",
  "Refresh":"تحديث",
  "Queue is clear":"لا توجد طلبات حالياً",
  "No orders in this view.":"لا توجد طلبات في هذا العرض.",
  "Select for Digylog":"تحديد للإرسال إلى Digylog",
  "Digylog Blacklist":"القائمة السوداء في Digylog",
  "Correct the customer information before retrying delivery.":"صحح بيانات العميل قبل إعادة محاولة الإرسال.",
  "Offer":"العرض",
  "Qty":"الكمية",
  "Standard":"عادي",
  "Agent Note":"ملاحظة الموظف",
  "Tracking":"رقم التتبع",
  "No Answer":"لا يجيب",
  "Not Interested":"غير مهتم",
  "Edit":"تعديل",
  "Retry Send to Digylog":"إعادة الإرسال إلى Digylog",
  "Send to Digylog":"إرسال إلى Digylog",
  "Selected":"المحدد",
  "confirmed orders ready for Digylog":"طلبات مؤكدة جاهزة للإرسال إلى Digylog",
  "Clear":"إلغاء التحديد",
  "Send Selected to Digylog":"إرسال الطلبات المحددة إلى Digylog",
  "Sending...":"جاري الإرسال...",
  "sent":"تم إرسالها",
  "failed":"فشلت",
  "Order created successfully.":"تم إنشاء الطلب بنجاح.",
  "Order updated successfully.":"تم تحديث الطلب بنجاح.",
  "Callback scheduled.":"تمت جدولة المتابعة.",
  "Select a Digylog city.":"اختر مدينة من قائمة Digylog.",
  "Manual":"يدوي",
  "Order Total":"إجمالي الطلب",
  "This order will automatically be assigned to you and created as NEW.":"سيتم إسناد هذا الطلب إليك تلقائياً وإنشاؤه بحالة جديد.",
  "Save Changes":"حفظ التعديلات",
  "No products are assigned to your agent account.":"لا توجد منتجات مسندة إلى حسابك.",

  'Dashboard':'لوحة التحكم','Orders':'الطلبات','Products':'المنتجات','Stores':'المتاجر','Agents':'الموظفون','Payments':'المدفوعات','Callbacks':'المتابعات','Integrations':'الربط والتكامل','Live Delivery':'التوصيل المباشر','Workspace':'مساحة العمل','My Stats':'إحصائياتي',
  'COD Call Center':'مركز تأكيد الطلبات','Operations Console':'لوحة العمليات','Admin & agent operations workspace':'مساحة موحدة للإدارة وموظفي التأكيد','Sign in':'تسجيل الدخول','Signing in...':'جاري تسجيل الدخول...','Username':'اسم المستخدم','Password':'كلمة المرور','Logout':'تسجيل الخروج','Loading...':'جاري التحميل...',
  'English':'English','Arabic':'العربية','Language':'اللغة',
  'Today':'اليوم','Yesterday':'أمس','Last 7 Days':'آخر 7 أيام','Last 30 Days':'آخر 30 يوماً','This Month':'هذا الشهر','Last Month':'الشهر الماضي','Custom':'فترة مخصصة','Apply':'تطبيق',
  'COD operations by date, product and agent.':'مؤشرات الطلبات حسب الفترة والمنتج والموظف.','Leads':'الطلبات الجديدة','Called':'تم الاتصال','Confirmed':'مؤكد','Delivered':'تم التسليم','No Answer':'لا يجيب','Agent Payout Due':'مستحقات الموظفين','Confirmed Revenue':'قيمة الطلبات المؤكدة','Product performance':'أداء المنتجات','Agent performance':'أداء الموظفين','Delivery %':'نسبة التسليم','Revenue':'المداخيل','Assigned':'مُسند','Due':'المستحق','CR':'نسبة التأكيد','of confirmed':'من المؤكد',
  'All orders, filters and manual COD order entry.':'جميع الطلبات مع البحث والفلاتر وإضافة طلب يدوي.','+ Manual Order':'+ طلب يدوي','Search order, customer, phone':'ابحث برقم الطلب أو العميل أو الهاتف','Search':'بحث','All call statuses':'كل حالات الاتصال','Order':'الطلب','Customer':'العميل','Product':'المنتج','Agent':'الموظف','Call':'الاتصال','Delivery':'التوصيل','Total':'المجموع','Actions':'الإجراءات','Unassigned':'غير مُسند','Auto assign':'إسناد تلقائي','Confirm':'تأكيد','Send Digylog':'إرسال إلى Digylog','Cancel':'إلغاء','Add Manual Order':'إضافة طلب يدوي','Store':'المتجر','Offer (optional)':'العرض (اختياري)','Standard price':'السعر العادي','Customer Name':'اسم العميل','Phone':'الهاتف','City':'المدينة','Assigned Agent':'الموظف المُسند','Quantity':'الكمية','Unit Price':'سعر الوحدة','Total Override (optional)':'تعديل المجموع (اختياري)','Initial Status':'الحالة الأولية','Address':'العنوان','Note':'ملاحظة','Create Order':'إنشاء الطلب','Creating...':'جاري الإنشاء...','Sent to Digylog. Tracking:':'تم الإرسال إلى Digylog. رقم التتبع:',
  'Add and edit products from Admin — including Digylog delivery designation.':'أضف وعدّل المنتجات من الإدارة، بما في ذلك مرجع Digylog.','+ Add Product':'+ إضافة منتج','SKU':'SKU','Price':'السعر','Delivery Ref':'مرجع التوصيل','Commission':'العمولة','Offers':'العروض','Status':'الحالة','Action':'الإجراء','Uses product name':'يستخدم اسم المنتج','Agent default':'افتراضي الموظف','Edit':'تعديل','Disable':'تعطيل','Enable':'تفعيل','Edit Product':'تعديل المنتج','Add Product':'إضافة منتج','Product Name':'اسم المنتج','Selling Price':'سعر البيع','Commission / Confirmation':'عمولة كل تأكيد','Currency':'العملة','Default Qty':'الكمية الافتراضية','Delivery Product Ref / Digylog Designation':'مرجع المنتج / تسمية Digylog','Leave empty to send the product name':'اتركه فارغاً لاستخدام اسم المنتج','Image URL (optional)':'رابط صورة المنتج (اختياري)','Save Changes':'حفظ التعديلات','Save Product':'حفظ المنتج','Saving...':'جاري الحفظ...',
  'Separate products, lead sources and delivery integrations by store.':'افصل المنتجات ومصادر الطلبات وربط شركات التوصيل حسب المتجر.','+ Add Store':'+ إضافة متجر','Code':'الكود','Country':'الدولة','Timezone':'المنطقة الزمنية','Add Store':'إضافة متجر','Store Name':'اسم المتجر','Country Code':'كود الدولة','Shopify Domain (optional)':'دومين Shopify (اختياري)','Save Store':'حفظ المتجر',
  'Create agents, assign products, control commission and access.':'أنشئ الموظفين وحدد المنتجات والعمولات والصلاحيات.','+ Add Agent':'+ إضافة موظف','Default Commission':'العمولة الافتراضية','Unpaid Balance':'الرصيد غير المدفوع','Display Name':'الاسم الظاهر','Allowed Products':'المنتجات المسموحة','Create Agent':'إنشاء الموظف',
  'Agent Payments':'مدفوعات الموظفين','Settle one agent at a time. Payment history is never deleted.':'ادفع لكل موظف بشكل مستقل مع الاحتفاظ بسجل المدفوعات كاملاً.','Current unpaid balances':'الأرصدة الحالية غير المدفوعة','Entries':'العمليات','Gross':'الإجمالي','Adjustments':'التعديلات','Balance':'الرصيد','Pay / Settle':'دفع / تسوية','Adjustment':'تعديل','Payment history':'سجل المدفوعات','Date':'التاريخ','Base':'الأساس','Method':'الطريقة','Reference':'المرجع','Pay Agent':'دفع للموظف','Current balance:':'الرصيد الحالي:','Only this agent will be settled.':'سيتم تسوية هذا الموظف فقط دون التأثير على الآخرين.','Payment Method':'طريقة الدفع','Confirm Payment':'تأكيد الدفع','Amount (+ bonus / - deduction)':'المبلغ (+ مكافأة / - خصم)','Reason':'السبب','Add Adjustment':'إضافة تعديل','settled:':'تمت تسويته:',
  'Due, overdue, today and tomorrow follow-ups.':'متابعات مستحقة ومتأخرة واليوم وغداً.','When':'الموعد','Reason':'السبب','Complete':'إكمال','No callbacks in this bucket.':'لا توجد متابعات في هذه الفئة.','TODAY':'اليوم','DUE':'مستحق','OVERDUE':'متأخر','TOMORROW':'غداً',
  'Connect delivery and lead sources without hard-coding credentials.':'اربط شركات التوصيل ومصادر الطلبات بدون تعديل الكود.','+ Connect Digylog':'+ ربط Digylog','+ Connect Google Sheets':'+ ربط Google Sheets','Connections':'الاتصالات','configured':'مُعدّ','Provider':'المزوّد','Name / Store':'الاسم / المتجر','Last Test':'آخر اختبار','No integration yet. Connect Digylog or Google Sheets above.':'لا يوجد ربط بعد. أضف Digylog أو Google Sheets.','All stores / no store':'كل المتاجر / بدون متجر','NOT TESTED':'لم يُختبر','Test':'اختبار','Apps Script':'Apps Script','Webhook':'Webhook','Recent Integration Events':'أحداث الربط الأخيرة','Troubleshooting log':'سجل التشخيص','Time':'الوقت','Direction':'الاتجاه','Event':'الحدث','Error':'الخطأ','No events yet.':'لا توجد أحداث بعد.','Connect Digylog':'ربط Digylog','Connection Name':'اسم الاتصال','Platform Store':'متجر المنصة','Digylog API Token':'رمز Digylog API','Paste the seller API token':'ألصق Seller API Token','Stored encrypted. It is never returned to the browser after save.':'يتم حفظه مشفراً ولا يعاد إظهاره في المتصفح بعد الحفظ.','Digylog Store ID / Ref':'معرف / مرجع متجر Digylog','Network':'الشبكة','Shipping Fee (port)':'متحمل مصاريف الشحن (port)','Customer pays':'العميل يدفع','Seller pays':'البائع يدفع','After Create':'بعد الإنشاء','Create & send':'إنشاء وإرسال','Create only':'إنشاء فقط','Ask Digylog to check duplicates':'اطلب من Digylog فحص الطلبات المكررة','Orders API URL':'رابط Orders API','Save Digylog':'حفظ Digylog','Connect Google Sheets':'ربط Google Sheets','Google Sheet Tab Name':'اسم تبويب Google Sheet','Default Product (optional)':'منتج افتراضي (اختياري)','Match by SKU':'مطابقة بواسطة SKU','Smart auto-assign imported leads to eligible agents':'إسناد الطلبات المستوردة تلقائياً للموظفين المؤهلين','Save & Generate Script':'حفظ وتوليد السكربت','Webhook URL':'رابط Webhook','Webhook URL — keep it private':'رابط Webhook — احتفظ به سرياً','Copy Webhook':'نسخ Webhook','Apps Script — paste the full code into Extensions → Apps Script':'ألصق الكود كاملاً في Extensions → Apps Script','Copy Full Apps Script':'نسخ Apps Script كاملاً',
  'Digylog shipments, webhook statuses and delivery rates.':'شحنات Digylog وحالات Webhook ومؤشرات التسليم.','Digylog health':'حالة Digylog','Connected':'متصل','Not connected':'غير متصل','Last webhook:':'آخر Webhook:','Seed Status Mappings':'تهيئة ربط الحالات','Failed shipments':'شحنات فاشلة','Unmatched events':'أحداث غير مطابقة','Last test':'آخر اختبار','Last sync':'آخر مزامنة','Sent to delivery':'أرسل للتوصيل','In delivery':'قيد التوصيل','Refused':'مرفوض','Returned':'مرتجع','Issues':'مشاكل','Delivered revenue':'قيمة الطلبات المسلمة','Product delivery performance':'أداء التوصيل حسب المنتج','Dispatch %':'نسبة الإرسال','Confirmed → Delivered':'مؤكد ← مسلّم','Agent delivery quality':'جودة التوصيل حسب الموظف','Refusal %':'نسبة الرفض','Latest shipments':'آخر الشحنات','Tracking':'رقم التتبع','External status':'الحالة الخارجية','Fee':'الرسوم','Latest delivery events':'آخر أحداث التوصيل','Matched':'مطابق','Internal status':'الحالة الداخلية',
  'Queue':'قائمة الانتظار','Delivery sync':'مزامنة التوصيل','Morocco-ready':'جاهز للمغرب','Protected admin & agent session':'جلسة محمية للإدارة والموظفين','SECURE WORKSPACE':'مساحة عمل آمنة','Call Workspace':'مساحة الاتصال','Call → outcome → save → next order.':'اتصل ← اختر النتيجة ← احفظ ← انتقل للطلب التالي.','Queue':'قائمة الانتظار','No city':'بدون مدينة','No address yet':'لم يُدخل العنوان بعد','Busy':'مشغول','Callback':'متابعة','Cancelled':'ملغي','Wrong Number':'رقم خاطئ','Call phone':'اتصال هاتفي','No orders in this queue.':'لا توجد طلبات في هذه القائمة.','Schedule Callback':'جدولة متابعة','Date & Time':'التاريخ والوقت','Schedule':'جدولة','My Stats':'إحصائياتي','Your assigned orders, confirmations, delivery quality and unpaid earnings.':'طلباتك المؤكدة وجودة التسليم ومستحقاتك غير المدفوعة.','Unpaid Earnings':'المستحقات غير المدفوعة',
  'ACTIVE':'نشط','INACTIVE':'غير نشط','DISABLED':'معطل','SUCCESS':'نجاح','FAILED':'فشل','PENDING':'قيد الانتظار','NEW':'جديد','FOLLOW UP':'متابعة','FOLLOW_UP':'متابعة','ALL':'الكل','NO_ANSWER':'لا يجيب','BUSY':'مشغول','CALLBACK':'متابعة','CONFIRMED':'مؤكد','CANCELLED':'ملغي','WRONG_NUMBER':'رقم خاطئ','DUPLICATE':'مكرر','NOT_INTERESTED':'غير مهتم','NOT_READY':'غير جاهز','DISPATCHED':'تم الإرسال','IN_TRANSIT':'في الطريق','OUT_FOR_DELIVERY':'خارج للتسليم','DELIVERED':'تم التسليم','REFUSED':'مرفوض','RETURNED':'مرتجع','DELIVERY_ISSUE':'مشكلة توصيل','CASH':'نقداً','BANK_TRANSFER':'تحويل بنكي','OTHER':'أخرى',
  'Sent':'تم الإرسال','Latest delivery events':'آخر أحداث التوصيل','Internal status':'الحالة الداخلية','Copied to clipboard.':'تم النسخ إلى الحافظة.','Could not copy automatically. Select and copy the text manually.':'تعذر النسخ تلقائياً. حدد النص وانسخه يدوياً.','Digylog integration saved.':'تم حفظ ربط Digylog.','Google Sheets integration saved.':'تم حفظ ربط Google Sheets.','Connection OK':'الاتصال ناجح','Connection test failed':'فشل اختبار الاتصال','NOT_TESTED':'لم يُختبر','CIH':'CIH','CASH_PLUS':'Cash Plus',
  'Cancel':'إلغاء','Close':'إغلاق','Save':'حفظ','Active':'نشط','Inactive':'غير نشط'
}

const LanguageContext = createContext(null)

export function LanguageProvider({ children }) {
  const [locale, setLocaleState] = useState('en')
  useEffect(() => {
    const saved = window.localStorage.getItem('cod_locale')
    if (saved === 'ar' || saved === 'en') setLocaleState(saved)
  }, [])
  useEffect(() => {
    const dir = locale === 'ar' ? 'rtl' : 'ltr'
    document.documentElement.lang = locale
    document.documentElement.dir = dir
    document.body.dataset.locale = locale
  }, [locale])
  const setLocale = (next) => {
    const safe = next === 'ar' ? 'ar' : 'en'
    setLocaleState(safe)
    window.localStorage.setItem('cod_locale', safe)
  }
  const value = useMemo(() => ({
    locale,
    dir: locale === 'ar' ? 'rtl' : 'ltr',
    setLocale,
    t: (text) => locale === 'ar' ? (AR[text] || text) : text,
    status: (text) => locale === 'ar' ? (AR[text] || AR[String(text).replaceAll('_',' ')] || String(text).replaceAll('_',' ')) : String(text).replaceAll('_',' '),
    date: (value, options) => value ? new Intl.DateTimeFormat(locale === 'ar' ? 'ar-MA' : 'en-GB', options || {dateStyle:'medium',timeStyle:'short'}).format(new Date(value)) : '—'
  }), [locale])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useI18n() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useI18n must be used inside LanguageProvider')
  return ctx
}
