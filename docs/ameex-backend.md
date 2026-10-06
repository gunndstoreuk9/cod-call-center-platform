# AMEEX backend integration

The backend supports `AMEEX` through existing integration configuration and delivery tables. No database migration or frontend change is included. Implementation follows the API specification supplied on 6 October 2026.

## Configure in the backend

Use an OWNER/ADMIN session in `/docs`, or the existing authenticated API client:

```json
POST /api/v1/integrations
{
  "provider": "AMEEX",
  "name": "AMEEX Morocco",
  "store_id": "YOUR_STORE_ID",
  "secrets": {
    "client_id": "YOUR_C_API_ID",
    "api_key": "YOUR_TEST_OR_LIVE_KEY",
    "webhook_secret": "SECRET_FROM_AMEEX_KEYS_AND_WEBHOOK"
  }
}
```

Enter real credentials only in the platform's authenticated settings/API. Credentials are encrypted using the existing APP_SECRET mechanism. Keep APP_SECRET stable across deployments. The API host is fixed to https://api.ameex.app/customer; redirects are disabled so credentials cannot be forwarded to another host.

1. Start with a `test_` key and an AMEEX webhook secret.
2. POST `/api/v1/integrations/{id}/test` to authenticate and sync cities.
3. GET `/api/v1/integrations/{id}/webhook-config`; register its URL in AMEEX and enable signing with the same webhook secret.
4. Dispatch a confirmed test order using an endpoint below. Confirm its code in AMEEX and exercise a sandbox status callback.
5. Configure a separate live integration, disable the sandbox integration before default dispatch, and use live credentials after sandbox validation.

Set PUBLIC_API_BASE_URL to the externally reachable backend origin before copying the webhook URL. Backend Swagger is `/docs`; existing admin UI does not yet have an AMEEX connection form or dispatch button.

## Platform endpoints

All paths below have prefix `/api/v1/integrations`.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/ameex/{id}/dispatch/{order_id}` | Create SIMPLE parcel for a confirmed order |
| POST | `/ameex/dispatch/{order_id}` | Select exactly one active AMEEX connection for the order's store |
| POST | `/ameex/{id}/sync-cities` | Store city IDs and names |
| GET | `/ameex/{id}/statuses` | Return carrier status catalog |
| GET | `/ameex/{id}/tracking/{code}` | Return carrier tracking response |
| POST | `/ameex/{id}/mass-tracking` | Bulk tracking; JSON array of 1–100 codes |
| POST | `/ameex/{id}/mass-info` | Bulk info; JSON array of 1–100 codes |
| POST | `/ameex/{id}/webhook` | Receive signed form-encoded callback |

City names or previously synced IDs resolve to the current integration's city catalog. COD is the order total, product text includes quantity, and `order_num` is the platform order number. Carrier requests use form encoding and C-Api-Id / C-Api-Key headers. Tracking reads return carrier data; order updates occur through verified callbacks.

## Webhooks and retries

The backend requires signing; unsigned callbacks are rejected. It verifies HMAC-SHA256 of `timestamp + "." + raw body` using X-Ameex-Signature, with a 5-minute timestamp tolerance. Sandbox callbacks are accepted only for a test key. Matching uses integration ID plus parcel code; repeated identical callbacks do not duplicate order history. Unknown statuses remain inspectable without changing the order's internal status. IN_PROGRESS currently maps to IN_TRANSIT; sub-status fields are retained in raw event data.

Dispatch locks the order in PostgreSQL and blocks another active/unknown AMEEX shipment. An unsuccessful parcel request is recorded as UNKNOWN because a timeout or malformed response may still have created a parcel remotely. Do not automatically retry: reconcile in AMEEX and attach its tracking code or resolve the uncertain shipment before dispatching again.

## Verification limits

The supplied specification does not include JSON response examples or the complete status catalog. The implementation accepts city arrays in CITIES/cities/data/DATA envelopes and city entries with ID/id, NAME/name. It recognizes PARCEL_CODE, parcel_code, ParcelCode, or CODE in parcel responses. These formats are covered by mocked tests, not confirmed against AMEEX sandbox. Obtain sanitized city/create/status response examples and run a sandbox smoke test before production. Request body encoding should also be confirmed by that smoke test.

Run: `cd backend && python -m pytest tests/test_ameex.py tests/test_integrations.py -q`.
