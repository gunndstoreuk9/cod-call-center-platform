from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.core.time import utcnow
from app.models import PayoutBatch, PayoutEntry, User
from app.schemas import AdjustmentCreate, PayoutPayRequest
from app.services.audit import log_action
from app.services.payouts import unpaid_balance

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/agents")
def agent_balances(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    agents = db.query(User).filter(User.role == "AGENT").order_by(User.display_name.asc()).all()
    result = []
    for agent in agents:
        entries = db.query(PayoutEntry).filter(PayoutEntry.agent_id == agent.id, PayoutEntry.status == "UNPAID").all()
        positive = sum((Decimal(x.amount) for x in entries if Decimal(x.amount) > 0), Decimal("0"))
        negative = sum((Decimal(x.amount) for x in entries if Decimal(x.amount) < 0), Decimal("0"))
        result.append({
            "agent_id": agent.id,
            "display_name": agent.display_name,
            "username": agent.username,
            "entries_count": len(entries),
            "gross_positive": str(positive),
            "adjustments": str(negative),
            "unpaid_balance": str(positive + negative),
        })
    return result


@router.get("/history")
def payment_history(
    agent_id: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    q = db.query(PayoutBatch)
    if agent_id:
        q = q.filter(PayoutBatch.agent_id == agent_id)
    rows = q.order_by(PayoutBatch.paid_at.desc()).limit(min(max(limit, 1), 500)).all()
    agents = {u.id: u.display_name for u in db.query(User).filter(User.id.in_([x.agent_id for x in rows])).all()} if rows else {}
    return [{
        "id": x.id,
        "agent_id": x.agent_id,
        "agent_name": agents.get(x.agent_id),
        "entries_count": x.entries_count,
        "base_amount": str(x.base_amount),
        "adjustment_amount": str(x.adjustment_amount),
        "total_amount": str(x.total_amount),
        "payment_method": x.payment_method,
        "payment_reference": x.payment_reference,
        "note": x.note,
        "paid_at": x.paid_at,
    } for x in rows]


@router.post("/agents/{agent_id}/adjustments")
def create_adjustment(
    agent_id: str,
    payload: AdjustmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    agent = db.query(User).filter(User.id == agent_id, User.role == "AGENT").first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    row = PayoutEntry(
        agent_id=agent_id,
        entry_type="ADJUSTMENT",
        amount=payload.amount,
        status="UNPAID",
        description=payload.description,
    )
    db.add(row)
    db.flush()
    log_action(db, user_id=user.id, action="PAYOUT_ADJUSTMENT_CREATED", entity_type="AGENT", entity_id=agent_id, after={"amount": str(payload.amount), "description": payload.description})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "agent_id": agent_id, "amount": str(row.amount), "status": row.status, "balance": str(unpaid_balance(db, agent_id))}


@router.post("/agents/{agent_id}/pay")
def pay_agent(
    agent_id: str,
    payload: PayoutPayRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    agent = db.query(User).filter(User.id == agent_id, User.role == "AGENT").first()
    if not agent:
        raise HTTPException(404, "Agent not found")

    # PostgreSQL will lock these rows; SQLite simply ignores FOR UPDATE in tests/dev.
    entries = (
        db.query(PayoutEntry)
        .filter(PayoutEntry.agent_id == agent_id, PayoutEntry.status == "UNPAID")
        .with_for_update()
        .order_by(PayoutEntry.created_at.asc())
        .all()
    )
    if not entries:
        raise HTTPException(409, "This agent has no unpaid entries")

    positives = [x for x in entries if Decimal(x.amount) >= 0]
    negatives = [x for x in entries if Decimal(x.amount) < 0]
    base_amount = sum((Decimal(x.amount) for x in positives if x.entry_type == "CONFIRMATION"), Decimal("0"))
    adjustment_amount = sum((Decimal(x.amount) for x in entries if x.entry_type != "CONFIRMATION"), Decimal("0"))
    total_amount = sum((Decimal(x.amount) for x in entries), Decimal("0"))
    period_start = min((x.created_at for x in entries), default=None)
    period_end = max((x.created_at for x in entries), default=None)
    now = utcnow()

    batch = PayoutBatch(
        agent_id=agent_id,
        period_start=period_start,
        period_end=period_end,
        entries_count=len(entries),
        base_amount=base_amount,
        adjustment_amount=adjustment_amount,
        total_amount=total_amount,
        payment_method=payload.payment_method.upper(),
        payment_reference=payload.payment_reference,
        note=payload.note,
        paid_by_user_id=user.id,
        paid_at=now,
    )
    db.add(batch)
    db.flush()
    for entry in entries:
        entry.status = "PAID"
        entry.payment_batch_id = batch.id
        entry.paid_at = now
    log_action(db, user_id=user.id, action="AGENT_PAYMENT_SETTLED", entity_type="AGENT", entity_id=agent_id, after={"batch_id": batch.id, "entries": len(entries), "total": str(total_amount), "method": batch.payment_method})
    db.commit()
    db.refresh(batch)
    return {
        "batch_id": batch.id,
        "agent_id": agent_id,
        "agent_name": agent.display_name,
        "entries_count": len(entries),
        "total_amount": str(total_amount),
        "payment_method": batch.payment_method,
        "paid_at": batch.paid_at,
        "remaining_unpaid_balance": str(unpaid_balance(db, agent_id)),
    }
