# V4 Design & bilingual UI

## Languages
- English: LTR
- العربية: RTL
- Switch language from the login screen or the top bar.
- The preference is stored in the browser (`cod_locale`). No separate database or duplicate application is required.
- Navigation, dashboards, forms, table headings, statuses, date filters, payment screens, integrations, Live Delivery, and agent workspace are bilingual.

## Visual system
The interface is designed as a compact operations console rather than a marketing dashboard.

- Navigation: deep navy `#0B1220`
- Primary action / selection: blue `#2563EB`
- Delivered / confirmed / healthy: green `#16A34A`
- Follow-up / pending / return: amber `#D97706`
- Error / refusal / cancellation: red `#DC2626`
- App background: `#F4F7FB`
- Cards: white `#FFFFFF`
- Primary text: `#0F172A`
- Muted text: `#64748B`
- Borders: `#E2E8F0`

Colors are semantic: red is not used decoratively, so an operator can scan problems quickly.

## Agent workflow
The agent view prioritizes:
1. Customer + phone
2. Product / quantity / COD value
3. Call outcomes
4. Callback scheduling
5. Phone / WhatsApp
6. Digylog dispatch after confirmation
7. Queue on the side

## Responsive behavior
- Desktop: sticky sidebar + compact top bar.
- Tablet: narrower sidebar and 2-column KPI cards.
- Mobile: navigation becomes a compact grid, forms become single-column, agent queue moves under the focused order.
- RTL uses logical CSS properties so sidebar/table/forms reverse correctly without a second stylesheet.

## Optional demo data
After the normal database migration and seed, you can populate a realistic preview dataset manually:

```bash
cd backend
python -m app.demo_seed
```

It adds 2 demo products, 2 demo agents and 30 demo orders with confirmed, delivery, refused, callback and no-answer states. It never runs automatically.

Demo agent (preview only):
- Username: `demo.sara`
- Password: `DemoPass123!`

Remove/change demo accounts before production.
