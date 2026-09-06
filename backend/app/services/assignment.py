from datetime import timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.time import utcnow
from app.models import AgentProduct, CallAttempt, Order, User


def choose_agent(db: Session, product_id: str) -> User | None:
    agents = (
        db.query(User)
        .join(AgentProduct, AgentProduct.agent_id == User.id)
        .filter(User.role == "AGENT", User.is_active.is_(True), AgentProduct.product_id == product_id)
        .all()
    )
    if not agents:
        return None

    since = utcnow() - timedelta(days=30)
    scored: list[tuple[float, User]] = []
    for agent in agents:
        assigned = db.query(func.count(Order.id)).filter(Order.assigned_agent_id == agent.id, Order.created_at >= since).scalar() or 0
        confirmed = db.query(func.count(Order.id)).filter(
            Order.assigned_agent_id == agent.id,
            Order.call_status == "CONFIRMED",
            Order.created_at >= since,
        ).scalar() or 0
        open_load = db.query(func.count(Order.id)).filter(
            Order.assigned_agent_id == agent.id,
            Order.call_status.in_(["NEW", "NO_ANSWER", "BUSY", "CALLBACK"]),
        ).scalar() or 0
        avg_first_call = db.query(func.avg(CallAttempt.duration_seconds)).filter(
            CallAttempt.agent_id == agent.id,
            CallAttempt.created_at >= since,
        ).scalar()

        confirmation_score = (confirmed / assigned) if assigned else 0.5
        speed_score = 1.0 if avg_first_call is None else max(0.0, min(1.0, 1.0 - (float(avg_first_call) / 600.0)))
        load_score = 1.0 / (1.0 + float(open_load))
        score = confirmation_score * 0.40 + speed_score * 0.30 + load_score * 0.30
        scored.append((score, agent))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]
