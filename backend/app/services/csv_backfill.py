"""Idempotent backfill of orders from store order-export CSVs (stores that were never connected to CODOPS).

Source STORE_CSV_BACKFILL is a *historical* source: the orders are real, visible in Orders and agent workload, but are NOT counted as
new acquisition (see app.core.sources). Submission dates are unknown in these exports and are never invented: created_at is the real
import time and the order note / import event say so.

Identity of a CSV order: (originating store key, Shopify order id) -> external_order_id "csv:<store_key>:<shopify_id>". The store key
keeps two stores that reuse the same numeric ids apart. The CODOPS store is the one that OWNS the mapped product.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.sources import BACKFILL_SOURCE
from app.core.time import utcnow
from app.models import Customer, IntegrationEvent, Order, Product, ProductOffer, Store
from app.services.phone import normalize_phone

TEST_NAME = re.compile(r"^\s*test\b", re.IGNORECASE)


@dataclass
class CsvSpec:
    file_name: str
    store_key: str                 # originating store identity, e.g. "nabil"
    sku_map: dict[str, str]        # CSV sku -> CODOPS sku


@dataclass
class Row:
    file: str
    store_key: str
    line: int                      # CSV line number (header = 1)
    source_sku: str
    sku: str
    name: str
    phone_raw: str
    phone: str = ""                # +212... (empty when invalid)
    city: str = ""
    quantity: int = 0
    total: Decimal | None = None
    shopify_id: str = ""
    product_name: str = ""
    klass: str = ""
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def ext_id(self) -> str:
        return f"csv:{self.store_key}:{self.shopify_id}"

    @property
    def key9(self) -> str:
        return re.sub(r"\D", "", self.phone)[-9:]


def parse_csv_text(text_: str, spec: CsvSpec) -> list[Row]:
    rows: list[Row] = []
    for i, r in enumerate(csv.DictReader(io.StringIO(text_)), start=2):
        g = lambda k: (r.get(k) or "").strip()
        try:
            qty = int(g("quantity"))
        except ValueError:
            qty = 0
        try:
            total = Decimal(g("total"))
        except InvalidOperation:
            total = None
        src_sku = g("SKU")
        row = Row(file=spec.file_name, store_key=spec.store_key, line=i, source_sku=src_sku, sku=spec.sku_map.get(src_sku, ""), name=g("FULL NAME"),
                  phone_raw=g("PHONE NUMBER"), city=g("city"), quantity=qty, total=total, shopify_id=g("SHOPIFY ORDER ID"), product_name=g("product name"))
        try:
            row.phone = normalize_phone(row.phone_raw, "MA")
        except Exception:
            row.phone = ""
        rows.append(row)
    return rows


def classify(rows: list[Row], existing: list[dict], offers: dict[str, set[tuple[int, Decimal]]]) -> list[Row]:
    """Row-by-row classification. `existing` = [{order_number, ext, phone, sku, qty, total, source}] for ALL production orders.

    NEW           no evidence of this order in CODOPS (an existing customer with a different product is still NEW)
    EXISTING      same phone + same SKU + same quantity + same total already in CODOPS, or same csv identity already imported
    DUPLICATE     the same submission repeated inside the supplied files
    CONFLICT      same Shopify order id AND same customer already in CODOPS, but a different product/quantity/total
    NEEDS_REVIEW  same phone + SKU in CODOPS with another quantity/total (probably an earlier import with default values), a probable
                  merchant test order, or a total that is not a whole price
    INVALID       missing/invalid essential data (name, phone, quantity, total, unmapped SKU)
    """
    by_phone: dict[str, list[dict]] = {}
    imported_ids = set()
    for o in existing:
        by_phone.setdefault(re.sub(r"\D", "", o["phone"])[-9:], []).append(o)
        if str(o["ext"]).startswith("csv:"):
            imported_ids.add(o["ext"])
    seen: dict[tuple, Row] = {}
    cluster: dict[str, int] = {}
    for r in rows:
        if r.phone:
            cluster[r.key9[:5]] = cluster.get(r.key9[:5], 0) + 1     # a 5-digit block holds only 10,000 possible numbers
    for r in rows:
        # ---- INVALID ---------------------------------------------------------------------------------
        if not r.name:
            r.reasons.append("missing customer name")
        if not r.phone:
            r.reasons.append("invalid phone")
        if r.quantity < 1:
            r.reasons.append("invalid quantity")
        if r.total is None or r.total <= 0:
            r.reasons.append("invalid total")
        if not r.sku:
            r.reasons.append(f"SKU '{r.source_sku}' has no mapping")
        if not r.shopify_id:
            r.reasons.append("missing Shopify order id")
        if r.reasons:
            r.klass = "INVALID"
            continue
        # ---- duplicates inside the supplied files -------------------------------------------------------
        sig = (r.key9, r.sku, r.quantity, r.total)
        ident = (r.store_key, r.shopify_id)
        if ident in seen or sig in seen:
            first = seen.get(ident) or seen.get(sig)
            r.klass = "DUPLICATE"
            r.reasons.append(f"same submission as {first.file} line {first.line}")
            continue
        seen[ident] = r
        seen[sig] = r
        ex = by_phone.get(r.key9, [])
        same_sku = [o for o in ex if o["sku"] == r.sku]
        exact = [o for o in same_sku if str(o["qty"]) == str(r.quantity) and Decimal(str(o["total"])) == r.total]
        id_same_customer = [o for o in ex if o["ext"] == r.shopify_id or str(o["ext"]).startswith(r.shopify_id + "~")]
        if r.ext_id in imported_ids:
            r.klass = "EXISTING"
            r.reasons.append("already imported by a previous CSV backfill")
            continue
        if exact:
            r.klass = "EXISTING"
            r.evidence = [f"{o['order_number']} ({o['source']}, qty {o['qty']}, {o['total']} MAD)" for o in exact]
            r.reasons.append("same phone + SKU + quantity + total already in CODOPS")
            continue
        if id_same_customer and not any(o["sku"] == r.sku and str(o["qty"]) == str(r.quantity) for o in id_same_customer):
            r.klass = "CONFLICT"
            r.evidence = [f"{o['order_number']} ext {o['ext']} {o['sku']} qty {o['qty']} {o['total']} MAD" for o in id_same_customer]
            r.reasons.append("same order id and customer in CODOPS with different product/quantity/total")
            continue
        if same_sku:
            r.klass = "NEEDS_REVIEW"
            r.evidence = [f"{o['order_number']} ({o['source']}, qty {o['qty']}, {o['total']} MAD, {o.get('day', '')})" for o in same_sku]
            r.reasons.append("customer already has this product in CODOPS with a different quantity/total (probably the same order imported earlier with default values)")
            continue
        # ---- NEW, possibly flagged ------------------------------------------------------------------------
        r.klass = "NEW"
        if ex:
            r.flags.append("REPEAT_CUSTOMER: phone already has orders for another product - keep with one agent")
            r.evidence = [f"{o['order_number']} {o['sku']}" for o in ex][:3]
        review = []
        if TEST_NAME.match(r.name):
            review.append("name looks like a test order")
        if r.total != r.total.to_integral_value():
            review.append(f"total {r.total} MAD is not a whole price (not rounded)")
        if cluster.get(r.key9[:5], 0) >= 3:
            review.append("phone is one of 3+ numbers in the same 5-digit block within the supplied files (probable merchant test numbers)")
        if review:
            r.klass = "NEEDS_REVIEW"
            r.reasons += review
            continue
        if (r.quantity, r.total) not in offers.get(r.sku, set()):
            r.flags.append(f"PRICE_NOT_IN_OFFERS: {r.quantity} x {r.sku} for {r.total} MAD is not an active CODOPS offer (price kept as exported)")
    # repeated customer inside the supplied files
    phones: dict[str, list[Row]] = {}
    for r in rows:
        if r.klass == "NEW" and r.phone:
            phones.setdefault(r.key9, []).append(r)
    for rs in phones.values():
        if len(rs) > 1:
            for r in rs:
                r.flags.append("REPEAT_IN_FILES: same customer has several new orders - keep with one agent, confirm each is intended")
    return rows


def load_existing(db: Session) -> list[dict]:
    q = db.execute(text(
        "select o.order_number, coalesce(o.external_order_id,''), cu.phone_e164, p.sku, o.quantity, o.total_price, o.source, o.created_at "
        "from orders o join customers cu on cu.id=o.customer_id join products p on p.id=o.product_id"))
    return [dict(zip(("order_number", "ext", "phone", "sku", "qty", "total", "source", "day"), (*r[:7], str(r[7])[:10]))) for r in q.all()]


def load_offers(db: Session) -> dict[str, set[tuple[int, Decimal]]]:
    out: dict[str, set[tuple[int, Decimal]]] = {}
    for sku, qty, price in db.query(Product.sku, ProductOffer.quantity, ProductOffer.price).join(ProductOffer, ProductOffer.product_id == Product.id).filter(ProductOffer.is_active.is_(True)).all():
        out.setdefault(sku, set()).add((int(qty), Decimal(price)))
    return out


def resolve_store(db: Session, skus: set[str]) -> tuple[Store, dict[str, Product]]:
    """The CODOPS store is the store that owns the mapped products; refuse if they disagree or are missing/inactive."""
    prods = {p.sku: p for p in db.query(Product).filter(Product.sku.in_(skus)).all()}
    missing = [s for s in skus if s not in prods or prods[s].status != "ACTIVE"]
    if missing:
        raise SystemExit(f"refusing: products missing or not ACTIVE in CODOPS: {missing}")
    store_ids = {p.store_id for p in prods.values()}
    if len(store_ids) != 1:
        raise SystemExit("refusing: the mapped products belong to different stores")
    return db.query(Store).filter(Store.id == store_ids.pop()).one(), prods


def _try_lock(db: Session, key: str) -> bool:
    if db.get_bind().dialect.name != "postgresql":
        return True
    return bool(db.execute(text("select pg_try_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key}).scalar())


def import_row(db: Session, store: Store, product: Product, r: Row, batch: str) -> dict:
    """Insert one NEW row. Never touches existing customers/orders; unassigned, NEW, no shipment/payout."""
    if not _try_lock(db, f"csvbf:{store.id}:{r.ext_id}"):
        return {"outcome": "FAILED", "error": "concurrent import of the same order; retry"}
    existing = db.query(Order).filter(Order.store_id == store.id, Order.external_order_id == r.ext_id).first()
    if existing:
        return {"outcome": "DUPLICATE", "order_number": existing.order_number}
    customer = db.query(Customer).filter(Customer.phone_e164 == r.phone).first()
    created_customer = customer is None
    if created_customer:
        customer = Customer(name=r.name[:160], phone_raw=r.phone_raw[:60], phone_e164=r.phone, city=r.city[:120] or None, address=None)
        db.add(customer)
        db.flush()
    note = (f"CSV BACKFILL ({r.store_key}, Shopify order #{r.shopify_id}, {r.file} line {r.line}). Original submission date unknown."
            + ("".join(f"\n[{f.split(':')[0]}] {f.split(':', 1)[1].strip()}" for f in r.flags) if r.flags else ""))
    unit = (r.total / r.quantity) if r.quantity else r.total
    order = Order(order_number=_order_number(), store_id=store.id, product_id=product.id, customer_id=customer.id, assigned_agent_id=None, quantity=r.quantity,
                  unit_price=unit, total_price=r.total, currency=product.currency or store.currency, source=BACKFILL_SOURCE, external_order_id=r.ext_id,
                  call_status="NEW", call_note=note, city=r.city[:120] or None, address=None)
    db.add(order)
    db.flush()
    db.add(IntegrationEvent(integration_id=None, provider=BACKFILL_SOURCE, direction="INBOUND", event_type="ORDER_IMPORT", status="SUCCESS", entity_type="ORDER", entity_id=order.id,
                            payload={"batch": batch, "file": r.file, "csv_line": r.line, "store_key": r.store_key, "shopify_order_id": r.shopify_id, "source_sku": r.source_sku,
                                     "sku": r.sku, "submitted_at": "unknown", "imported_at": utcnow().isoformat(), "flags": r.flags, "new_customer": created_customer}))
    db.flush()      # the session does not autoflush: make the order AND its import event visible to later queries in the same transaction
    return {"outcome": "INSERTED", "order_number": order.order_number, "new_customer": created_customer}


def _order_number() -> str:
    from app.services.google_sheets import new_order_number
    return new_order_number()
