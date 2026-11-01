"""READ-ONLY, production-side verification of sheet rows against CODOPS orders.

Input: the DIGESTS block printed by diagnoseMissingLeads() (rows with a salted phone digest, no phone numbers).
The key (DIAG_KEY) is passed by environment variable so it never appears in arguments or logs.

    DIAG_KEY=... python verify_row_digests.py digests.txt
    (run where DATABASE_URL points at the database; nothing is written - the session is read-only)

Verdicts per row (a phone number alone is never proof; the order number / external id / SKU must also fit):
  CONFIRMED_OWN        order number exists and belongs to this row's full phone (and SKU, when both known)
  OWNER_BY_EXT_ID      sheet mark missing/odd but an order with same external id + same full phone + same SKU exists
  NUMBER_BELONGS_TO_OTHER  the recorded CODOPS order number belongs to a DIFFERENT customer  -> false IMPORTED
  NO_ORDER_FOUND       nothing in CODOPS matches this row                                       -> MISSING
  POSSIBLE_EXISTING    same full phone + same SKU exists under another id (manual review, NOT counted as missing)
  NO_PHONE             row cannot be imported at all
  SKU_NOT_IN_CODOPS    would be rejected until the SKU is mapped (also reported as missing)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from collections import defaultdict


def digest(key: str, phone: str) -> str:
    last9 = "".join(ch for ch in str(phone) if ch.isdigit())[-9:]
    return hmac.new(key.encode(), last9.encode(), hashlib.sha256).hexdigest()[:12]


def parse_rows(text: str) -> list[dict]:
    body = text.split("DIGESTS_BEGIN", 1)[-1].split("DIGESTS_END", 1)[0]
    rows = []
    for line in body.strip().splitlines():
        parts = line.strip().split("|")
        if len(parts) != 8 or parts[0] == "row" or not parts[0].isdigit():
            continue
        rows.append(dict(zip(("row", "ext", "status", "order_no", "sku", "qty", "total", "digest"), parts)) | {"row": int(parts[0])})
    return rows


def classify(rows: list[dict], orders: list[dict], skus: set[str], key: str) -> list[dict]:
    """orders: [{order_number, external_order_id, phone, sku}] for source GOOGLE_SHEETS."""
    by_no = {o["order_number"]: {**o, "digest": digest(key, o["phone"])} for o in orders}
    by_ext = defaultdict(list)
    by_phone_sku = defaultdict(list)
    for o in by_no.values():
        base = (o["external_order_id"] or "").split("~")[0]
        if base and not base.startswith(("sheet:", "fp:")):
            by_ext[base].append(o)
        by_phone_sku[(o["digest"], (o["sku"] or "").upper())].append(o)
    out = []
    for r in rows:
        sku = r["sku"].strip().upper()
        res = dict(r)
        if r["digest"] == "NOPHONE":
            res["verdict"] = "NO_PHONE"
        else:
            o = by_no.get(r["order_no"]) if r["order_no"] else None
            sku_ok = lambda ord_: not sku or not ord_["sku"] or ord_["sku"].upper() == sku
            if o and o["digest"] == r["digest"] and sku_ok(o):
                res["verdict"] = "CONFIRMED_OWN"
            elif o and o["digest"] != r["digest"]:
                res["verdict"] = "NUMBER_BELONGS_TO_OTHER"
            else:
                cand = [x for x in by_ext.get(r["ext"], []) if x["digest"] == r["digest"] and sku_ok(x)] if r["ext"] else []
                if cand:
                    res["verdict"] = "OWNER_BY_EXT_ID"
                    res["found_order"] = cand[0]["order_number"]
                elif by_phone_sku.get((r["digest"], sku)):
                    res["verdict"] = "POSSIBLE_EXISTING"
                    res["found_order"] = by_phone_sku[(r["digest"], sku)][0]["order_number"]
                else:
                    res["verdict"] = "NO_ORDER_FOUND"
        res["sku_known"] = bool(sku) and sku in skus
        out.append(res)
    return out


def summarize(results: list[dict]) -> dict:
    groups: dict[str, list[int]] = defaultdict(list)
    for r in results:
        groups[r["verdict"]].append(r["row"])
    missing = sorted((r for r in results if r["verdict"] in ("NUMBER_BELONGS_TO_OTHER", "NO_ORDER_FOUND")), key=lambda r: r["row"])
    return {
        "rows": len(results),
        "verdict_counts": {k: len(v) for k, v in sorted(groups.items())},
        "rows_by_verdict": {k: sorted(v) for k, v in sorted(groups.items())},
        "confirmed_missing_rows": [r["row"] for r in missing],
        "confirmed_missing_importable_now": [r["row"] for r in missing if r["sku_known"]],
        "confirmed_missing_blocked_by_sku": [r["row"] for r in missing if not r["sku_known"]],
        "blocked_sku_values": sorted({r["sku"] or "(empty)" for r in missing if not r["sku_known"]}),
    }


def main() -> None:
    from sqlalchemy import create_engine, text

    key = os.environ.get("DIAG_KEY") or sys.exit("DIAG_KEY env var required")
    rows = parse_rows(open(sys.argv[1], encoding="utf-8").read())
    url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1).replace("postgres://", "postgresql+psycopg://", 1)
    with create_engine(url).connect() as c:
        c.execute(text("set transaction read only"))
        orders = [dict(zip(("order_number", "external_order_id", "phone", "sku"), r)) for r in c.execute(text(
            "select o.order_number, coalesce(o.external_order_id,''), cu.phone_e164, p.sku from orders o "
            "join customers cu on cu.id=o.customer_id join products p on p.id=o.product_id where o.source='GOOGLE_SHEETS'"))]
        skus = {r[0].upper() for r in c.execute(text("select sku from products where status='ACTIVE'"))}
    print(json.dumps(summarize(classify(rows, orders, skus, key)), indent=1))


if __name__ == "__main__":
    main()
