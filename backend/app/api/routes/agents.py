from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import current_user, require_roles
from app.core.security import hash_password
from app.core.time import date_bounds, utcnow
from app.models import AgentProduct, Order, OrderAssignment, PayoutEntry, Product, User
from app.schemas import AgentCreate, AgentOut, AgentUpdate
from app.services.assignment import OPEN_CALL_STATUSES, choose_agent
from app.services.audit import log_action
from app.services.payouts import unpaid_balance

router = APIRouter(prefix="/agents", tags=["agents"])


def agent_payload(db: Session, agent: User) -> dict:
    product_ids = [x.product_id for x in db.query(AgentProduct).filter(AgentProduct.agent_id == agent.id).all()]
    return {
        "id": agent.id,
        "username": agent.username,
        "display_name": agent.display_name,
        "role": agent.role,
        "is_active": agent.is_active,
        "phone": agent.phone,
        "email": agent.email,
        "commission_default": agent.commission_default,
        "product_ids": product_ids,
        "current_balance": unpaid_balance(db, agent.id),
    }


def set_products(db: Session, agent_id: str, product_ids: list[str]) -> None:
    valid = {x.id for x in db.query(Product).filter(Product.id.in_(product_ids)).all()} if product_ids else set()
    missing = set(product_ids) - valid
    if missing:
        raise HTTPException(400, f"Invalid product ids: {', '.join(sorted(missing))}")
    db.query(AgentProduct).filter(AgentProduct.agent_id == agent_id).delete(synchronize_session=False)
    for product_id in product_ids:
        db.add(AgentProduct(agent_id=agent_id, product_id=product_id))


@router.get("", response_model=list[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    agents = db.query(User).filter(User.role == "AGENT").order_by(User.display_name.asc()).all()
    return [agent_payload(db, a) for a in agents]


@router.post("", response_model=AgentOut)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    username = payload.username.strip().lower()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "Username already exists")
    if payload.role != "AGENT":
        raise HTTPException(400, "This endpoint creates AGENT users only")
    agent = User(
        username=username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role="AGENT",
        phone=payload.phone,
        email=payload.email,
        commission_default=payload.commission_default,
        is_active=True,
    )
    db.add(agent)
    db.flush()
    set_products(db, agent.id, payload.product_ids)
    log_action(db, user_id=user.id, action="AGENT_CREATED", entity_type="AGENT", entity_id=agent.id, after={"username": agent.username, "display_name": agent.display_name, "products": payload.product_ids})
    db.commit()
    db.refresh(agent)
    return agent_payload(db, agent)


@router.patch("/{agent_id}", response_model=AgentOut)
def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    agent = db.query(User).filter(User.id == agent_id, User.role == "AGENT").first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    before = {"display_name": agent.display_name, "is_active": agent.is_active, "commission_default": str(agent.commission_default)}
    updates = payload.model_dump(exclude_unset=True, exclude={"password", "product_ids"})
    if "username" in updates and updates["username"]:
        updates["username"] = updates["username"].strip().lower()
        exists = db.query(User).filter(User.username == updates["username"], User.id != agent_id).first()
        if exists:
            raise HTTPException(409, "Username already exists")
    for key, value in updates.items():
        setattr(agent, key, value)
    if payload.password:
        agent.password_hash = hash_password(payload.password)
    if payload.product_ids is not None:
        set_products(db, agent.id, payload.product_ids)
    log_action(db, user_id=user.id, action="AGENT_UPDATED", entity_type="AGENT", entity_id=agent.id, before=before, after={"display_name": agent.display_name, "is_active": agent.is_active, "commission_default": str(agent.commission_default)})
    db.commit()
    db.refresh(agent)
    return agent_payload(db, agent)



@router.post("/{agent_id}/remove")
def remove_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    agent = (
        db.query(User)
        .filter(
            User.id == agent_id,
            User.role == "AGENT",
        )
        .first()
    )

    if not agent:
        raise HTTPException(404, "Agent not found")

    open_orders = (
        db.query(Order)
        .filter(
            Order.assigned_agent_id == agent.id,
            Order.call_status.in_(OPEN_CALL_STATUSES),
        )
        .order_by(Order.created_at.asc())
        .all()
    )

    before = {
        "display_name": agent.display_name,
        "is_active": agent.is_active,
        "open_leads": len(open_orders),
    }

    # Immediately block login and future auto assignment.
    agent.is_active = False

    # Remove product access.
    db.query(AgentProduct).filter(
        AgentProduct.agent_id == agent.id
    ).delete(synchronize_session=False)

    db.flush()

    reassigned = 0
    unassigned = 0

    for order in open_orders:
        now = utcnow()

        # Close the previous active assignment history entry.
        previous_assignment = (
            db.query(OrderAssignment)
            .filter(
                OrderAssignment.order_id == order.id,
                OrderAssignment.agent_id == agent.id,
                OrderAssignment.released_at.is_(None),
            )
            .order_by(OrderAssignment.assigned_at.desc())
            .first()
        )

        if previous_assignment:
            previous_assignment.released_at = now

        # Smart balancer now ignores the removed agent because
        # the agent is inactive and has no product access.
        new_agent = choose_agent(db, order.product_id)

        if new_agent:
            order.assigned_agent_id = new_agent.id
            order.assigned_at = now

            db.add(
                OrderAssignment(
                    order_id=order.id,
                    agent_id=new_agent.id,
                    assigned_by_user_id=user.id,
                    assignment_type="AGENT_REMOVAL_REASSIGN",
                )
            )

            reassigned += 1
        else:
            # Keep the lead safely unassigned if no eligible agent exists.
            order.assigned_agent_id = None
            order.assigned_at = None
            unassigned += 1

        # Important: next choose_agent() sees the updated workloads.
        db.flush()

    log_action(
        db,
        user_id=user.id,
        action="AGENT_REMOVED",
        entity_type="AGENT",
        entity_id=agent.id,
        before=before,
        after={
            "is_active": False,
            "products_removed": True,
            "open_leads": len(open_orders),
            "reassigned": reassigned,
            "unassigned": unassigned,
        },
    )

    db.commit()

    return {
        "ok": True,
        "agent_id": agent.id,
        "display_name": agent.display_name,
        "open_leads": len(open_orders),
        "reassigned": reassigned,
        "unassigned": unassigned,
        "message": "Agent removed and open leads redistributed.",
    }


@router.get("/{agent_id}/stats")
def agent_stats(
    agent_id: str,
    range: str = "today",
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role == "AGENT" and user.id != agent_id:
        raise HTTPException(403, "Agents can only view their own stats")
    agent = db.query(User).filter(User.id == agent_id, User.role == "AGENT").first()
    if not agent:
        raise HTTPException(404, "Agent not found")
    start, end = date_bounds(range, from_date, to_date)
    q = db.query(Order).filter(Order.assigned_agent_id == agent_id, Order.created_at >= start, Order.created_at < end)
    total = q.count()
    confirmed = q.filter(Order.call_status == "CONFIRMED").count()
    delivered = q.filter(Order.delivery_status == "DELIVERED").count()
    return {
        "agent_id": agent_id,
        "display_name": agent.display_name,
        "range": range,
        "assigned": total,
        "confirmed": confirmed,
        "confirmation_rate": round((confirmed / total * 100), 2) if total else 0,
        "delivered": delivered,
        "confirmed_to_delivered_rate": round((delivered / confirmed * 100), 2) if confirmed else 0,
        "no_answer": q.filter(Order.call_status == "NO_ANSWER").count(),
        "callbacks": q.filter(Order.call_status == "CALLBACK").count(),
        "cancelled": q.filter(Order.call_status == "CANCELLED").count(),
        "current_unpaid_balance": str(unpaid_balance(db, agent_id)),
    }
