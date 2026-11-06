from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime
from pathlib import Path
from decimal import Decimal
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.sources import RECOVERY_SOURCE
from app.core.time import utcnow
from app.models import AgentProduct, Customer, IntegrationConfig, IntegrationEvent, Order, OrderAssignment, Product, Store
from app.services.assignment import choose_agent
from app.services.phone import normalize_phone


def new_order_number() -> str:
    return f"CC-{datetime.now().strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"


def _fit(value, limit: int) -> str:
    """Trim to the DB column width so one long cell cannot make the whole row fail."""
    return str(value or "").strip()[:limit]


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def lead_fingerprint(store_id: str, phone_e164: str, sku: str, qty: int, total, name: str, lead_date) -> str:
    """Stable identity for a lead that does not depend on its sheet row position."""
    raw = "|".join([store_id, phone_e164, sku.upper(), str(qty), "" if total is None else str(Decimal(str(total)).normalize()), _norm(name), _norm(lead_date)])
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def _try_lock(db: Session, key: str) -> bool:
    """Transaction-scoped advisory lock on one lead identity (PostgreSQL), held until commit/rollback.

    It serialises normal imports and recovery for the SAME lead, so a concurrent request can never miss an uncommitted insert
    (the partial unique index only covers GOOGLE_SHEETS, not GOOGLE_SHEETS_RECOVERY). Non-blocking on purpose: a contended
    lead is reported as a transient failure and retried, which rules out deadlocks between large batches. Re-entrant for the
    same transaction. No-op on other databases (tests)."""
    if db.get_bind().dialect.name != "postgresql":
        return True
    return bool(db.execute(text("select pg_try_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": key}).scalar())


def _result(item: dict, status: str, outcome: str, **extra) -> dict:
    return {"status": status, "outcome": outcome, "row_number": item.get("row_number"), **extra}


def _same_lead(db: Session, existing: Order, phone: str, sku: str) -> bool:
    """A stored order is the SAME lead only when phone (and SKU, if both known) match.

    Matching on external id alone silently dropped different leads that share an id
    (re-used ids, several feeds, Shopify multi-line orders)."""
    customer = db.query(Customer).filter(Customer.id == existing.customer_id).first()
    if not customer or customer.phone_e164 != phone:
        return False
    if sku:
        product = db.query(Product).filter(Product.id == existing.product_id).first()
        if product and (product.sku or "").upper() != sku:
            return False
    return True


def _duplicate(item: dict, existing: Order) -> dict:
    return _result(item, "IMPORTED", "DUPLICATE", order_id=existing.id, order_number=existing.order_number, duplicate=True)


def import_sheet_order(db: Session, integration: IntegrationConfig, item: dict) -> dict:
    """Import one lead idempotently. outcome is one of INSERTED, DUPLICATE, REJECTED (permanent) or FAILED (transient)."""
    config = dict(integration.config or {})
    store = db.query(Store).filter(Store.id == integration.store_id).first() if integration.store_id else None
    if not store:
        return _result(item, "ERROR", "FAILED", error="Integration store not found")

    sku = str(item.get("sku") or "").strip().upper()
    try:
        phone = normalize_phone(str(item.get("phone") or ""), store.country)
    except Exception as exc:
        return _result(item, "ERROR", "REJECTED", error=f"Invalid phone: {exc}")
    qty = max(int(item.get("quantity") or 1), 1)
    total = Decimal(str(item.get("total_price"))) if item.get("total_price") not in (None, "") else None
    name = _fit(item.get("customer_name") or "Customer", 160)
    fp = lead_fingerprint(store.id, phone, sku, qty, total, name, item.get("lead_date"))

    # ---- identity / idempotency -------------------------------------------------
    supplied = str(item.get("external_order_id") or "").strip()[:140]
    legacy_row_id = supplied.startswith("sheet:")          # old scripts used row position as identity
    if not _try_lock(db, f"gsheets:{store.id}:{supplied if supplied and not legacy_row_id else fp}"):
        return _result(item, "ERROR", "FAILED", error="Same lead is being imported by a concurrent request; will be retried")
    collision = False
    if supplied and not legacy_row_id:
        external = supplied
        existing = db.query(Order).filter(Order.store_id == store.id, Order.external_order_id == external).first()
        if existing:
            if _same_lead(db, existing, phone, sku):
                return _duplicate(item, existing)
            # Same id, different lead: do NOT drop it. Give it a derived, still-deterministic id.
            collision = True
            external = f"{external[:125]}~{fp[:10]}"
            again = db.query(Order).filter(Order.store_id == store.id, Order.external_order_id == external).first()
            if again:
                return _duplicate(item, again)
    else:
        external = f"fp:{fp}"
        existing = db.query(Order).filter(Order.store_id == store.id, Order.external_order_id == external).first()
        if existing:
            return _duplicate(item, existing)
        # Orders imported earlier under a row-position id: same lead only if phone matches.
        legacy_candidates = []
        if supplied:
            legacy_candidates = db.query(Order).filter(Order.store_id == store.id, Order.external_order_id == supplied).all()
        elif item.get("row_number"):
            legacy_candidates = db.query(Order).filter(Order.store_id == store.id, Order.source == "GOOGLE_SHEETS", Order.external_order_id.like(f"sheet:%:{int(item['row_number'])}")).all()
        for cand in legacy_candidates:
            if _same_lead(db, cand, phone, sku):
                return _duplicate(item, cand)

    product = db.query(Product).filter(Product.store_id == store.id, Product.sku == sku, Product.status == "ACTIVE").first() if sku else None
    if not product and not sku and config.get("default_product_id"):
        # default product is only used when the integration owner configured it AND the row has no SKU at all.
        product = db.query(Product).filter(Product.id == config["default_product_id"], Product.store_id == store.id, Product.status == "ACTIVE").first()
    if not product:
        return _result(item, "ERROR", "REJECTED", error=f"Product SKU not found: {sku or '(empty)'}")

    customer = db.query(Customer).filter(Customer.phone_e164 == phone).first()
    if not customer:
        customer = Customer(name=name, phone_raw=_fit(item.get("phone"), 60), phone_e164=phone, city=_fit(item.get("city"), 120) or None, address=item.get("address"))
        db.add(customer)
        db.flush()
    elif not item.get("recovery"):          # recovery mode never modifies an existing customer record
        customer.name = name or customer.name
        customer.city = _fit(item.get("city"), 120) or customer.city
        customer.address = item.get("address") or customer.address

    total_v = total if total is not None else Decimal(product.selling_price) * qty
    unit = total_v / qty if qty else Decimal(product.selling_price)
    # recovery mode (set only by the operator-run recovery tool, never by the webhook): leads stay NEW and UNASSIGNED
    recovery = bool(item.get("recovery"))
    agent = None if recovery else (choose_agent(db, product.id, customer.id) if config.get("auto_assign", True) else None)
    row = Order(
        order_number=new_order_number(), store_id=store.id, product_id=product.id, customer_id=customer.id,
        assigned_agent_id=agent.id if agent else None, quantity=qty, unit_price=unit, total_price=total_v,
        currency=product.currency or store.currency, source=RECOVERY_SOURCE if recovery else "GOOGLE_SHEETS", external_order_id=external,
        call_status="NEW", call_note=item.get("note"), city=_fit(item.get("city"), 120) or None, address=item.get("address"),
        assigned_at=utcnow() if agent else None,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
            if agent:
                db.add(OrderAssignment(order_id=row.id, agent_id=agent.id, assignment_type="SMART_SCORE"))
            db.add(IntegrationEvent(integration_id=integration.id, provider="GOOGLE_SHEETS", direction="INBOUND", event_type="ORDER_IMPORT", status="SUCCESS", entity_type="ORDER", entity_id=row.id, payload={"row_number": item.get("row_number"), "sku": sku, "external_order_id": external, "collision": collision, "source": item.get("source"), "recovery": recovery, "recovered_at": utcnow().isoformat() if recovery else None}))
            db.flush()
    except IntegrityError:
        # A concurrent request inserted the same lead first (unique index uq_orders_gsheets_ext). Never double-insert:
        winner = db.query(Order).filter(Order.store_id == store.id, Order.external_order_id == external).first()
        if winner is not None and _same_lead(db, winner, phone, sku):
            return _duplicate(item, winner)
        return _result(item, "ERROR", "FAILED", error="Concurrent import conflict; will be retried")
    return _result(item, "IMPORTED", "INSERTED", order_id=row.id, order_number=row.order_number, duplicate=False, collision=collision)


_SCRIPT_DIR = Path(__file__).parent / "apps_script"


def apps_script(integration: IntegrationConfig, webhook_token: str) -> str:
    config = dict(integration.config or {})
    public_api = settings.public_api_base_url.rstrip("/")
    webhook = f"{public_api}/api/v1/integrations/google-sheets/{integration.id}/webhook"
    sheet_name = str(config.get("sheet_name") or "Sheet1")
    template = (_SCRIPT_DIR / "sync.gs.tmpl").read_text(encoding="utf-8")
    script = template.replace("__WEBHOOK__", json.dumps(webhook)).replace("__TOKEN__", json.dumps(webhook_token)).replace("__SHEET__", json.dumps(sheet_name))
    return script + "\n" + (_SCRIPT_DIR / "diagnose_missing_leads.gs").read_text(encoding="utf-8")
