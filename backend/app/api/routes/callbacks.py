from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user
from app.core.time import utcnow
from app.models import Callback, Customer, Order, Product, User
from app.schemas import CallbackUpdate

router = APIRouter(prefix="/callbacks", tags=["callbacks"])


@router.get("")
def list_callbacks(
    bucket: str = "due",
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    now = utcnow()
    q = db.query(Callback).filter(Callback.status == "PENDING")
    if user.role == "AGENT":
        q = q.filter(Callback.agent_id == user.id)
    if bucket == "overdue":
        q = q.filter(Callback.scheduled_at < now)
    elif bucket == "today":
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        q = q.filter(Callback.scheduled_at >= day_start, Callback.scheduled_at < day_start + timedelta(days=1))
    elif bucket == "tomorrow":
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
        q = q.filter(Callback.scheduled_at >= day_start, Callback.scheduled_at < day_start + timedelta(days=1))
    else:
        q = q.filter(Callback.scheduled_at <= now + timedelta(hours=1))
    rows = q.order_by(Callback.scheduled_at.asc()).limit(min(max(limit, 1), 300)).all()
    result = []
    for cb in rows:
        order = db.query(Order).filter(Order.id == cb.order_id).first()
        customer = db.query(Customer).filter(Customer.id == order.customer_id).first() if order else None
        product = db.query(Product).filter(Product.id == order.product_id).first() if order else None
        agent = db.query(User).filter(User.id == cb.agent_id).first()
        result.append({
            "id": cb.id,
            "order_id": cb.order_id,
            "order_number": order.order_number if order else None,
            "customer_name": customer.name if customer else None,
            "phone": customer.phone_e164 if customer else None,
            "product_name": product.name if product else None,
            "agent_name": agent.display_name if agent else None,
            "scheduled_at": cb.scheduled_at,
            "reason": cb.reason,
            "note": cb.note,
            "status": cb.status,
        })
    return result


@router.patch("/{callback_id}")
def update_callback(
    callback_id: str,
    payload: CallbackUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    row = db.query(Callback).filter(Callback.id == callback_id).first()
    if not row:
        raise HTTPException(404, "Callback not found")
    if user.role == "AGENT" and row.agent_id != user.id:
        raise HTTPException(403, "This callback is not assigned to you")
    status = payload.status.upper()
    if status not in {"PENDING", "COMPLETED", "CANCELLED"}:
        raise HTTPException(400, "Invalid callback status")
    row.status = status
    row.completed_at = utcnow() if status == "COMPLETED" else None
    db.commit()
    return {"id": row.id, "status": row.status, "completed_at": row.completed_at}
