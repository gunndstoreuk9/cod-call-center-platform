"""Reconcile a Google Sheet CSV export against the database.

READ-ONLY by default (every row is imported inside a savepoint that is rolled back).
Pass --apply to actually insert genuinely missing rows; already-imported rows are matched by
external order id and never touched, so the run is idempotent.

    python -m scripts.reconcile_sheet --integration-id <id> --csv orders.csv [--apply]

Output contains counts and row numbers only (no names, phones or addresses).
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter

from app.core.db import SessionLocal
from app.models import IntegrationConfig
from app.services.google_sheets import import_sheet_order

ALIASES = {
    "sku": ["SKU", "Product SKU", "Lineitem sku", "Variant SKU"],
    "customer_name": ["FULL NAME", "Full Name", "First Name", "Name", "Customer Name", "Shipping Name"],
    "phone": ["PHONE NUMBER", "Phone Number", "Phone", "Mobile", "Shipping Phone"],
    "city": ["CITY", "City", "Shipping City"],
    "address": ["ADDRESS", "Address", "Shipping Address", "Address1"],
    "quantity": ["QUANTITY", "Quantity", "Product Quantity", "Qty", "Lineitem quantity"],
    "total_price": ["TOTAL PRICE MAD", "Total Price MAD", "Total Price", "Total", "Price", "Amount"],
    "external_order_id": ["SHOPIFY ORDER ID", "Shopify Order ID", "Order ID", "Order Number", "Order Name"],
    "note": ["NOTE", "Note", "Notes"],
    "lead_date": ["DATE", "Date", "Created At", "Created", "Timestamp", "Order Date", "Date Created", "Created Time", "Lead Date"],
}


def _get(row: dict, key: str) -> str:
    lowered = {k.strip().lower(): v for k, v in row.items() if k}
    for alias in ALIASES[key]:
        if alias.lower() in lowered:
            return str(lowered[alias.lower()] or "").strip()
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--integration-id", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--sheet-name", default="orders")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rows", help="comma-separated sheet row numbers to process (e.g. 154,155); default: all rows")
    args = ap.parse_args()

    db = SessionLocal()
    integration = db.query(IntegrationConfig).filter(IntegrationConfig.id == args.integration_id, IntegrationConfig.provider == "GOOGLE_SHEETS").first()
    if not integration:
        raise SystemExit("integration not found")

    only_rows = {int(x) for x in args.rows.split(",")} if args.rows else None
    counts: Counter = Counter()
    reasons: Counter = Counter()
    failed_rows: dict[str, list[int]] = {}
    seen_ids: Counter = Counter()
    with open(args.csv, newline="", encoding="utf-8-sig") as fh:
        for n, raw in enumerate(csv.DictReader(fh), start=2):
            if only_rows and n not in only_rows:
                continue
            phone, name = _get(raw, "phone"), _get(raw, "customer_name")
            if not phone or not name:
                counts["skipped_missing_phone_or_name"] += 1
                continue
            ext = _get(raw, "external_order_id")
            if ext:
                seen_ids[ext] += 1
            total = _get(raw, "total_price")
            try:
                qty = max(int(float(_get(raw, "quantity") or 1)), 1)
                total_v = float(total) if total else None
            except ValueError:
                counts["invalid_record"] += 1
                reasons["bad quantity/price"] += 1
                continue
            item = {"row_number": n, "sku": _get(raw, "sku"), "customer_name": name, "phone": phone, "city": _get(raw, "city"),
                    "address": _get(raw, "address"), "quantity": qty, "total_price": total_v, "external_order_id": _get(raw, "external_order_id"), "lead_date": _get(raw, "lead_date"), "note": _get(raw, "note")}
            sp = db.begin_nested()
            try:
                result = import_sheet_order(db, integration, item)
            except Exception as exc:  # noqa: BLE001
                result = {"status": "ERROR", "error": f"{type(exc).__name__}"}
            if result["status"] == "ERROR":
                sp.rollback()
                counts["failed"] += 1
                reasons[str(result["error"])[:60]] += 1
                failed_rows.setdefault(str(result["error"])[:60], []).append(n)
            elif result.get("duplicate"):
                sp.rollback()
                counts["already_imported"] += 1
            else:
                counts["inserted" if args.apply else "would_insert"] += 1
                if args.apply:
                    sp.commit()
                else:
                    sp.rollback()
    if args.apply:
        db.commit()
    else:
        db.rollback()
    counts["duplicate_ids_in_sheet"] = sum(1 for v in seen_ids.values() if v > 1)
    print(json.dumps({"apply": args.apply, "counts": counts, "failure_reasons": reasons,
                      "sample_failed_rows": {k: v[:15] for k, v in failed_rows.items()}}, indent=2))


if __name__ == "__main__":
    main()
