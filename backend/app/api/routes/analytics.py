from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.core.time import date_bounds
from app.models import Order, PayoutEntry, Product, User

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
    q = db.query(Order).filter(Order.created_at >= start, Order.created_at < end)
    total = q.count()
    confirmed = q.filter(Order.call_status == "CONFIRMED").count()
    delivered = q.filter(Order.delivery_status == "DELIVERED").count()
    called = q.filter(Order.first_call_at.is_not(None)).count()
    confirmed_revenue = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.created_at >= start, Order.created_at < end, Order.call_status == "CONFIRMED").scalar() or 0
    delivered_revenue = db.query(func.coalesce(func.sum(Order.total_price), 0)).filter(Order.created_at >= start, Order.created_at < end, Order.delivery_status == "DELIVERED").scalar() or 0
    payout_due = db.query(func.coalesce(func.sum(PayoutEntry.amount), 0)).filter(PayoutEntry.status == "UNPAID").scalar() or 0
    return {
        "range": range,
        "start": start,
        "end": end,
        "leads": total,
        "assigned": q.filter(Order.assigned_agent_id.is_not(None)).count(),
        "unassigned": q.filter(Order.assigned_agent_id.is_(None)).count(),
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
        q = db.query(Order).filter(Order.product_id == product.id, Order.created_at >= start, Order.created_at < end)
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
            "delivered_revenue": str(revenue),
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
