import secrets
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user, require_roles
from app.core.time import utcnow
from app.models import (
    AgentProduct,
    CallAttempt,
    Callback,
    Customer,
    DeliveryShipment,
    Order,
    OrderAssignment,
    OrderStatusHistory,
    PayoutEntry,
    Product,
    ProductOffer,
    Store,
    User,
)
from app.schemas import AssignRequest, CallAttemptCreate, CallbackCreate, ManualOrderCreate, OrderOut, OrderUpdate
from app.services.assignment import choose_agent
from app.services.audit import log_action
from app.services.phone import normalize_phone
from app.services.payouts import reconcile_confirmation_payout

router = APIRouter(prefix="/orders", tags=["orders"])

CALL_STATUSES = {"NEW", "NO_ANSWER", "BUSY", "CALLBACK", "CONFIRMED", "CANCELLED", "WRONG_NUMBER", "DUPLICATE", "BLACKLIST", "NOT_INTERESTED"}
DELIVERY_STATUSES = {"NOT_READY", "READY", "DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "REFUSED", "RETURNED", "CANCELLED", "ISSUE"}


def new_order_number() -> str:
    return f"CC-{datetime.now().strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"


def order_to_dict(db: Session, order: Order) -> dict:
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    product = db.query(Product).filter(Product.id == order.product_id).first()
    agent = db.query(User).filter(User.id == order.assigned_agent_id).first() if order.assigned_agent_id else None
    data = {c.name: getattr(order, c.name) for c in order.__table__.columns}
    shipment = db.query(DeliveryShipment).filter(DeliveryShipment.order_id == order.id).order_by(DeliveryShipment.created_at.desc()).first()
    data.update({
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.phone_e164 if customer else None,
        "product_name": product.name if product else None,
        "product_sku": product.sku if product else None,
        "agent_name": agent.display_name if agent else None,
        "delivery_provider": shipment.provider if shipment else None,
        "delivery_tracking": shipment.tracking_number if shipment else None,
        "delivery_error": shipment.error if shipment else None,
    })
    return data


def assert_order_access(order: Order, user: User) -> None:
    if user.role == "AGENT" and order.assigned_agent_id != user.id:
        raise HTTPException(403, "This order is not assigned to you")


def apply_status_side_effects(order: Order, previous_call: str | None = None, previous_delivery: str | None = None) -> None:
    now = utcnow()
    if order.call_status == "CONFIRMED" and previous_call != "CONFIRMED" and not order.confirmed_at:
        order.confirmed_at = now
    if order.delivery_status == "DISPATCHED" and previous_delivery != "DISPATCHED" and not order.dispatched_at:
        order.dispatched_at = now
    if order.delivery_status == "DELIVERED" and previous_delivery != "DELIVERED" and not order.delivered_at:
        order.delivered_at = now


@router.get("", response_model=list[OrderOut])
def list_orders(
    range: str | None = None,
    product_id: str | None = None,
    agent_id: str | None = None,
    call_status: str | None = None,
    delivery_status: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    q = db.query(Order)
    if user.role == "AGENT":
        q = q.filter(Order.assigned_agent_id == user.id)
    elif agent_id:
        q = q.filter(Order.assigned_agent_id == agent_id)
    if product_id:
        q = q.filter(Order.product_id == product_id)
    if call_status:
        q = q.filter(Order.call_status == call_status.upper())
    if delivery_status:
        q = q.filter(Order.delivery_status == delivery_status.upper())
    if search:
        customer_ids = [x.id for x in db.query(Customer).filter(or_(Customer.name.ilike(f"%{search}%"), Customer.phone_e164.ilike(f"%{search}%"))).all()]
        q = q.filter(or_(Order.order_number.ilike(f"%{search}%"), Order.customer_id.in_(customer_ids)))
    rows = q.order_by(Order.created_at.desc()).offset(max(offset, 0)).limit(min(max(limit, 1), 500)).all()
    return [order_to_dict(db, x) for x in rows]


@router.get("/my-queue", response_model=list[OrderOut])
def my_queue(
    bucket: str = "NEW",
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("AGENT")),
):
    q = db.query(Order).filter(Order.assigned_agent_id == user.id)
    bucket = bucket.upper()
    if bucket == "FOLLOW_UP":
        q = q.filter(Order.call_status.in_(["NO_ANSWER", "BUSY", "CALLBACK"]))
    elif bucket == "CONFIRMED":
        q = q.filter(Order.call_status == "CONFIRMED")
    elif bucket != "ALL":
        q = q.filter(Order.call_status == bucket)
    return [order_to_dict(db, x) for x in q.order_by(Order.created_at.asc()).limit(min(limit, 200)).all()]


@router.post("/manual", response_model=OrderOut)
def create_manual_order(
    payload: ManualOrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    store = db.query(Store).filter(Store.id == payload.store_id).first()
    product = db.query(Product).filter(Product.id == payload.product_id, Product.store_id == payload.store_id).first()
    if not store or not product:
        raise HTTPException(400, "Invalid store/product combination")
    offer = db.query(ProductOffer).filter(ProductOffer.id == payload.offer_id, ProductOffer.product_id == product.id, ProductOffer.is_active.is_(True)).first() if payload.offer_id else None
    if payload.offer_id and not offer:
        raise HTTPException(400, "Invalid product offer")

    phone = normalize_phone(payload.phone, store.country)
    customer = db.query(Customer).filter(Customer.phone_e164 == phone).first()
    if not customer:
        customer = Customer(name=payload.customer_name.strip(), phone_raw=payload.phone, phone_e164=phone, city=payload.city, address=payload.address)
        db.add(customer)
        db.flush()
    else:
        customer.name = payload.customer_name.strip() or customer.name
        customer.city = payload.city or customer.city
        customer.address = payload.address or customer.address

    qty = offer.quantity if offer else payload.quantity
    unit_price = Decimal(payload.unit_price) if payload.unit_price is not None else (Decimal(offer.price) / offer.quantity if offer else Decimal(product.selling_price))
    total = Decimal(payload.total_price) if payload.total_price is not None else (Decimal(offer.price) if offer else unit_price * qty)
    if payload.assigned_agent_id:
        agent = db.query(User).filter(User.id == payload.assigned_agent_id, User.role == "AGENT", User.is_active.is_(True)).first()
        if not agent:
            raise HTTPException(400, "Invalid agent")
        allowed = db.query(AgentProduct).filter(AgentProduct.agent_id == agent.id, AgentProduct.product_id == product.id).first()
        if not allowed:
            raise HTTPException(400, "Agent is not enabled for this product")

    call_status = payload.call_status.upper()
    if call_status not in CALL_STATUSES:
        raise HTTPException(400, "Invalid call status")
    row = Order(
        order_number=new_order_number(),
        store_id=store.id,
        product_id=product.id,
        offer_id=offer.id if offer else None,
        customer_id=customer.id,
        assigned_agent_id=payload.assigned_agent_id,
        quantity=qty,
        unit_price=unit_price,
        total_price=total,
        currency=product.currency or store.currency,
        source=payload.source.upper(),
        call_status=call_status,
        call_note=payload.call_note,
        city=payload.city,
        address=payload.address,
        assigned_at=utcnow() if payload.assigned_agent_id else None,
    )
    db.add(row)
    db.flush()
    if payload.assigned_agent_id:
        db.add(OrderAssignment(order_id=row.id, agent_id=payload.assigned_agent_id, assigned_by_user_id=user.id, assignment_type="MANUAL"))
    apply_status_side_effects(row, previous_call=None)
    reconcile_confirmation_payout(db, row)
    log_action(db, user_id=user.id, action="ORDER_MANUAL_CREATED", entity_type="ORDER", entity_id=row.id, after={"order_number": row.order_number, "product_id": row.product_id, "total": str(row.total_price)})
    db.commit()
    db.refresh(row)
    return order_to_dict(db, row)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.query(Order).filter(Order.id == order_id).first()
    if not row:
        raise HTTPException(404, "Order not found")
    assert_order_access(row, user)
    return order_to_dict(db, row)


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(
    order_id: str,
    payload: OrderUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    row = db.query(Order).filter(Order.id == order_id).first()
    if not row:
        raise HTTPException(404, "Order not found")
    assert_order_access(row, user)
    updates = payload.model_dump(exclude_unset=True)
    if user.role == "AGENT" and "assigned_agent_id" in updates and updates["assigned_agent_id"] != user.id:
        raise HTTPException(403, "Agents cannot reassign orders")
    if "call_status" in updates and updates["call_status"]:
        updates["call_status"] = updates["call_status"].upper()
        if updates["call_status"] not in CALL_STATUSES:
            raise HTTPException(400, "Invalid call status")
    if "delivery_status" in updates and updates["delivery_status"]:
        updates["delivery_status"] = updates["delivery_status"].upper()
        if updates["delivery_status"] not in DELIVERY_STATUSES:
            raise HTTPException(400, "Invalid delivery status")

    previous_call = row.call_status
    previous_delivery = row.delivery_status
    previous_agent = row.assigned_agent_id
    before = {"call_status": previous_call, "delivery_status": previous_delivery, "assigned_agent_id": previous_agent, "total_price": str(row.total_price)}
    for key, value in updates.items():
        setattr(row, key, value)
    if row.assigned_agent_id != previous_agent:
        row.assigned_at = utcnow() if row.assigned_agent_id else None
        if previous_agent:
            active_assignment = db.query(OrderAssignment).filter(OrderAssignment.order_id == row.id, OrderAssignment.agent_id == previous_agent, OrderAssignment.released_at.is_(None)).order_by(OrderAssignment.assigned_at.desc()).first()
            if active_assignment:
                active_assignment.released_at = utcnow()
        if row.assigned_agent_id:
            db.add(OrderAssignment(order_id=row.id, agent_id=row.assigned_agent_id, assigned_by_user_id=user.id, assignment_type="REASSIGNED"))

    apply_status_side_effects(row, previous_call, previous_delivery)
    if row.call_status != previous_call or row.delivery_status != previous_delivery:
        db.add(OrderStatusHistory(
            order_id=row.id,
            from_call_status=previous_call,
            to_call_status=row.call_status,
            from_delivery_status=previous_delivery,
            to_delivery_status=row.delivery_status,
            changed_by_user_id=user.id,
        ))
    reconcile_confirmation_payout(db, row)
    log_action(db, user_id=user.id, action="ORDER_UPDATED", entity_type="ORDER", entity_id=row.id, before=before, after={"call_status": row.call_status, "delivery_status": row.delivery_status, "assigned_agent_id": row.assigned_agent_id, "total_price": str(row.total_price)})
    db.commit()
    db.refresh(row)
    return order_to_dict(db, row)


@router.post("/{order_id}/assign", response_model=OrderOut)
def assign_order(
    order_id: str,
    payload: AssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    row = db.query(Order).filter(Order.id == order_id).first()
    agent = db.query(User).filter(User.id == payload.agent_id, User.role == "AGENT", User.is_active.is_(True)).first()
    if not row or not agent:
        raise HTTPException(404, "Order or agent not found")
    allowed = db.query(AgentProduct).filter(AgentProduct.agent_id == agent.id, AgentProduct.product_id == row.product_id).first()
    if not allowed:
        raise HTTPException(400, "Agent is not enabled for this product")
    previous = row.assigned_agent_id
    row.assigned_agent_id = agent.id
    row.assigned_at = utcnow()
    if previous and previous != agent.id:
        active = db.query(OrderAssignment).filter(OrderAssignment.order_id == row.id, OrderAssignment.agent_id == previous, OrderAssignment.released_at.is_(None)).first()
        if active:
            active.released_at = utcnow()
    db.add(OrderAssignment(order_id=row.id, agent_id=agent.id, assigned_by_user_id=user.id, assignment_type=payload.assignment_type.upper()))
    reconcile_confirmation_payout(db, row)
    log_action(db, user_id=user.id, action="ORDER_ASSIGNED", entity_type="ORDER", entity_id=row.id, before={"agent_id": previous}, after={"agent_id": agent.id})
    db.commit()
    db.refresh(row)
    return order_to_dict(db, row)


@router.post("/{order_id}/auto-assign", response_model=OrderOut)
def auto_assign_order(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    row = db.query(Order).filter(Order.id == order_id).first()
    if not row:
        raise HTTPException(404, "Order not found")
    agent = choose_agent(db, row.product_id)
    if not agent:
        raise HTTPException(409, "No active agent is enabled for this product")
    previous = row.assigned_agent_id
    row.assigned_agent_id = agent.id
    row.assigned_at = utcnow()
    db.add(OrderAssignment(order_id=row.id, agent_id=agent.id, assigned_by_user_id=user.id, assignment_type="SMART_SCORE"))
    reconcile_confirmation_payout(db, row)
    log_action(db, user_id=user.id, action="ORDER_AUTO_ASSIGNED", entity_type="ORDER", entity_id=row.id, before={"agent_id": previous}, after={"agent_id": agent.id})
    db.commit()
    db.refresh(row)
    return order_to_dict(db, row)


@router.post("/{order_id}/call-attempts")
def add_call_attempt(
    order_id: str,
    payload: CallAttemptCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    row = db.query(Order).filter(Order.id == order_id).first()
    if not row:
        raise HTTPException(404, "Order not found")
    assert_order_access(row, user)
    agent_id = user.id if user.role == "AGENT" else row.assigned_agent_id
    if not agent_id:
        raise HTTPException(400, "Assign an agent before recording a call")
    outcome = payload.outcome.upper()
    if outcome not in CALL_STATUSES:
        raise HTTPException(400, "Invalid call outcome")
    started = payload.started_at or utcnow()
    attempt = CallAttempt(
        order_id=row.id,
        agent_id=agent_id,
        channel=payload.channel.upper(),
        outcome=outcome,
        note=payload.note,
        started_at=started,
        ended_at=utcnow(),
        duration_seconds=payload.duration_seconds,
    )
    db.add(attempt)
    previous = row.call_status
    row.call_status = outcome
    row.call_note = payload.note or row.call_note
    if not row.first_call_at:
        row.first_call_at = started
    apply_status_side_effects(row, previous_call=previous)
    db.add(OrderStatusHistory(order_id=row.id, from_call_status=previous, to_call_status=outcome, from_delivery_status=row.delivery_status, to_delivery_status=row.delivery_status, changed_by_user_id=user.id, reason=payload.note))
    reconcile_confirmation_payout(db, row)
    log_action(db, user_id=user.id, action="CALL_ATTEMPT_CREATED", entity_type="ORDER", entity_id=row.id, after={"outcome": outcome, "duration_seconds": payload.duration_seconds})
    db.commit()
    db.refresh(attempt)
    return {"id": attempt.id, "order_id": attempt.order_id, "agent_id": attempt.agent_id, "outcome": attempt.outcome, "created_at": attempt.created_at}


@router.post("/{order_id}/callbacks")
def create_callback(
    order_id: str,
    payload: CallbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    row = db.query(Order).filter(Order.id == order_id).first()
    if not row:
        raise HTTPException(404, "Order not found")
    assert_order_access(row, user)
    agent_id = payload.agent_id or row.assigned_agent_id or (user.id if user.role == "AGENT" else None)
    if not agent_id:
        raise HTTPException(400, "Callback needs an assigned agent")
    cb = Callback(order_id=row.id, agent_id=agent_id, scheduled_at=payload.scheduled_at, reason=payload.reason, note=payload.note)
    db.add(cb)
    previous = row.call_status
    row.call_status = "CALLBACK"
    db.add(OrderStatusHistory(order_id=row.id, from_call_status=previous, to_call_status="CALLBACK", from_delivery_status=row.delivery_status, to_delivery_status=row.delivery_status, changed_by_user_id=user.id, reason=payload.reason))
    reconcile_confirmation_payout(db, row)
    db.commit()
    db.refresh(cb)
    return {"id": cb.id, "order_id": cb.order_id, "scheduled_at": cb.scheduled_at, "status": cb.status}


@router.get("/{order_id}/timeline")
def order_timeline(order_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    row = db.query(Order).filter(Order.id == order_id).first()
    if not row:
        raise HTTPException(404, "Order not found")
    assert_order_access(row, user)
    statuses = db.query(OrderStatusHistory).filter(OrderStatusHistory.order_id == order_id).order_by(OrderStatusHistory.created_at.asc()).all()
    calls = db.query(CallAttempt).filter(CallAttempt.order_id == order_id).order_by(CallAttempt.created_at.asc()).all()
    callbacks = db.query(Callback).filter(Callback.order_id == order_id).order_by(Callback.created_at.asc()).all()
    payouts = db.query(PayoutEntry).filter(PayoutEntry.order_id == order_id).order_by(PayoutEntry.created_at.asc()).all() if user.role != "AGENT" else []
    return {
        "order": order_to_dict(db, row),
        "status_history": [{"from_call": x.from_call_status, "to_call": x.to_call_status, "from_delivery": x.from_delivery_status, "to_delivery": x.to_delivery_status, "reason": x.reason, "created_at": x.created_at} for x in statuses],
        "calls": [{"id": x.id, "agent_id": x.agent_id, "channel": x.channel, "outcome": x.outcome, "note": x.note, "duration_seconds": x.duration_seconds, "created_at": x.created_at} for x in calls],
        "callbacks": [{"id": x.id, "agent_id": x.agent_id, "scheduled_at": x.scheduled_at, "status": x.status, "reason": x.reason, "note": x.note} for x in callbacks],
        "payouts": [{"id": x.id, "agent_id": x.agent_id, "type": x.entry_type, "amount": str(x.amount), "status": x.status, "created_at": x.created_at} for x in payouts],
    }
