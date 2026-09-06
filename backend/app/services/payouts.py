from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import AgentProduct, Order, PayoutEntry, Product, ProductOffer, User
from app.core.time import utcnow


def commission_for_order(db: Session, order: Order) -> Decimal:
    agent = db.query(User).filter(User.id == order.assigned_agent_id).first()
    product = db.query(Product).filter(Product.id == order.product_id).first()
    offer = db.query(ProductOffer).filter(ProductOffer.id == order.offer_id).first() if order.offer_id else None
    agent_product = (
        db.query(AgentProduct)
        .filter(AgentProduct.agent_id == order.assigned_agent_id, AgentProduct.product_id == order.product_id)
        .first()
        if order.assigned_agent_id
        else None
    )
    if agent_product and agent_product.commission_override is not None:
        return Decimal(agent_product.commission_override)
    if offer and offer.commission_override is not None:
        return Decimal(offer.commission_override)
    if product and product.commission_per_confirmation is not None:
        return Decimal(product.commission_per_confirmation)
    if agent:
        return Decimal(agent.commission_default)
    return Decimal("0")


def reconcile_confirmation_payout(db: Session, order: Order) -> None:
    positives = (
        db.query(PayoutEntry)
        .filter(PayoutEntry.order_id == order.id, PayoutEntry.entry_type == "CONFIRMATION")
        .all()
    )
    target_agent = order.assigned_agent_id if order.call_status == "CONFIRMED" else None

    for entry in positives:
        valid = target_agent and entry.agent_id == target_agent
        if valid:
            if entry.status == "VOID":
                entry.status = "UNPAID"
            reversal = (
                db.query(PayoutEntry)
                .filter(
                    PayoutEntry.entry_type == "REVERSAL",
                    PayoutEntry.description == f"AUTO_REVERSAL:{entry.id}",
                    PayoutEntry.status == "UNPAID",
                )
                .first()
            )
            if reversal:
                reversal.status = "VOID"
            continue

        if entry.status == "UNPAID":
            entry.status = "VOID"
        elif entry.status == "PAID":
            reversal = (
                db.query(PayoutEntry)
                .filter(
                    PayoutEntry.entry_type == "REVERSAL",
                    PayoutEntry.description == f"AUTO_REVERSAL:{entry.id}",
                    PayoutEntry.status.in_(["UNPAID", "PAID"]),
                )
                .first()
            )
            if not reversal:
                db.add(
                    PayoutEntry(
                        agent_id=entry.agent_id,
                        order_id=order.id,
                        product_id=order.product_id,
                        entry_type="REVERSAL",
                        amount=-Decimal(entry.amount),
                        status="UNPAID",
                        description=f"AUTO_REVERSAL:{entry.id}",
                    )
                )

    if target_agent:
        valid_positive = (
            db.query(PayoutEntry)
            .filter(
                PayoutEntry.order_id == order.id,
                PayoutEntry.agent_id == target_agent,
                PayoutEntry.entry_type == "CONFIRMATION",
                PayoutEntry.status.in_(["UNPAID", "PAID"]),
            )
            .first()
        )
        if not valid_positive:
            db.add(
                PayoutEntry(
                    agent_id=target_agent,
                    order_id=order.id,
                    product_id=order.product_id,
                    entry_type="CONFIRMATION",
                    amount=commission_for_order(db, order),
                    status="UNPAID",
                    description=f"Confirmation commission for {order.order_number}",
                )
            )


def unpaid_balance(db: Session, agent_id: str) -> Decimal:
    entries = db.query(PayoutEntry).filter(PayoutEntry.agent_id == agent_id, PayoutEntry.status == "UNPAID").all()
    return sum((Decimal(x.amount) for x in entries), Decimal("0"))
