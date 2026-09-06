# V3 Delivery / Digylog Database

## Why this schema exists

The platform separates call-center confirmation state from delivery state and keeps the complete delivery history. Webhooks never overwrite history; they append `delivery_events` and update the current snapshot in `delivery_shipments` and `orders.delivery_status`.

## Tables

### delivery_shipments
Current shipment snapshot per order/provider.

Key fields:
- `order_id`
- `integration_id`
- `provider`
- `external_id`
- `external_reference`
- `tracking_number`
- `barcode`
- `external_status_id`
- `external_status_name`
- `status` (internal normalized status)
- `cod_amount`
- `delivery_fee`
- `destination_city`
- `hub`
- `accepted_at`
- `first_attempt_at`
- `delivered_at`
- `refused_at`
- `returned_at`
- `last_synced_at`
- `retry_count`
- `last_attempt_at`
- `payload` (raw create/latest payload)
- `error`

### delivery_events
Append-only delivery timeline.

Key fields:
- `shipment_id`, `order_id`, `integration_id`
- `event_type`
- `external_order_number`
- `tracking_number`
- `external_status_id`, `external_status_name`
- `internal_status`
- `event_at`, `received_at`
- `matched`, `processed`, `processing_error`
- `raw_payload`

Unmatched webhooks are retained with `matched=false` instead of being dropped.

### delivery_status_mappings
Configurable external status normalization.

- `provider`
- `external_status_id`
- `external_status_name`
- `internal_status`
- `is_final`
- `is_success`
- `is_active`

### delivery_destinations
Provider city/coverage cache.

- `integration_id`
- `external_city_id`
- `city_name`
- `hub`
- `fee`
- `min_days`, `max_days`
- `is_active`
- `raw_payload`
- `last_synced_at`

### delivery_sync_runs
Audit trail for reconciliation/sync jobs.

- `integration_id`
- `sync_type`
- `status`
- `scanned_count`
- `updated_count`
- `error_count`
- `details`, `error`
- `started_at`, `finished_at`

### integration_configs / integration_events
Integration configuration/secrets and raw troubleshooting events.

## Order statuses

Call-center and delivery statuses are intentionally separate:

```text
orders.call_status     = NEW / CALLBACK / CONFIRMED / CANCELLED / ...
orders.delivery_status = NOT_READY / READY / DISPATCHED / IN_TRANSIT / DELIVERED / REFUSED / RETURNED / CANCELLED / ISSUE
```

## Migration

Alembic revision:

```text
0003_full_delivery
```

Run:

```bash
cd backend
alembic upgrade head
```
