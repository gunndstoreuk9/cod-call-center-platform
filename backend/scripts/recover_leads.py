"""Idempotent recovery of historical sheet leads as GOOGLE_SHEETS_RECOVERY orders.

Safe by construction:
  * DRY RUN by default (everything happens inside a transaction that is rolled back).
  * --apply additionally requires --confirm-batch <batch id> that matches the batch id inside the input file.
  * Leads are created NEW and UNASSIGNED; no agent is ever picked.
  * Existing orders / customers are never modified: a lead that already exists returns DUPLICATE and is skipped.
  * created_at is the real recovery time (never backdated); the unknown submission date is recorded as "unknown".
  * Provenance (spreadsheet id, tab, row, batch, recovered_at) is stored in the ORDER_IMPORT event; a note on the order.

Input (stdin, JSON list): [{sheet, row_number, sku, customer_name, phone, city, quantity, total_price, external_order_id, source:{spreadsheet_id, tab, ...}}]

    python -m scripts.recover_leads --batch 2026-11-06-25 < items.json                     # dry run
    python -m scripts.recover_leads --batch 2026-11-06-25 --apply --confirm-batch 2026-11-06-25 < items.json
Prints counts and row numbers only (no names, phones or addresses).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from types import SimpleNamespace

from sqlalchemy import text

from app.core.db import SessionLocal
from app.models import IntegrationConfig, Order
from app.services.google_sheets import import_sheet_order

MAX_ITEMS = 100
TABLES = (("orders", "id,order_number,external_order_id,customer_id,product_id,quantity,unit_price,total_price,call_status,assigned_agent_id,delivery_status,city,address,call_note,source"),
          ("customers", "id,name,phone_e164,city,address"), ("order_assignments", "id,order_id,agent_id"),
          ("payout_entries", "id,order_id,agent_id,amount,status"), ("delivery_shipments", "id,order_id,status"))


def _fingerprint(db) -> dict:
    import hashlib
    out = {}
    for table, cols in TABLES:
        rows = db.execute(text(f"select {cols} from {table} order by id")).all()
        out[table] = [hashlib.sha256(repr(rows).encode()).hexdigest()[:12], len(rows)]
    return out


def dashboard_probe(db) -> dict:
    """Key dashboard / profit figures for today, read through the real report functions (inside the caller's transaction)."""
    from app.api.routes import analytics, profit
    o = analytics.overview(range="today", from_date=None, to_date=None, db=db, _=None)
    keys = ("leads", "called", "confirmed", "confirmation_rate", "assigned", "unassigned", "recovered_leads", "recovered_unassigned", "recovered_confirmed", "confirmed_revenue", "confirmed_revenue_recovered", "delivered_revenue_recovered")
    p = profit.profit_dashboard(range="today", from_date=None, to_date=None, store_id=None, product_id=None, db=db, _=None)
    pk = ("leads", "confirmed", "cpa_confirmed", "cpa_delivered", "recovered_leads", "recovered_confirmed", "revenue", "revenue_recovered")
    return {"overview": {k: o[k] for k in keys}, "profit": {k: p[k] for k in pk}}


def run_recovery(db, items: list[dict], batch: str, apply: bool, integration_id: str | None = None, probe: bool = False) -> dict:
    if not items or len(items) > MAX_ITEMS:
        raise SystemExit(f"refusing: need 1..{MAX_ITEMS} items, got {len(items)}")
    q = db.query(IntegrationConfig).filter(IntegrationConfig.provider == "GOOGLE_SHEETS")
    real = q.filter(IntegrationConfig.id == integration_id).one() if integration_id else q.one()   # .one(): refuse if ambiguous
    # in-memory view of the integration: the production config is never modified
    integration = SimpleNamespace(id=real.id, store_id=real.store_id, config={**dict(real.config or {}), "auto_assign": False})
    for it in items:
        if not str(it.get("sku") or "").strip():
            raise SystemExit(f"refusing: row {it.get('row_number')} has an empty SKU (needs an explicit product decision)")
        if not it.get("row_number") or not (it.get("source") or {}).get("spreadsheet_id"):
            raise SystemExit(f"refusing: row {it.get('row_number')} lacks source spreadsheet id / row number")
    before = _fingerprint(db)
    probe_before = dashboard_probe(db) if probe else None
    outer = db.begin_nested()
    outcomes = []
    for raw in items:
        it = dict(raw)
        sheet = it.pop("sheet", "?")
        it["recovery"] = True
        it["source"] = {**it["source"], "recovery_batch": batch, "submitted_at": "unknown", "row": it["row_number"]}
        it["note"] = it.get("note") or f"RECOVERED historical lead - original submission date unknown. Source: spreadsheet {it['source']['spreadsheet_id'][:8]}... tab {it['source'].get('tab', '?')} row {it['row_number']}. Batch {batch}."
        sp = db.begin_nested()
        res = import_sheet_order(db, integration, it)
        if res.get("outcome") != "INSERTED":
            sp.rollback()          # nothing is kept for rows that are duplicates / rejected
        else:
            sp.commit()
        outcomes.append({"sheet": sheet, "row": it["row_number"], "outcome": res.get("outcome"), "error": res.get("error"), "existing": res.get("order_number") if res.get("outcome") == "DUPLICATE" else None})
    inserted = [o for o in outcomes if o["outcome"] == "INSERTED"]
    probe_after = dashboard_probe(db) if probe else None
    if apply:
        outer.commit()
        db.commit()
    else:
        outer.rollback()
        db.rollback()
    after = _fingerprint(db)
    recovered_now = db.query(Order).filter(Order.source == "GOOGLE_SHEETS_RECOVERY").count()
    return {"apply": apply, "batch": batch, "counts": dict(Counter(o["outcome"] for o in outcomes)), "outcomes": outcomes,
            "inserted": len(inserted), "orders_before": before["orders"][1], "orders_after": after["orders"][1],
            "recovered_orders_in_db": recovered_now,
            "dashboard_before": probe_before, "dashboard_after_inside_transaction": probe_after,
            "existing_rows_untouched": all(before[t][1] <= after[t][1] for t in before) and (apply or before == after)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-batch", default="")
    ap.add_argument("--integration-id", default=None)
    ap.add_argument("--probe", action="store_true", help="include today's dashboard/profit figures before and after (inside the same transaction)")
    args = ap.parse_args()
    if args.apply and args.confirm_batch != args.batch:
        raise SystemExit("refusing: --apply needs --confirm-batch equal to --batch")
    items = json.load(sys.stdin)
    db = SessionLocal()
    print("RECOVERY_JSON:" + json.dumps(run_recovery(db, items, args.batch, args.apply, args.integration_id, args.probe)))


if __name__ == "__main__":
    main()
