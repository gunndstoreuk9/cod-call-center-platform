"""Assign the (unassigned) orders of one import batch to active agents with the production routing logic.

Dry run by default (rolled back). --apply needs --confirm-batch. Retry-safe: orders that already have an agent are skipped, and no
second OrderAssignment is ever written for them. Several orders of one customer go to ONE agent and get a visible verification note.
Order status stays NEW; nothing else is touched.

    python -m scripts.assign_batch --source STORE_CSV_BACKFILL --batch 2026-11-06-csv [--apply --confirm-batch 2026-11-06-csv]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from sqlalchemy import func

from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models import IntegrationEvent, Order, OrderAssignment, User
from app.services.assignment import OPEN_CALL_STATUSES, choose_agent
from app.services.audit import log_action
from app.services.payouts import reconcile_confirmation_payout

FLAG = "[VERIFY - SAME CUSTOMER]"


def run(db, source: str, batch: str, apply: bool) -> dict:
    evs = (db.query(IntegrationEvent).join(Order, Order.id == IntegrationEvent.entity_id)
           .filter(Order.source == source, IntegrationEvent.event_type == "ORDER_IMPORT", IntegrationEvent.status == "SUCCESS").all())
    ids = [e.entity_id for e in evs if (e.payload or {}).get("batch") == batch or ((e.payload or {}).get("source") or {}).get("recovery_batch") == batch]
    if not ids:
        raise SystemExit("refusing: no orders found for that source/batch")
    owner = db.query(User).filter(User.role == "OWNER", User.is_active.is_(True)).first()
    agents = db.query(User).filter(User.role == "AGENT").all()
    load = lambda a: db.query(func.count(Order.id)).filter(Order.assigned_agent_id == a.id, Order.call_status.in_(OPEN_CALL_STATUSES)).scalar()
    before = {a.display_name: load(a) for a in agents}
    orders = db.query(Order).filter(Order.id.in_(ids)).order_by(Order.customer_id, Order.created_at).all()
    by_customer: dict[str, list[Order]] = {}
    for o in orders:
        by_customer.setdefault(o.customer_id, []).append(o)
    outer = db.begin_nested()
    assigned, skipped, per = [], 0, Counter()
    try:
        for cust, os_ in by_customer.items():
            agent = None
            for o in os_:
                if o.assigned_agent_id:
                    skipped += 1
                    agent = agent or next((a for a in agents if a.id == o.assigned_agent_id), None)
                    continue
                agent = agent or choose_agent(db, o.product_id, o.customer_id)
                if agent is None:
                    raise RuntimeError(f"no eligible agent for {o.order_number}")
                o.assigned_agent_id, o.assigned_at = agent.id, utcnow()
                db.add(OrderAssignment(order_id=o.id, agent_id=agent.id, assigned_by_user_id=owner.id, assignment_type="SMART_SCORE"))
                reconcile_confirmation_payout(db, o)
                log_action(db, user_id=owner.id, action="ORDER_AUTO_ASSIGNED", entity_type="ORDER", entity_id=o.id, before={"agent_id": None}, after={"agent_id": agent.id, "batch": batch})
                db.flush()
                assigned.append((o.order_number, agent.display_name)); per[agent.display_name] += 1
            if len(os_) > 1:
                nums = ", ".join(sorted(o.order_number for o in os_))
                for o in os_:
                    if FLAG not in (o.call_note or ""):
                        o.call_note = ((o.call_note or "").rstrip() + "\n") + f"{FLAG} {len(os_)} orders from this phone number ({nums}). Call the customer ONCE, ask which orders they intended, and do NOT confirm duplicates."
        after = {a.display_name: load(a) for a in agents}
        if apply:
            outer.commit(); db.commit()
        else:
            outer.rollback(); db.rollback()
    except Exception:
        db.rollback(); raise
    return {"apply": apply, "batch": batch, "orders_in_batch": len(ids), "assigned_now": len(assigned), "skipped_already_assigned": skipped, "per_agent": dict(per),
            "workload_before": before, "workload_after_inside_transaction": after, "multi_order_customers": sum(1 for v in by_customer.values() if len(v) > 1),
            "still_unassigned": db.query(func.count(Order.id)).filter(Order.id.in_(ids), Order.assigned_agent_id.is_(None)).scalar()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm-batch", default="")
    a = ap.parse_args()
    if a.apply and a.confirm_batch != a.batch:
        raise SystemExit("refusing: --apply needs --confirm-batch equal to --batch")
    print("ASSIGN_JSON:" + json.dumps(run(SessionLocal(), a.source, a.batch, a.apply)))


if __name__ == "__main__":
    main()
