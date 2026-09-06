# COD Call Center — Setup A to Z

هاد الـguide مكتوب باش تمشي **step by step / click by click** من ZIP حتى platform production مربوطة بـ:

- GitHub
- Railway hosting
- PostgreSQL
- Domain + HTTPS
- Digylog delivery
- Google Sheets lead import

> **مهم قبل ما تبدأ:** ما تبدّلش `APP_SECRET` من بعد ما تربط integrations. هو المفتاح اللي كيتستعمل لتشفير API tokens داخل database. إلا تبدّل، الـtokens القديمة ما غاديش تبقى قابلة للفك.

---

# 0) الشكل النهائي اللي غادي نوصلو ليه

```text
Your Domain
│
├── app.yourdomain.com  → Next.js Frontend
│                         Admin + Agents
│
└── api.yourdomain.com  → FastAPI Backend
                          │
                          ├── PostgreSQL
                          ├── Digylog API
                          ├── Digylog Webhook
                          └── Google Sheets Webhook
```

Repo واحد فـGitHub:

```text
cod-call-center-platform/
├── backend/
├── frontend/
├── docs/
├── docker-compose.yml
├── .env.example
└── README.md
```

Railway غادي يكون فيه 3 services:

```text
Postgres
Backend
Frontend
```

---

# 1) شنو خاصك قبل البداية

وجد هاد الحسابات/الحوايج:

- GitHub account
- Railway account
- Domain عندك أو domain غادي تشريه
- DNS access ديال domain
- Digylog Seller/API token
- Google account باش تستعمل Google Sheets + Apps Script
- ZIP ديال هاد المشروع

لـDigylog، الـAPI documentation المرجعية:

`https://documenter.getpostman.com/view/20928347/2sBXqNoKfH`

الـintegration الحالي مبني على Seller API V2/V3 contract المستعمل فالمشروع القديم، وCreate Order default endpoint هو:

```text
POST https://api.digylog.com/api/v2/seller/orders
```

---

# 2) جرّب المشروع محلياً أولاً — Recommended

## 2.1 فك ZIP

فك:

```text
cod-call-center-platform-v2-integrations.zip
```

غادي تلقى folder:

```text
cod-call-center-platform
```

## 2.2 افتح Terminal داخل folder

macOS:

1. افتح Terminal.
2. كتب `cd ` مع space.
3. جرّ folder ديال المشروع للـTerminal.
4. Enter.

Windows:

1. افتح folder.
2. Click فـaddress bar.
3. كتب `cmd`.
4. Enter.

## 2.3 أنشئ `.env`

macOS/Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

## 2.4 بدّل secrets

فتح `.env` بأي text editor.

بدّل على الأقل:

```env
POSTGRES_PASSWORD=PUT_A_STRONG_DB_PASSWORD_HERE
DATABASE_URL=postgresql+psycopg://callcenter:PUT_A_STRONG_DB_PASSWORD_HERE@db:5432/callcenter

ADMIN_USERNAME=owner
ADMIN_PASSWORD=PUT_A_STRONG_OWNER_PASSWORD_HERE
ADMIN_DISPLAY_NAME=Owner

APP_SECRET=PUT_A_LONG_RANDOM_SECRET_HERE
```

Generate `APP_SECRET`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Local values يبقاو:

```env
CORS_ORIGINS=http://localhost:3000
COOKIE_SECURE=false
PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## 2.5 شغل Docker

خص Docker Desktop يكون شغال.

```bash
docker compose up --build
```

من بعد افتح:

Frontend:

```text
http://localhost:3000
```

Backend health:

```text
http://localhost:8000/health
```

Swagger API docs:

```text
http://localhost:8000/docs
```

Expected health response:

```json
{
  "ok": true,
  "service": "COD Call Center",
  "environment": "development"
}
```

## 2.6 Login

استعمل:

```text
Username = ADMIN_USERNAME
Password = ADMIN_PASSWORD
```

الـbackend كينشئ Owner و`Morocco Store` أوتوماتيكياً أول مرة.

---

# 3) Setup الأول داخل platform

من بعد Login دير setup بهاد الترتيب:

```text
1. Stores
2. Products
3. Agents
4. Integrations
5. Test Order
```

## 3.1 Stores

Sidebar → **Stores**.

كاين `Morocco Store` default.

إلا بغيتي store جديد:

1. Click `+ Add Store`.
2. `Store Name`: مثلاً `Morocco NOVAMAN`.
3. `Code`: مثلاً `MOROCCO_NOVAMAN`.
4. `Country Code`: `MA`.
5. `Currency`: `MAD`.
6. `Timezone`: `Africa/Casablanca`.
7. Shopify domain optional.
8. Click `Save Store`.

## 3.2 Products

Sidebar → **Products** → `+ Add Product`.

مثال:

```text
Store: Morocco Store
Product Name: NOVAMAN
SKU: NOVAMAN2026
Selling Price: 399
Commission / Confirmation: 5
Currency: MAD
Default Qty: 1
Delivery Product Ref / Digylog Designation: NOVAMAN
```

`Delivery Product Ref` هو الاسم/reference اللي غادي يمشي لـDigylog داخل `refs.designation`.

إلا خليتيه فارغ، system كيستعمل Product Name.

Click `Save Product`.

إلا product موجود من قبل:

1. Products.
2. Click `Edit`.
3. عمّر `Delivery Product Ref / Digylog Designation`.
4. `Save Changes`.

## 3.3 Agents

Sidebar → **Agents** → `+ Add Agent`.

دخل:

```text
Username
Password
Display Name
Default Commission
Allowed Products
```

اختار products اللي agent مسموح ليه يخدم عليهم.

---

# 4) Upload المشروع لـGitHub — Click by Click

## Option A — GitHub Web + Terminal

### 4.1 أنشئ repository

1. دخل لـGitHub.
2. فوق فاليمين click `+`.
3. Click `New repository`.
4. Repository name:

```text
cod-call-center-platform
```

5. اختار **Private** إلا platform ديالك production وفيها business code.
6. **ما تزيدش README جديد** حيث المشروع عندو README ديالو.
7. Click `Create repository`.

### 4.2 Push المشروع

من Terminal داخل project folder:

```bash
git init
git add .
git commit -m "Initial COD call center platform with integrations"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cod-call-center-platform.git
git push -u origin main
```

إلا GitHub عطاك commands مختلفين فالـQuick Setup، استعمل URL ديال repo ديالك بالضبط.

### 4.3 تأكد أن `.env` ما طلعش

فـGitHub خاصك تشوف:

```text
.env.example   ✅
.env           ❌ MUST NOT EXIST
```

`.gitignore` فالمشروع كيمنع `.env`، ولكن تأكد بعينيك.

---

# 5) Hosting على Railway — الطريقة الموصى بها لهاد repo

المشروع monorepo فيه `frontend/` و`backend/` منفصلين. Railway كيدعم هاد الشكل باستعمال Root Directory مختلف لكل service.

## 5.1 Create Project

1. دخل لـRailway dashboard.
2. Click `+ New Project`.
3. اختار `Empty Project`.
4. سميه مثلاً:

```text
COD Call Center
```

---

# 6) Add PostgreSQL

1. داخل Railway Project Canvas click `+ New`.
2. اختار `Database`.
3. اختار `PostgreSQL`.
4. تسنى حتى يولي service online.

Railway PostgreSQL كيوفر variables من بينها `DATABASE_URL`.

سمّي service مثلاً:

```text
Postgres
```

---

# 7) Deploy Backend

## 7.1 Create Backend service

1. Project Canvas → `+ New`.
2. اختار `GitHub Repo`.
3. Connect GitHub إذا طلب permission.
4. اختار repo:

```text
cod-call-center-platform
```

5. سمّي service:

```text
Backend
```

## 7.2 Root Directory

1. افتح Backend service.
2. `Settings`.
3. قلب على `Root Directory`.
4. كتب:

```text
/backend
```

Railway غادي يلقى `backend/Dockerfile` أوتوماتيكياً من بعد root directory يتحدد.

## 7.3 Backend Variables

Backend service → `Variables`.

زيد هاد variables:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
CORS_ORIGINS=https://app.YOURDOMAIN.com
SESSION_COOKIE_NAME=cc_session
SESSION_HOURS=12
COOKIE_SECURE=true
TIMEZONE=Africa/Casablanca
ADMIN_USERNAME=owner
ADMIN_PASSWORD=YOUR_VERY_STRONG_OWNER_PASSWORD
ADMIN_DISPLAY_NAME=Owner
APP_SECRET=YOUR_LONG_RANDOM_SECRET
PUBLIC_API_BASE_URL=https://api.YOURDOMAIN.com
ENVIRONMENT=production
```

### مهم جداً: APP_SECRET

Generate مرة وحدة:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

خزنو فpassword manager.

**ما تبدلوش من بعد ما تزيد Digylog/Google Sheets integrations**، حيث tokens كيتشفرو به.

### إلا domain مازال ما ربطتيهش

تقدر فالأول تستعمل Railway temporary backend domain فـ:

```env
PUBLIC_API_BASE_URL=https://YOUR-BACKEND.up.railway.app
```

ومن بعد تبدلو لـcustom domain وتعمل redeploy.

## 7.4 Deploy backend

Review staged changes → `Deploy`.

Backend startup كيدير تلقائياً:

```text
alembic upgrade head
python -m app.seed
uvicorn
```

يعني database migrations وOwner seed كيتدارو تلقائياً.

## 7.5 Generate temporary backend domain

Backend → `Settings` → `Public Networking` → `Generate Domain`.

جرب:

```text
https://YOUR-BACKEND.up.railway.app/health
```

خاص ترجع `ok: true`.

---

# 8) Deploy Frontend

## 8.1 Create Frontend service

1. Project Canvas → `+ New`.
2. `GitHub Repo`.
3. اختار **نفس repo**.
4. سمي service:

```text
Frontend
```

## 8.2 Root Directory

Frontend → `Settings` → `Root Directory`:

```text
/frontend
```

## 8.3 Frontend Variable

Frontend → `Variables`:

```env
NEXT_PUBLIC_API_URL=https://YOUR-BACKEND.up.railway.app/api/v1
```

أو من بعد custom domain:

```env
NEXT_PUBLIC_API_URL=https://api.YOURDOMAIN.com/api/v1
```

`NEXT_PUBLIC_API_URL` كيتدخل فـNext.js build، لذلك من بعد تغييره خاص deploy جديد.

## 8.4 Deploy

Deploy service.

## 8.5 Generate temporary frontend domain

Frontend → `Settings` → `Public Networking` → `Generate Domain`.

مثلاً:

```text
https://YOUR-FRONTEND.up.railway.app
```

---

# 9) CORS قبل أول Login production

دابا رجع Backend → Variables.

إلا كتستعمل temporary frontend Railway domain:

```env
CORS_ORIGINS=https://YOUR-FRONTEND.up.railway.app
```

Save/Deploy Backend.

جرب login من frontend temporary domain.

إلا login خدم، hosting الأساسي سليم.

---

# 10) ربط Domain

أفضل structure:

```text
app.yourdomain.com → Frontend
api.yourdomain.com → Backend
```

ماشي ضروري domain provider يكون Cloudflare؛ تقدر تستعمل Namecheap/GoDaddy/Cloudflare أو أي DNS provider.

## 10.1 Frontend custom domain

Railway:

1. Frontend service.
2. `Settings`.
3. `Public Networking`.
4. `+ Custom Domain`.
5. كتب:

```text
app.yourdomain.com
```

Railway غادي يعطيك DNS records، عادة:

```text
CNAME
TXT
```

## 10.2 زيد DNS records

فـDNS provider ديالك:

1. DNS / Records.
2. Add Record.
3. زيد **CNAME** بالضبط كما Railway عطاه.
4. زيد **TXT** بالضبط كما Railway عطاه.

**CNAME بوحدو ما كافيش فـRailway custom domain؛ TXT verification مهم حتى هو.**

## 10.3 Backend custom domain

نفس الخطوات فـBackend:

```text
api.yourdomain.com
```

زيد CNAME + TXT اللي Railway عطاك.

Railway كيصدر SSL certificate أوتوماتيكياً منين domain يتحقق.

## 10.4 Update production variables

Backend:

```env
CORS_ORIGINS=https://app.yourdomain.com
PUBLIC_API_BASE_URL=https://api.yourdomain.com
COOKIE_SECURE=true
```

Frontend:

```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1
```

Deploy Backend وFrontend من جديد.

## 10.5 Final domain test

جرب:

```text
https://api.yourdomain.com/health
```

ثم:

```text
https://app.yourdomain.com
```

Login.

---

# 10.5) Live Delivery Database (V3)

V3 ما كتخزنش غير آخر delivery status. PostgreSQL فيها:

```text
delivery_shipments       = current shipment snapshot
delivery_events          = immutable webhook/status history
delivery_status_mappings = Digylog external status ID → platform status
delivery_destinations    = city/hub/fee/delay data when synced/imported
delivery_sync_runs       = reconciliation/sync history
integration_configs      = Digylog/Sheets configuration + encrypted secrets
integration_events       = API/webhook troubleshooting log
```

من Admin sidebar افتح **Live Delivery** باش تشوف:

- Confirmed
- Sent to delivery
- In delivery
- Delivered
- Refused
- Returned
- Issues
- Dispatch Rate
- Confirmed → Delivered Rate
- Refusal / Return rates
- Product-by-product delivery performance
- Agent-by-agent delivery quality
- Latest shipments
- Latest webhook events
- Unmatched events count

أول مرة بعد deployment، Live Delivery → **Seed Status Mappings**. Seed كيدخل mappings التاريخية المستعملة من integration القديمة، ويمكن تعديل mapping من API/Admin لاحقاً إذا Digylog V3 عطاك official status names مختلفة.

> Important: current Seller API path/version varies between the older working integration and the public V3 Postman publication. Keep `API Base URL`, `Orders URL`, and `Test URL` configured from Admin; do not assume every account uses the same endpoint path.

# 11) ربط Digylog — Click by Click

## 11.1 قبل الربط

خاصك:

```text
Digylog Seller API token
```

الـpublic Postman documentation كتوثق API، ولكن مكان استخراج token داخل Digylog account يقدر يختلف حسب account/version. إلا ما عندكش token ظاهر فseller account، طلب من Digylog support/sales **Seller API token** ديالك.

## 11.2 Product mapping أولاً

Platform:

1. Sidebar → `Products`.
2. Click `Edit` على product.
3. فـ`Delivery Product Ref / Digylog Designation` دخل designation اللي بغيت يمشي لـDigylog.
4. `Save Changes`.

مثال:

```text
NOVAMAN
```

## 11.3 Add Digylog Integration

Platform:

1. Sidebar → `Integrations`.
2. Click `+ Connect Digylog`.
3. `Connection Name`: مثلاً `Digylog Morocco`.
4. `Platform Store`: اختار store.
5. `Digylog API Token`: paste token.
6. `Digylog Store ID / Ref`: دخل store reference ديالك إذا Digylog setup ديالك كيطلبها.
7. `Network`: default `1` إلا Digylog ما عطاكش value أخرى.
8. `Shipping Fee (port)`:
   - `1 — Customer pays`
   - `2 — Seller pays`
9. `After Create`:
   - `1 — Create & send`
   - `0 — Create only`
10. خليه `Ask Digylog to check duplicates` مفعّل إلا بغيت duplicate check.
11. Orders API URL default:

```text
https://api.digylog.com/api/v2/seller/orders
```

12. Click `Save Digylog`.

API token كيتخزن encrypted فdatabase؛ frontend ما كيرجعوش من بعد save.

## 11.4 Test Connection

Integrations table → Digylog → `Test`.

Expected:

```text
SUCCESS
Digylog connection succeeded
```

إلا جا 401/403:

- راجع token.
- راجع واش token Seller API صالح.
- راجع Digylog account/API permissions.

## 11.5 Digylog Webhook

Integrations → Digylog → `Webhook`.

غادي يبان URL بحال:

```text
https://api.yourdomain.com/api/v1/integrations/digylog/INTEGRATION_ID/webhook?token=SECRET_TOKEN
```

Click `Copy Webhook`.

هاد URL **private**؛ ما تحطوش فGitHub ولا public docs.

داخل Digylog، سجل هاد URL كـstatus webhook/callback. الـplatform كتفهم event:

```text
order-status-changed
```

وتستقبل POST أو PUT.

إلا Digylog dashboard ديالك ما فيهش webhook registration UI واضح، صيفط URL لـDigylog support وطلب منهم يربطوه بـSeller API order status callback. أسماء menus داخل Digylog يمكن تختلف حسب version/account، لذلك ما نفترضوش menu غير موثق.

## 11.6 Test Order → Digylog

Platform:

1. Orders.
2. `+ Manual Order`.
3. اختار نفس store المرتبط بـDigylog.
4. اختار product.
5. دخل test customer data صالح.
6. Create Order.
7. Confirm order.
8. من Actions click `Send Digylog`.

أو Agent:

1. Agent Workspace.
2. Confirmed order.
3. Click `Send Digylog`.

إذا نجح:

```text
Delivery Status = DISPATCHED
Provider = DIGYLOG
Tracking = tracking returned by Digylog
```

Integrations → Recent Integration Events غادي يوري:

```text
CREATE_ORDER
SUCCESS
```

إلا وقع error، نفس table كيعطيك message باش تعرف السبب.

## 11.7 Delivery status updates

منين Digylog يبعت `order-status-changed` webhook:

```text
Digylog
   ↓
Webhook
   ↓
DeliveryShipment
   ↓
Order Delivery Status
   ↓
Dashboard Analytics
```

Call status وDelivery status بقاو منفصلين عمداً.

---

# 12) ربط Google Sheets — Click by Click

هاد integration كيخلي Sheet تبعت leads للplatform أوتوماتيكياً.

## 12.1 حضّر Products أولاً

كل SKU فالSheet خاص يطابق SKU فالplatform.

مثال platform:

```text
NOVAMAN2026
```

Sheet:

```text
SKU = NOVAMAN2026
```

المطابقة case-insensitive فالإصدار الحالي.

إلا Sheet كاملة product واحد، تقدر تختار `Default Product` فالintegration وتخلي SKU فارغ.

## 12.2 Minimum columns

الأقل:

```text
SKU
FULL NAME
PHONE NUMBER
```

Supported aliases كذلك:

SKU:

```text
SKU
Product SKU
Lineitem sku
Variant SKU
```

Customer:

```text
FULL NAME
Full Name
Name
Customer Name
Shipping Name
```

Phone:

```text
PHONE NUMBER
Phone Number
Phone
Mobile
Shipping Phone
```

Optional:

```text
CITY
ADDRESS
QUANTITY
TOTAL PRICE MAD
PRODUCT NAME
SHOPIFY ORDER ID
NOTE
```

## 12.3 Add Google Sheets integration

Platform:

1. Sidebar → `Integrations`.
2. Click `+ Connect Google Sheets`.
3. `Connection Name`: `Google Sheets Leads`.
4. `Platform Store`: اختار store.
5. `Google Sheet Tab Name`: الاسم بالضبط ديال tab لتحت، مثلاً:

```text
Leads
```

6. `Default Product`: optional.
7. `Smart auto-assign`: خليه on إذا بغيت leads يمشيو أوتوماتيكياً للagents eligible.
8. Click `Save & Generate Script`.

غادي يفتح modal فيه:

```text
Webhook URL
Apps Script
```

## 12.4 Copy Apps Script

Click:

```text
Copy Full Apps Script
```

## 12.5 Google Sheet → Apps Script

1. افتح Google Sheet.
2. Menu فوق → `Extensions`.
3. Click `Apps Script`.
4. Google يفتح script editor.
5. مسح code الافتراضي كامل.
6. Paste code اللي نسخت من platform.
7. Click `Save`.

الكود generated فيه webhook URL/token ديال integration ديالك، لذلك **ما تشاركوش public**.

## 12.6 Run أول test يدوي

فـApps Script editor:

1. من function dropdown اختار:

```text
sendNewLeadsToCallCenter
```

2. Click `Run`.
3. أول مرة Google غادي يطلب authorization.
4. `Review permissions`.
5. اختار Google account اللي عندو access للSheet.
6. وافق على permissions المطلوبة.

Apps Script كيستعمل `UrlFetchApp` باش يدير HTTPS POST للbackend.

## 12.7 Check Sheet result

Script كيزيد أوتوماتيكياً columns:

```text
CALL CENTER IMPORT STATUS
CALL CENTER ORDER ID
CALL CENTER IMPORT ERROR
```

Successful row:

```text
CALL CENTER IMPORT STATUS = IMPORTED
CALL CENTER ORDER ID = CC-...
CALL CENTER IMPORT ERROR = blank
```

إلا وقع error مثلاً:

```text
Product SKU not found: ABC123
```

صلح SKU فالplatform أو Sheet، ومن بعد run script من جديد.

## 12.8 Install automatic 1-minute trigger

فـApps Script:

1. Function dropdown.
2. اختار:

```text
installEveryMinuteTrigger
```

3. Click `Run` مرة وحدة.

هاد function كيخلق time-driven trigger كيستدعي importer كل دقيقة.

من بعد ما تديرو، ما خاصكش تبقى Run يدوي.

## 12.9 Verify trigger

Apps Script left sidebar → clock icon / `Triggers`.

خاص تشوف trigger للفنكسيون:

```text
sendNewLeadsToCallCenter
```

Time-driven.

## 12.10 Stop integration مؤقتاً

عندك جوج طرق:

Platform:

```text
Integrations → Google Sheets → Disable
```

أو Apps Script:

Run:

```text
removeCallCenterTriggers
```

---

# 13) Daily workflow من بعد setup

## Admin

```text
Dashboard
↓
Orders
↓
Products
↓
Stores
↓
Agents
↓
Payments
↓
Callbacks
↓
Integrations
```

## Lead flow

```text
Google Sheet / Manual Order
        ↓
      NEW
        ↓
Agent Assignment
        ↓
Call Attempt
        ↓
CONFIRMED
        ↓
Payout Entry Created
        ↓
Send Digylog
        ↓
DISPATCHED
        ↓
Digylog Webhook
        ↓
DELIVERED / REFUSED / RETURNED / ...
```

---

# 14) Agent Payment الصحيح

كل confirmation كتخلق ledger entry.

مثال:

```text
Sara   = 195 MAD UNPAID
Ahmed  = 135 MAD UNPAID
```

Admin:

1. Payments.
2. Sara.
3. `Pay Agent`.
4. Payment method.
5. Confirm.

Result:

```text
Sara   = 0 MAD unpaid
Ahmed  = 135 MAD unpaid
```

History ديال Sara ما كيتمسحش.

ما تستعملش concept ديال global reset.

---

# 15) Manual Order

Admin → Orders → `+ Manual Order`.

دخل:

```text
Store
Product
Customer Name
Phone
City
Address
Quantity
Price
Assigned Agent optional
Initial Status
Note
```

Create.

من بعد order كتدخل لنفس workflow بحال Sheet lead.

---

# 16) Today / Yesterday / Product / Agent data

Dashboard فيه date ranges:

```text
Today
Yesterday
Last 7 Days
Last 30 Days
This Month
Last Month
Custom
```

وكيفصل analytics:

```text
Product by Product
Agent by Agent
Confirmed Revenue
Delivered Revenue
Confirmation Rate
Delivery Rate
Refused / Returned
Payout Due
```

---

# 17) GitHub automatic validation

Repo فيه:

```text
.github/workflows/ci.yml
```

كل push/PR GitHub Actions كيدير:

```text
Backend:
- install Python dependencies
- pytest

Frontend:
- install npm dependencies
- next build
```

GitHub:

1. Repository.
2. Tab `Actions`.
3. Workflow `CI`.
4. تأكد backend وfrontend بجوج خضر.

ما تديرش production deployment على commit CI ديالو حمر إلا فهمتي السبب وصلحتو.

---

# 18) Production security checklist

قبل ما تستعمل real customer data:

- [ ] GitHub repo Private إلا ما عندكش سبب يكون public.
- [ ] `.env` ما كايناش فGitHub.
- [ ] `ADMIN_PASSWORD` قوي ومختلف.
- [ ] `POSTGRES_PASSWORD` قوي.
- [ ] `APP_SECRET` طويل ومخزن فمكان آمن.
- [ ] ما تبدلش `APP_SECRET` بعد integrations إلا كنت ناوي تعاود تدخل tokens.
- [ ] `COOKIE_SECURE=true` فproduction.
- [ ] `CORS_ORIGINS` فيه غير frontend domain ديالك.
- [ ] `PUBLIC_API_BASE_URL` هو HTTPS backend domain.
- [ ] `NEXT_PUBLIC_API_URL` هو HTTPS backend `/api/v1`.
- [ ] Digylog webhook URL/token ما تنشروش.
- [ ] Generated Google Apps Script ما تنشروش لأنه فيه private webhook token.
- [ ] كل Agent عندو username/password ديالو.
- [ ] Disable agents اللي ما بقاش كيخدمو.
- [ ] راقب Railway/Postgres backups حسب plan ديالك.

---

# 19) Troubleshooting — أسرع تشخيص

## Frontend opens ولكن Login كيعطي Network Error

Check Backend:

```text
https://api.yourdomain.com/health
```

إلا ما خدمش، المشكل Backend/domain ماشي frontend.

راجع:

```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1
```

ثم redeploy Frontend.

---

## Login 401

راجع:

```env
ADMIN_USERNAME
ADMIN_PASSWORD
```

**مهم:** seed كيخلق owner إلا ما كانش موجود. تغيير `ADMIN_PASSWORD` environment من بعد ما owner تخلق ما كيبدلش password الموجودة تلقائياً. اختار owner password الصحيح **قبل أول production deploy**.

---

## Browser CORS error

Backend variable لازم يكون frontend origin exact:

```env
CORS_ORIGINS=https://app.yourdomain.com
```

بدون `/` فالآخر.

Deploy Backend من جديد.

---

## Cookies/Login ما كيبقاش production

راجع:

```env
COOKIE_SECURE=true
```

واستعمل HTTPS فقط.

Frontend fetch أصلاً مبرمج بـ:

```text
credentials: include
```

---

## Railway database connection error

Backend:

```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

الbackend كيحوّل `postgresql://` Railway URL أوتوماتيكياً لـpsycopg SQLAlchemy URL.

---

## APP_SECRET changed / integrations cannot decrypt

Message محتمل:

```text
Integration secrets cannot be decrypted. APP_SECRET may have changed.
```

الحل الصحيح هو رجّع نفس `APP_SECRET` القديم.

إلا ضاع نهائياً، خاصك تعاود إنشاء integrations وتدخل API tokens من جديد.

---

## Digylog Test = 401 / 403

راجع:

- Seller API token.
- API permission.
- Token ما فيهش spaces قبل/بعد.
- Account/store/network config.

Integrations → Recent Integration Events.

---

## Digylog says accepted but no tracking

Platform غادي تسجل failed event مع response/error.

راجع:

- Product `Delivery Product Ref`.
- Customer phone.
- City/address.
- Digylog store/network/port.
- Digylog seller dashboard.

ما تعاودش dispatch عشوائياً إلا تأكدتي أن Digylog ما خلقش shipment، باش ما تديرش duplicate حقيقي.

---

## Send Digylog button says no active integration

لازم:

```text
Order Store == Digylog Integration Store
```

ثم:

```text
Integrations → Digylog → ACTIVE
```

---

## Google Sheet row ما دخلاتش

Check columns:

```text
FULL NAME
PHONE NUMBER
SKU
```

Check:

```text
CALL CENTER IMPORT ERROR
```

Check Integrations → Recent Events.

---

## Google Sheets Product SKU not found

مثال:

```text
Product SKU not found: ABC123
```

الحل:

1. Products.
2. تأكد product مرتبط بنفس Store ديال integration.
3. تأكد SKU صحيح.

أو اختار `Default Product` فالGoogle Sheets integration.

---

## Google Apps Script HTTP 401

غالباً webhook token القديم/غلط.

الحل الأسهل:

1. Platform → Integrations.
2. Google Sheets.
3. `Apps Script`.
4. Copy script الجديد كامل.
5. بدّل script القديم فGoogle Apps Script.
6. Save.
7. Run `sendNewLeadsToCallCenter`.

---

## Google script ما كيرنش كل دقيقة

Apps Script:

1. Run `installEveryMinuteTrigger` مرة أخرى.
2. Open Triggers.
3. تأكد `sendNewLeadsToCallCenter` موجود.

Google installable time-driven triggers يمكنهم الخدمة كل دقيقة.

---

## Custom domain gives 404 even CNAME is correct

Railway custom domains كيتطلبو CNAME **وTXT verification record** بجوج.

راجع Railway → Service → Settings → Public Networking، ونسخ records exact.

DNS propagation ممكن تاخذ وقت.

---

# 20) كيفاش تدير update للplatform من بعد

من بعد أي تعديل محلي:

```bash
git add .
git commit -m "Describe the update"
git push
```

Railway services المرتبطين بنفس repo يقدرو يديرو redeploy من GitHub source.

راقب GitHub Actions وRailway Deploy Logs.

---

# 21) Backup قبل تغييرات كبيرة

قبل migrations كبيرة أو تغيير integrations:

- خذ backup/snapshot لـPostgres حسب Railway plan/settings ديالك.
- ما تمسحش production database باش تصلح UI issue.
- payout history وdelivery history خاصهم يبقاو persistent.

---

# 22) Final Launch Checklist

## GitHub

- [ ] Repo uploaded.
- [ ] `.env` absent.
- [ ] CI backend green.
- [ ] CI frontend green.

## Railway Backend

- [ ] `/backend` root directory.
- [ ] Postgres connected.
- [ ] `DATABASE_URL` set.
- [ ] `APP_SECRET` set.
- [ ] `ADMIN_PASSWORD` set before first seed.
- [ ] `COOKIE_SECURE=true`.
- [ ] CORS correct.
- [ ] `/health` returns ok.

## Railway Frontend

- [ ] `/frontend` root directory.
- [ ] `NEXT_PUBLIC_API_URL` correct.
- [ ] Login works.

## Domain

- [ ] `app.domain.com` verified.
- [ ] `api.domain.com` verified.
- [ ] HTTPS works.
- [ ] Railway CNAME + TXT both present.

## Platform

- [ ] Store correct.
- [ ] Products added.
- [ ] Delivery Product Ref set.
- [ ] Agents added.
- [ ] Allowed products selected.
- [ ] Manual order tested.
- [ ] Payment agent-by-agent tested.

## Digylog

- [ ] API token saved.
- [ ] Connection Test success.
- [ ] Webhook registered.
- [ ] One controlled test order dispatched.
- [ ] Tracking appears.
- [ ] Status webhook appears in Integration Events.

## Google Sheets

- [ ] Integration created.
- [ ] Sheet tab name correct.
- [ ] Apps Script pasted.
- [ ] Manual import test success.
- [ ] IMPORTED + Order ID written back.
- [ ] 1-minute trigger installed.

إذا هاد checklist كاملة خضرا، platform الأساسية production-ready من ناحية setup/configuration flow.

---

# Official references

GitHub repository creation:

`https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository`

Railway monorepo/root directories:

`https://docs.railway.com/deployments/monorepo`

Railway PostgreSQL:

`https://docs.railway.com/databases/postgresql`

Railway variables:

`https://docs.railway.com/variables`

Railway custom domains:

`https://docs.railway.com/networking/domains/working-with-domains`

Google Apps Script UrlFetch:

`https://developers.google.com/apps-script/reference/url-fetch`

Google Apps Script installable triggers:

`https://developers.google.com/apps-script/guides/triggers/installable`

Digylog Seller API Postman documentation:

`https://documenter.getpostman.com/view/20928347/2sBXqNoKfH`

---

## V4 — English / Arabic and UI preview

The V4 frontend is bilingual from one codebase.

1. Open the login page.
2. Use `EN / ع` in the top corner.
3. English uses LTR.
4. العربية automatically switches the complete application to RTL.
5. The selection is saved in the browser and remains after logout/reload.

The same switch is available in the authenticated top bar. Products, customers and other database content are not duplicated; only the interface language changes.

### Optional preview/sample dataset

Use this only on a fresh development or staging database if you want to see populated dashboards before connecting real leads:

```bash
cd backend
python -m app.demo_seed
```

This creates 2 demo products, 2 demo agents and 30 demo orders. It never runs automatically.

Preview agent credentials:

```text
username: demo.sara
password: DemoPass123!
```

Do not keep demo credentials on a production database.

For design tokens and responsive/RTL details, see `docs/DESIGN_BILINGUAL_V4.md`.
