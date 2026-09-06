# COD Call Center Platform — V4 Bilingual

GitHub-ready COD call-center platform built with **Next.js + FastAPI + PostgreSQL + Alembic**.


## V4 UI / language

- Premium compact operations UI (navy / blue / green / amber / red semantic palette)
- English + Arabic from one codebase
- Real RTL/LTR layout switching from login and top bar
- Bilingual Admin, Live Delivery, Integrations and Agent Workspace
- Optional preview dataset: `python -m app.demo_seed`
- Design details: `docs/DESIGN_BILINGUAL_V4.md`

## V3 — Full Digylog delivery data + Google Sheets included

### Admin
- Dashboard: Today / Yesterday / Last 7 / Last 30 / This Month / Last Month / Custom dates
- Product-by-product analytics
- Agent-by-agent analytics
- Stores management
- Add/Edit/Enable/Disable products — no hard-coded SKU
- Delivery Product Ref / Digylog designation per product
- Add/Enable/Disable agents + allowed products
- Manual orders
- Smart assignment
- Call history + callbacks
- Agent payout ledger
- Pay/reset **one agent only**, permanent payment history
- Digylog integration settings in Admin UI
- Digylog connection test
- Digylog dispatch from Admin Orders and Agent Workspace
- Digylog tracking + full delivery webhook history
- Live Delivery dashboard: sent / in delivery / delivered / refused / returned / cancelled / issues
- Product-by-product and agent-by-agent delivery quality/rates
- Delivery status mapping table (external Digylog ID → internal status)
- Unmatched webhook event storage for later reconciliation
- Delivery destinations/cities/hub/fee schema
- Delivery sync-run/reconciliation schema
- Google Sheets integration settings in Admin UI
- Generated Google Apps Script with private webhook token
- Google Sheets row import + status/order/error write-back
- Integration event log for troubleshooting
- Encrypted integration secrets in PostgreSQL

### Agent
- Assigned queue
- New / Follow-up / Confirmed / All
- Call outcomes
- Callback scheduler
- Phone + WhatsApp shortcuts
- Send confirmed orders to Digylog
- Personal stats and unpaid earnings

## Full A-to-Z setup guide

**Start here:** [`docs/SETUP_A_TO_Z.md`](docs/SETUP_A_TO_Z.md)

It covers click-by-click:

```text
ZIP
→ Local Docker test
→ GitHub
→ Railway PostgreSQL
→ Railway Backend
→ Railway Frontend
→ Domain + HTTPS
→ First platform setup
→ Digylog
→ Google Sheets
→ Tests
→ Troubleshooting
→ Launch checklist
```

## Quick local start

```bash
cp .env.example .env
```

Change passwords and `APP_SECRET`, then:

```bash
docker compose up --build
```

Open:

- Frontend: `http://localhost:3000`
- Backend health: `http://localhost:8000/health`
- Swagger: `http://localhost:8000/docs`

## Critical production environment variables

Backend:

```env
DATABASE_URL=...
CORS_ORIGINS=https://app.yourdomain.com
COOKIE_SECURE=true
ADMIN_USERNAME=owner
ADMIN_PASSWORD=...
APP_SECRET=...
PUBLIC_API_BASE_URL=https://api.yourdomain.com
```

Frontend:

```env
NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api/v1
```

> Do not change `APP_SECRET` after integrations are saved unless you intend to re-enter their API/webhook secrets.

## Full delivery database

V3 stores Digylog operational data in dedicated PostgreSQL tables:

```text
delivery_shipments
delivery_events
delivery_status_mappings
delivery_destinations
delivery_sync_runs
integration_configs
integration_events
```

`delivery_events` is append-only history: a new webhook status creates a new event instead of destroying previous delivery history.

## Integration API highlights

```text
GET    /api/v1/integrations
POST   /api/v1/integrations
PATCH  /api/v1/integrations/{id}
POST   /api/v1/integrations/{id}/test
GET    /api/v1/integrations/events
GET    /api/v1/integrations/google-sheets/{id}/script
POST   /api/v1/integrations/google-sheets/{id}/webhook
POST   /api/v1/integrations/digylog/dispatch/{order_id}
POST   /api/v1/integrations/digylog/{id}/dispatch/{order_id}
POST/PUT /api/v1/integrations/digylog/{id}/webhook

GET    /api/v1/delivery/dashboard
GET    /api/v1/delivery/shipments
GET    /api/v1/delivery/events
GET    /api/v1/delivery/unmatched
GET    /api/v1/delivery/status-mappings
POST   /api/v1/delivery/status-mappings/seed-digylog
GET    /api/v1/delivery/destinations
GET    /api/v1/delivery/sync-runs
GET    /api/v1/delivery/health
```

## Security model

- Argon2 password hashing
- DB-backed sessions
- HttpOnly session cookie
- Secrets encrypted before storage using a key derived from `APP_SECRET`
- Integration API tokens are not returned in normal list responses
- Webhooks use private per-integration tokens
- Audit/integration event logs retained

## Tests

Backend:

```bash
cd backend
pytest -q
```

Current suite includes:

- Agent-specific payout settlement
- Date analytics
- Phone normalization
- Google Sheets integration/import
- Digylog secret/webhook protection
- Digylog live webhook → delivery event → shipment/order status → delivery dashboard

GitHub Actions additionally installs frontend dependencies and runs `next build` on push/PR.
