"""Reusable, idempotent importer for store order-export CSVs (source STORE_CSV_BACKFILL).

READ-ONLY by default. A normal run classifies every CSV row against production and imports the eligible rows inside a transaction
that is ROLLED BACK (dry run). Writing needs --apply AND --confirm-batch <same batch id>.

    python -m scripts.csv_backfill --batch 2026-11-06-csv                                   # classify + dry-run import (local files)
    python -m scripts.csv_backfill --batch ... --stdin-json < files.json                    # same, CSV text supplied on stdin (server use)
    python -m scripts.csv_backfill --batch ... --apply --confirm-batch ... [--include nabil:12,custom-blood:4]

Eligible = class NEW, plus NEEDS_REVIEW rows you explicitly name with --include store_key:csv_line. EXISTING / DUPLICATE / CONFLICT /
INVALID rows are never imported. Existing customers/orders are never modified; orders are NEW, UNASSIGNED, no shipment/payout.
Output has counts and masked data only (no names, no full phones).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from app.core.db import SessionLocal
from app.models import Order
from app.services.csv_backfill import CsvSpec, classify, import_row, load_existing, load_offers, parse_csv_text, resolve_store
from scripts.recover_leads import _fingerprint, dashboard_probe

DEFAULT_SPECS = [
    CsvSpec("custom-blood-orders-team.csv", "custom-blood", {"Custom Blood": "TOPLUX-BSC-940-60"}),
    CsvSpec("nabil-orders-team.csv", "nabil", {"NOVAMAN2026": "NOVAMAN2026"}),
]


def mask(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    return (d[:5] + "•••••" + d[-2:]) if len(d) >= 8 else "(invalid)"


def run(db, texts: dict[str, str], batch: str, apply: bool, include: set[tuple[str, int]], specs=DEFAULT_SPECS, probe: bool = True) -> dict:
    rows = []
    for sp in specs:
        rows += parse_csv_text(texts[sp.file_name], sp)
    store, products = resolve_store(db, {s for sp in specs for s in sp.sku_map.values()})
    classify(rows, load_existing(db), load_offers(db))
    eligible = [r for r in rows if r.klass == "NEW" or (r.klass == "NEEDS_REVIEW" and (r.store_key, r.line) in include)]
    before = _fingerprint(db)
    probe_before = dashboard_probe(db) if probe else None
    outer = db.begin_nested()
    results = []
    for r in eligible:
        sp = db.begin_nested()
        res = import_row(db, store, products[r.sku], r, batch)
        sp.commit() if res["outcome"] == "INSERTED" else sp.rollback()
        results.append((r, res))
    probe_after = dashboard_probe(db) if probe else None
    if apply:
        outer.commit()
        db.commit()
    else:
        outer.rollback()
        db.rollback()
    after = _fingerprint(db)
    inserted = [x for x in results if x[1]["outcome"] == "INSERTED"]
    by_file = {}
    for sp in specs:
        fr = [r for r in rows if r.file == sp.file_name]
        by_file[sp.file_name] = {"rows": len(fr), "classes": dict(Counter(r.klass for r in fr)),
                                 "value_mad_by_class": {k: str(sum((r.total or Decimal(0) for r in fr if r.klass == k), Decimal(0))) for k in sorted({r.klass for r in fr})},
                                 "eligible": sum(1 for r in eligible if r.file == sp.file_name)}
    new_customers = sum(1 for _, res in results if res.get("new_customer"))
    return {
        "apply": apply, "batch": batch, "store": {"name": store.name, "code": store.code}, "sku_mapping": {s.file_name: s.sku_map for s in specs},
        "files": by_file, "classes": dict(Counter(r.klass for r in rows)),
        "import": {"eligible": len(eligible), "outcomes": dict(Counter(x[1]["outcome"] for x in results)), "inserted": len(inserted), "new_customers": new_customers,
                   "value_mad": str(sum((x[0].total for x in inserted), Decimal(0)))},
        "orders_before": before["orders"][1], "orders_after": after["orders"][1], "customers_before": before["customers"][1], "customers_after": after["customers"][1],
        "backfilled_orders_in_db": db.query(Order).filter(Order.source == "STORE_CSV_BACKFILL").count(),
        "dashboard_before": probe_before, "dashboard_after_inside_transaction": probe_after,
        "rows": [{"file": r.file[:12], "store": r.store_key, "line": r.line, "shopify_id": r.shopify_id, "phone": mask(r.phone), "qty": r.quantity, "total": str(r.total), "sku": r.sku,
                  "class": r.klass, "reasons": r.reasons, "flags": [f.split(":")[0] for f in r.flags], "evidence": r.evidence,
                  "import": next((res["outcome"] for rr, res in results if rr is r), None)} for r in rows],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-batch", default="")
    ap.add_argument("--include", default="", help="explicitly approved NEEDS_REVIEW rows, e.g. nabil:12,custom-blood:4")
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parent.parent / "private_imports"))
    ap.add_argument("--stdin-json", action="store_true", help='stdin = {"<file name>": "<csv text>", ...}')
    args = ap.parse_args()
    if args.apply and args.confirm_batch != args.batch:
        raise SystemExit("refusing: --apply needs --confirm-batch equal to --batch")
    texts = json.load(sys.stdin) if args.stdin_json else {sp.file_name: (Path(args.dir) / sp.file_name).read_text(encoding="utf-8") for sp in DEFAULT_SPECS}
    include = {(a, int(b)) for a, b in (x.split(":") for x in args.include.split(",") if x.strip())}
    print("CSVBF_JSON:" + json.dumps(run(SessionLocal(), texts, args.batch, args.apply, include), default=str))


if __name__ == "__main__":
    main()
