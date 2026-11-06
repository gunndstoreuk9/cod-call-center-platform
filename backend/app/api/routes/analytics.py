from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.sources import BACKFILL_SOURCE, HISTORICAL_SOURCES, RECOVERY_SOURCE
from app.core.deps import require_roles
from app.core.time import date_bounds
from app.models import Order, PayoutEntry, Product, User

router = APIRouter(prefix="/analytics", tags=["analytics"])


def acquisition(query):
    """Acquisition view: historical recovered leads are not new customers acquired in this period."""
    return query.filter(Order.source.notin_(HISTORICAL_SOURCES))


def pct(num: int | Decimal, den: int | Decimal) -> float:
    return round(float(num) / float(den) * 100, 2) if den else 0.0


@router.get("/overview")
def overview(
    range: str = "today",
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    start, end = date_bounds(range, from_date, to_date)
    q_all = db.query(Order).filter(Order.created_at >= start, Order.created_at < end)   # operational + financial view
    q = acquisition(q_all)                                                              # acquisition KPIs (no recovered leads)
    recovered = q_all.filter(Order.source == RECOVERY_SOURCE)
    backfilled = q_all.filter(Order.source == BACKFILL_SOURCE)
    total = q.count()
    confirmed = q.filter(Order.call_status == "CONFIRMED").count()
    delivered = q.filter(Order.delivery_status == "DELIVERED").count()
    called = q.filter(Order.first_call_at.is_not(None)).count()
    confirmed_revenue = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.created_at >= start, Order.created_at < end, Order.call_status == "CONFIRMED").scalar() or 0
    delivered_revenue = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.created_at >= start, Order.created_at < end, Order.delivery_status == "DELIVERED").scalar() or 0
    payout_due = db.query(func.coalesce(func.sum(PayoutEntry.amount), 0)).filter(PayoutEntry.status == "UNPAID").scalar() or 0
    confirmed_revenue_recovered = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.created_at >= start, Order.created_at < end, Order.call_status == "CONFIRMED", Order.source.in_(HISTORICAL_SOURCES)).scalar() or 0
    delivered_revenue_recovered = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.created_at >= start, Order.created_at < end, Order.delivery_status == "DELIVERED", Order.source.in_(HISTORICAL_SOURCES)).scalar() or 0
    return {
        # Populations are NOT the same: counts/rates (leads, called, confirmed, delivered, status counts) cover ACQUIRED leads only;
        # revenue fields cover ALL orders including recovered ones. The *_recovered fields below give the difference explicitly.
        "kpi_population": {"counts_and_rates": "acquisition_only", "revenue": "all_orders_incl_recovered", "workload_assigned_unassigned": "all_orders_incl_recovered"},
        "range": range,
        "start": start,
        "end": end,
        "leads": total,
        # workload counters are operational: they include recovered leads that still need an agent
        "assigned": q_all.filter(Order.assigned_agent_id.is_not(None)).count(),
        "unassigned": q_all.filter(Order.assigned_agent_id.is_(None)).count(),
        "recovered_leads": recovered.count(),
        "recovered_unassigned": recovered.filter(Order.assigned_agent_id.is_(None)).count(),
        "recovered_confirmed": recovered.filter(Order.call_status == "CONFIRMED").count(),
        "backfilled_leads": backfilled.count(),
        "backfilled_unassigned": backfilled.filter(Order.assigned_agent_id.is_(None)).count(),
        "backfilled_confirmed": backfilled.filter(Order.call_status == "CONFIRMED").count(),
        "called": called,
        "confirmed": confirmed,
        "confirmation_rate": pct(confirmed, total),
        "no_answer": q.filter(Order.call_status == "NO_ANSWER").count(),
        "busy": q.filter(Order.call_status == "BUSY").count(),
        "callbacks": q.filter(Order.call_status == "CALLBACK").count(),
        "cancelled": q.filter(Order.call_status == "CANCELLED").count(),
        "wrong_number": q.filter(Order.call_status == "WRONG_NUMBER").count(),
        "duplicate": q.filter(Order.call_status == "DUPLICATE").count(),
        "dispatched": q.filter(Order.delivery_status.in_(["DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "REFUSED", "RETURNED"])).count(),
        "delivered": delivered,
        "refused": q.filter(Order.delivery_status == "REFUSED").count(),
        "returned": q.filter(Order.delivery_status == "RETURNED").count(),
        "confirmed_to_delivered_rate": pct(delivered, confirmed),
        "confirmed_revenue": str(confirmed_revenue),
        "delivered_revenue": str(delivered_revenue),
        "confirmed_revenue_recovered": str(confirmed_revenue_recovered),
        "delivered_revenue_recovered": str(delivered_revenue_recovered),
        "confirmed_revenue_acquisition": str(Decimal(str(confirmed_revenue)) - Decimal(str(confirmed_revenue_recovered))),
        "agent_payout_due": str(payout_due),
    }


@router.get("/products")
def product_breakdown(
    range: str = "today",
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    start, end = date_bounds(range, from_date, to_date)
    rows = db.query(Product).order_by(Product.name.asc()).all()
    result = []
    for product in rows:
        q_all = db.query(Order).filter(Order.product_id == product.id, Order.created_at >= start, Order.created_at < end)
        q = acquisition(q_all)
        leads = q.count()
        confirmed = q.filter(Order.call_status == "CONFIRMED").count()
        delivered = q.filter(Order.delivery_status == "DELIVERED").count()
        revenue = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.product_id == product.id, Order.created_at >= start, Order.created_at < end, Order.delivery_status == "DELIVERED").scalar() or 0
        result.append({
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "status": product.status,
            "leads": leads,
            "called": q.filter(Order.first_call_at.is_not(None)).count(),
            "confirmed": confirmed,
            "confirmation_rate": pct(confirmed, leads),
            "cancelled": q.filter(Order.call_status == "CANCELLED").count(),
            "delivered": delivered,
            "delivery_rate": pct(delivered, confirmed),
            "refused": q.filter(Order.delivery_status == "REFUSED").count(),
            "delivered_revenue": str(revenue),    # financial: includes recovered orders once delivered
            "delivered_revenue_recovered": str(db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.product_id == product.id, Order.created_at >= start, Order.created_at < end, Order.delivery_status == "DELIVERED", Order.source.in_(HISTORICAL_SOURCES)).scalar() or 0),
            "recovered_leads": q_all.filter(Order.source == RECOVERY_SOURCE).count(),
            "backfilled_leads": q_all.filter(Order.source == BACKFILL_SOURCE).count(),
        })
    return result


@router.get("/agents")
def agent_breakdown(
    range: str = "today",
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    start, end = date_bounds(range, from_date, to_date)
    agents = db.query(User).filter(User.role == "AGENT").order_by(User.display_name.asc()).all()
    result = []
    for agent in agents:
        q = db.query(Order).filter(Order.assigned_agent_id == agent.id, Order.created_at >= start, Order.created_at < end)
        leads = q.count()
        confirmed = q.filter(Order.call_status == "CONFIRMED").count()
        delivered = q.filter(Order.delivery_status == "DELIVERED").count()
        balance = db.query(func.coalesce(func.sum(PayoutEntry.amount), 0)).filter(PayoutEntry.agent_id == agent.id, PayoutEntry.status == "UNPAID").scalar() or 0
        result.append({
            "agent_id": agent.id,
            "display_name": agent.display_name,
            "is_active": agent.is_active,
            "assigned": leads,
            "called": q.filter(Order.first_call_at.is_not(None)).count(),
            "confirmed": confirmed,
            "confirmation_rate": pct(confirmed, leads),
            "delivered": delivered,
            "delivery_rate": pct(delivered, confirmed),
            "no_answer": q.filter(Order.call_status == "NO_ANSWER").count(),
            "callbacks": q.filter(Order.call_status == "CALLBACK").count(),
            "cancelled": q.filter(Order.call_status == "CANCELLED").count(),
            "unpaid_balance": str(balance),
        })
    return result
