from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import date_bounds, utcnow
from app.models import AgentProduct, Order, User


# These statuses still represent work waiting for the agent.
OPEN_CALL_STATUSES = (
    "NEW",
    "NO_ANSWER",
    "BUSY",
    "CALLBACK",
    "FOLLOW_UP",
)

PERFORMANCE_LOOKBACK_DAYS = 30
RECENT_ASSIGNMENT_HOURS = 24


def _avg_response_seconds(
    db: Session,
    agent_id: str,
    since,
) -> float | None:
    """
    Real response time:
    assigned_at -> first_call_at

    We cap extreme values at 6 hours so one abandoned lead
    does not destroy an agent's score forever.
    """

    rows = (
        db.query(
            Order.assigned_at,
            Order.first_call_at,
        )
        .filter(
            Order.assigned_agent_id == agent_id,
            Order.created_at >= since,
            Order.assigned_at.isnot(None),
            Order.first_call_at.isnot(None),
        )
        .all()
    )

    values: list[float] = []

    for assigned_at, first_call_at in rows:
        if not assigned_at or not first_call_at:
            continue

        seconds = (
            first_call_at - assigned_at
        ).total_seconds()

        if seconds < 0:
            continue

        # Ignore extreme waiting-time influence.
        values.append(
            min(float(seconds), 6 * 60 * 60)
        )

    if not values:
        return None

    return sum(values) / len(values)


def choose_agent(
    db: Session,
    product_id: str,
    customer_id: str | None = None,
) -> User | None:
    """
    Smart COD lead router.

    Priority:
    1. Lowest current open workload.
    2. Better product confirmation performance.
    3. Faster first-response time.
    4. Fewer recent assignments.
    5. Agent waiting longest for the next lead.

    IMPORTANT:
    Performance NEVER overrides a lower workload.
    """

    agents = (
        db.query(User)
        .join(
            AgentProduct,
            AgentProduct.agent_id == User.id,
        )
        .filter(
            User.role == "AGENT",
            User.is_active.is_(True),
            AgentProduct.product_id == product_id,
        )
        .all()
    )

    if not agents:
        return None

    now = utcnow()
    today_start, today_end = date_bounds("today", None, None)

    # --------------------------------------------------
    # SAME CUSTOMER / SAME DAY
    #
    # If this customer already has an order assigned today,
    # keep every new order with the same eligible agent.
    # This prevents two agents from confirming the same client.
    # --------------------------------------------------
    if customer_id:
        same_customer_order = (
            db.query(Order)
            .filter(
                Order.customer_id == customer_id,
                Order.assigned_agent_id.isnot(None),
                Order.created_at >= today_start,
                Order.created_at < today_end,
            )
            .order_by(Order.created_at.asc())
            .first()
        )

        if same_customer_order:
            same_agent = next(
                (
                    agent
                    for agent in agents
                    if agent.id == same_customer_order.assigned_agent_id
                ),
                None,
            )

            # Reuse only if that agent is active and authorized
            # for the current product (already guaranteed by agents list).
            if same_agent:
                return same_agent

    performance_since = (
        now
        - timedelta(
            days=PERFORMANCE_LOOKBACK_DAYS
        )
    )

    recent_since = (
        now
        - timedelta(
            hours=RECENT_ASSIGNMENT_HOURS
        )
    )

    scored = []

    for agent in agents:

        # --------------------------------------------------
        # DAILY FAIRNESS — ABSOLUTE PRIORITY
        #
        # Count only leads created today that are currently
        # assigned to this agent. Existing leads are NEVER
        # modified; this only decides who gets the NEXT lead.
        # --------------------------------------------------
        assigned_today = (
            db.query(func.count(Order.id))
            .filter(
                Order.assigned_agent_id == agent.id,
                Order.created_at >= today_start,
                Order.created_at < today_end,
            )
            .scalar()
            or 0
        )

        # --------------------------------------------------
        # 1. CURRENT TOTAL WORKLOAD
        #
        # Count ALL open leads assigned to this agent,
        # even when they belong to another product.
        # --------------------------------------------------

        open_load = (
            db.query(func.count(Order.id))
            .filter(
                Order.assigned_agent_id == agent.id,
                Order.call_status.in_(
                    OPEN_CALL_STATUSES
                ),
            )
            .scalar()
            or 0
        )

        # --------------------------------------------------
        # 2. PRODUCT-SPECIFIC PERFORMANCE
        #
        # Only compare leads the agent has actually started
        # handling. New/unopened leads do not hurt CR.
        # --------------------------------------------------

        handled = (
            db.query(func.count(Order.id))
            .filter(
                Order.assigned_agent_id == agent.id,
                Order.product_id == product_id,
                Order.created_at >= performance_since,
                Order.first_call_at.isnot(None),
            )
            .scalar()
            or 0
        )

        confirmed = (
            db.query(func.count(Order.id))
            .filter(
                Order.assigned_agent_id == agent.id,
                Order.product_id == product_id,
                Order.created_at >= performance_since,
                Order.call_status == "CONFIRMED",
            )
            .scalar()
            or 0
        )

        # Bayesian smoothing.
        #
        # A new agent does not start at 0%.
        # Prior = 2 confirmed / 4 handled = 50%.
        confirmation_score = (
            float(confirmed) + 2.0
        ) / (
            float(handled) + 4.0
        )

        # --------------------------------------------------
        # 3. REAL FIRST RESPONSE SPEED
        # --------------------------------------------------

        avg_response_seconds = (
            _avg_response_seconds(
                db,
                agent.id,
                performance_since,
            )
        )

        # Neutral score for a new agent.
        if avg_response_seconds is None:
            speed_score = 0.50
        else:
            # 0 min ~= 1.0
            # 15 min ~= 0.5
            # 30+ min ~= 0.0
            speed_score = max(
                0.0,
                min(
                    1.0,
                    1.0
                    - (
                        float(
                            avg_response_seconds
                        )
                        / 1800.0
                    ),
                ),
            )

        quality_score = (
            confirmation_score * 0.70
            + speed_score * 0.30
        )

        # --------------------------------------------------
        # 4. RECENT FAIRNESS
        # --------------------------------------------------

        recent_assignments = (
            db.query(func.count(Order.id))
            .filter(
                Order.assigned_agent_id == agent.id,
                Order.assigned_at >= recent_since,
            )
            .scalar()
            or 0
        )

        last_assigned = (
            db.query(
                func.max(Order.assigned_at)
            )
            .filter(
                Order.assigned_agent_id == agent.id
            )
            .scalar()
        )

        last_assigned_ts = (
            last_assigned.timestamp()
            if last_assigned
            else 0.0
        )

        # --------------------------------------------------
        # SORT KEY
        #
        # IMPORTANT:
        # open_load comes FIRST.
        #
        # Therefore an agent with 2 open leads ALWAYS
        # beats an agent with 12 open leads.
        # --------------------------------------------------

        scored.append(
            (
                int(assigned_today),
                int(open_load),
                -float(quality_score),
                int(recent_assignments),
                float(last_assigned_ts),
                agent,
            )
        )

    scored.sort(
        key=lambda item: (
            item[0],  # fewest leads assigned today
            item[1],  # lowest open load
            item[2],  # highest quality
            item[3],  # fewer recent leads
            item[4],  # longest since last assignment
        )
    )

    return scored[0][5]
