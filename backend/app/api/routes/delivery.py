from __future__ import annotations

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.core.time import date_bounds
from app.models import (
    DeliveryDestination, DeliveryEvent, DeliveryShipment, DeliveryStatusMapping,
    DeliverySyncRun, IntegrationConfig, Order, Product, User,
)
from app.services.digylog import seed_status_mappings

router = APIRouter(prefix="/delivery", tags=["delivery"])


def pct(num, den) -> float:
    return round(float(num) / float(den) * 100, 2) if den else 0.0


def _daterange(range_name: str, from_date: str | None, to_date: str | None):
    return date_bounds(range_name, from_date, to_date)


@router.get("/dashboard")
def dashboard(
    range: str = "today", from_date: str | None = None, to_date: str | None = None,
    store_id: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    start, end = _daterange(range, from_date, to_date)
    q = db.query(Order).filter(Order.created_at >= start, Order.created_at < end)
    if store_id:
        q = q.filter(Order.store_id == store_id)
    total = q.count()
    confirmed = q.filter(Order.call_status == "CONFIRMED").count()
    sent = q.filter(Order.delivery_status.in_(["DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "ISSUE", "DELIVERED", "REFUSED", "RETURNED", "CANCELLED"])).count()
    delivered = q.filter(Order.delivery_status == "DELIVERED").count()
    refused = q.filter(Order.delivery_status == "REFUSED").count()
    returned = q.filter(Order.delivery_status == "RETURNED").count()
    cancelled = q.filter(Order.delivery_status == "CANCELLED").count()
    issue = q.filter(Order.delivery_status == "ISSUE").count()
    in_delivery = q.filter(Order.delivery_status.in_(["DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY"])).count()
    pending = q.filter(Order.delivery_status.in_(["NOT_READY", "READY"])).count()
    delivered_revenue = (db.query(func.coalesce(func.sum(Order.total_price), 0))
                         .filter(Order.created_at >= start, Order.created_at < end, Order.delivery_status == "DELIVERED"))
    confirmed_revenue = (db.query(func.coalesce(func.sum(Order.total_price), 0))
                         .filter(Order.created_at >= start, Order.created_at < end, Order.call_status == "CONFIRMED"))
    if store_id:
        delivered_revenue = delivered_revenue.filter(Order.store_id == store_id)
        confirmed_revenue = confirmed_revenue.filter(Order.store_id == store_id)

    product_rows = []
    products = db.query(Product).order_by(Product.name.asc()).all()
    for product in products:
        pq = q.filter(Order.product_id == product.id)
        pconfirmed = pq.filter(Order.call_status == "CONFIRMED").count()
        psent = pq.filter(Order.delivery_status.in_(["DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "ISSUE", "DELIVERED", "REFUSED", "RETURNED", "CANCELLED"])).count()
        pdelivered = pq.filter(Order.delivery_status == "DELIVERED").count()
        prefused = pq.filter(Order.delivery_status == "REFUSED").count()
        preturned = pq.filter(Order.delivery_status == "RETURNED").count()
        if pconfirmed or psent:
            product_rows.append({
                "product_id": product.id, "product": product.name, "sku": product.sku,
                "confirmed": pconfirmed, "sent": psent, "delivered": pdelivered,
                "refused": prefused, "returned": preturned,
                "dispatch_rate": pct(psent, pconfirmed), "delivery_rate": pct(pdelivered, psent),
                "confirmed_to_delivered_rate": pct(pdelivered, pconfirmed),
            })

    agent_rows = []
    agents = db.query(User).filter(User.role == "AGENT").order_by(User.display_name.asc()).all()
    for agent in agents:
        aq = q.filter(Order.assigned_agent_id == agent.id)
        aconfirmed = aq.filter(Order.call_status == "CONFIRMED").count()
        asent = aq.filter(Order.delivery_status.in_(["DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "ISSUE", "DELIVERED", "REFUSED", "RETURNED", "CANCELLED"])).count()
        adelivered = aq.filter(Order.delivery_status == "DELIVERED").count()
        arefused = aq.filter(Order.delivery_status == "REFUSED").count()
        if aconfirmed or asent:
            agent_rows.append({
                "agent_id": agent.id, "agent": agent.display_name, "confirmed": aconfirmed,
                "sent": asent, "delivered": adelivered, "refused": arefused,
                "dispatch_rate": pct(asent, aconfirmed),
                "confirmed_to_delivered_rate": pct(adelivered, aconfirmed),
                "refusal_rate": pct(arefused, asent),
            })

    return {
        "range": range, "start": start, "end": end,
        "orders": total, "confirmed": confirmed, "sent": sent, "in_delivery": in_delivery,
        "delivered": delivered, "refused": refused, "returned": returned,
        "cancelled": cancelled, "issues": issue, "pending": pending,
        "dispatch_rate": pct(sent, confirmed), "delivery_rate": pct(delivered, sent),
        "confirmed_to_delivered_rate": pct(delivered, confirmed),
        "refusal_rate": pct(refused, sent), "return_rate": pct(returned, sent),
        "cancellation_rate": pct(cancelled, sent), "issue_rate": pct(issue, sent),
        "confirmed_revenue": str(confirmed_revenue.scalar() or Decimal("0")),
        "delivered_revenue": str(delivered_revenue.scalar() or Decimal("0")),
        "products": product_rows, "agents": agent_rows,
    }


@router.get("/shipments")
def shipments(
    provider: str | None = None, status: str | None = None, integration_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    q = db.query(DeliveryShipment)
    if provider: q = q.filter(DeliveryShipment.provider == provider.upper())
    if status: q = q.filter(DeliveryShipment.status == status.upper())
    if integration_id: q = q.filter(DeliveryShipment.integration_id == integration_id)
    rows = q.order_by(DeliveryShipment.created_at.desc()).limit(limit).all()
    return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


@router.get("/events")
def events(
    matched: bool | None = None, tracking: str | None = None, integration_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    q = db.query(DeliveryEvent)
    if matched is not None: q = q.filter(DeliveryEvent.matched.is_(matched))
    if tracking: q = q.filter(DeliveryEvent.tracking_number == tracking)
    if integration_id: q = q.filter(DeliveryEvent.integration_id == integration_id)
    rows = q.order_by(DeliveryEvent.received_at.desc()).limit(limit).all()
    return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


@router.get("/unmatched")
def unmatched(
    limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    rows = (db.query(DeliveryEvent).filter(DeliveryEvent.matched.is_(False))
            .order_by(DeliveryEvent.received_at.desc()).limit(limit).all())
    return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


@router.post("/status-mappings/seed-digylog")
def seed_digylog_mappings(
    db: Session = Depends(get_db), _=Depends(require_roles("OWNER", "ADMIN")),
):
    count = seed_status_mappings(db)
    db.commit()
    return {"ok": True, "created": count}


@router.get("/status-mappings")
def status_mappings(
    provider: str = "DIGYLOG", db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    rows = (db.query(DeliveryStatusMapping).filter(DeliveryStatusMapping.provider == provider.upper())
            .order_by(DeliveryStatusMapping.external_status_id.asc()).all())
    return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


@router.patch("/status-mappings/{mapping_id}")
def update_mapping(
    mapping_id: str, payload: dict, db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN")),
):
    row = db.query(DeliveryStatusMapping).filter(DeliveryStatusMapping.id == mapping_id).first()
    if not row: raise HTTPException(404, "Mapping not found")
    for key in ["external_status_name", "internal_status", "is_final", "is_success", "is_active"]:
        if key in payload: setattr(row, key, payload[key])
    db.commit(); db.refresh(row)
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@router.get("/destinations")
def destinations(
    integration_id: str | None = None, active: bool | None = None,
    limit: int = Query(500, ge=1, le=2000), db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    q = db.query(DeliveryDestination)
    if integration_id: q = q.filter(DeliveryDestination.integration_id == integration_id)
    if active is not None: q = q.filter(DeliveryDestination.is_active.is_(active))
    rows = q.order_by(DeliveryDestination.city_name.asc()).limit(limit).all()
    return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


@router.post("/destinations/upsert")
def upsert_destination(
    payload: dict, db: Session = Depends(get_db), _=Depends(require_roles("OWNER", "ADMIN")),
):
    integration_id = str(payload.get("integration_id") or "")
    city_id = str(payload.get("external_city_id") or payload.get("city_name") or "")
    if not integration_id or not city_id or not payload.get("city_name"):
        raise HTTPException(400, "integration_id, external_city_id and city_name are required")
    if not db.query(IntegrationConfig).filter(IntegrationConfig.id == integration_id).first():
        raise HTTPException(404, "Integration not found")
    row = (db.query(DeliveryDestination)
           .filter(DeliveryDestination.integration_id == integration_id, DeliveryDestination.external_city_id == city_id).first())
    if not row:
        row = DeliveryDestination(integration_id=integration_id, external_city_id=city_id, city_name=str(payload["city_name"]))
        db.add(row)
    for key in ["city_name", "hub", "fee", "min_days", "max_days", "is_active", "raw_payload"]:
        if key in payload: setattr(row, key, payload[key])
    db.commit(); db.refresh(row)
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@router.get("/sync-runs")
def sync_runs(
    integration_id: str | None = None, limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db), _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    q = db.query(DeliverySyncRun)
    if integration_id: q = q.filter(DeliverySyncRun.integration_id == integration_id)
    rows = q.order_by(DeliverySyncRun.started_at.desc()).limit(limit).all()
    return [{c.name: getattr(row, c.name) for c in row.__table__.columns} for row in rows]


@router.get("/health")
def health(
    integration_id: str | None = None, db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    iq = db.query(IntegrationConfig).filter(
        IntegrationConfig.provider == "DIGYLOG"
    )

    if integration_id:
        integration = iq.filter(
            IntegrationConfig.id == integration_id
        ).first()
    else:
        # Health dashboard must use the CURRENT active Digylog connection,
        # not the oldest historical integration.
        integration = (
            iq.filter(IntegrationConfig.is_active.is_(True))
              .order_by(IntegrationConfig.created_at.desc())
              .first()
            or iq.order_by(IntegrationConfig.created_at.desc()).first()
        )

    if not integration:
        return {"connected": False, "message": "No Digylog integration configured"}

    # "Last webhook" must represent an actual Digylog status webhook,
    # not an outbound CREATE_ORDER event.
    # Last webhook = most recent inbound Digylog webhook event.
    last_event = (
        db.query(DeliveryEvent)
        .filter(DeliveryEvent.integration_id == integration.id)
        .order_by(DeliveryEvent.received_at.desc())
        .first()
    )
    last_sync = (db.query(DeliverySyncRun).filter(DeliverySyncRun.integration_id == integration.id)
                 .order_by(DeliverySyncRun.started_at.desc()).first())
    failed = db.query(DeliveryShipment).filter(DeliveryShipment.integration_id == integration.id, DeliveryShipment.status == "FAILED").count()
    unmatched_count = db.query(DeliveryEvent).filter(DeliveryEvent.integration_id == integration.id, DeliveryEvent.matched.is_(False)).count()
    return {
        "connected": bool(integration.is_active), "integration_id": integration.id,
        "last_test_status": integration.last_test_status, "last_test_at": integration.last_test_at,
        "last_webhook_at": last_event.received_at if last_event else None,
        "last_sync_at": last_sync.finished_at if last_sync else None,
        "last_sync_status": last_sync.status if last_sync else None,
        "failed_shipments": failed, "unmatched_events": unmatched_count,
    }
