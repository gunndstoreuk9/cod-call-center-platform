from pathlib import Path
from functools import lru_cache
import json
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

CALL_STATUSES = {"NEW", "NO_ANSWER", "VOICEMAIL", "BUSY", "CALLBACK", "CONFIRMED", "CANCELLED", "WRONG_NUMBER", "DUPLICATE", "BLACKLIST", "NOT_INTERESTED"}
DELIVERY_STATUSES = {"NOT_READY", "READY", "DISPATCHED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "REFUSED", "RETURNED", "CANCELLED", "ISSUE"}


def new_order_number() -> str:
    return f"CC-{datetime.now().strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"


def order_to_dict(db: Session, order: Order) -> dict:
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    product = db.query(Product).filter(Product.id == order.product_id).first()
    offer = (
        db.query(ProductOffer)
        .filter(ProductOffer.id == order.offer_id)
        .first()
        if order.offer_id
        else None
    )
    store = db.query(Store).filter(Store.id == order.store_id).first()
    agent = db.query(User).filter(User.id == order.assigned_agent_id).first() if order.assigned_agent_id else None
    data = {c.name: getattr(order, c.name) for c in order.__table__.columns}
    shipment = db.query(DeliveryShipment).filter(DeliveryShipment.order_id == order.id).order_by(DeliveryShipment.created_at.desc()).first()
    data.update({
        "customer_name": customer.name if customer else None,
        "customer_phone": customer.phone_e164 if customer else None,
        "product_name": product.name if product else None,
        "product_sku": product.sku if product else None,
        "product_image_url": product.image_url if product else None,
        "offer_name": offer.name if offer else None,
        "offer_quantity": offer.quantity if offer else None,
        "offer_price": offer.price if offer else None,
        "store_name": store.name if store else None,
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

    # Confirmation means ready for delivery, not automatically dispatched.
    if order.call_status == "CONFIRMED":
        if previous_call != "CONFIRMED" and not order.confirmed_at:
            order.confirmed_at = now

        if order.delivery_status in {"NOT_READY", "ISSUE"}:
            order.delivery_status = "READY"

    # Follow-up / closed outcomes are not ready for delivery.
    elif order.call_status in {
        "NEW",
        "NO_ANSWER",
        "VOICEMAIL",
        "BUSY",
        "CALLBACK",
        "CANCELLED",
        "WRONG_NUMBER",
        "DUPLICATE",
        "NOT_INTERESTED",
    }:
        if order.delivery_status == "READY":
            order.delivery_status = "NOT_READY"

    if (
        order.delivery_status == "DISPATCHED"
        and previous_delivery != "DISPATCHED"
        and not order.dispatched_at
    ):
        order.dispatched_at = now

    if (
        order.delivery_status == "DELIVERED"
        and previous_delivery != "DELIVERED"
        and not order.delivered_at
    ):
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
        allowed_product_ids = [
            x.product_id
            for x in db.query(AgentProduct)
            .filter(AgentProduct.agent_id == user.id)
            .all()
        ]

        if not allowed_product_ids:
            return []

        q = q.filter(
            Order.assigned_agent_id == user.id,
            Order.product_id.in_(allowed_product_ids),
        )
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
    allowed_product_ids = [
        x.product_id
        for x in db.query(AgentProduct)
        .filter(AgentProduct.agent_id == user.id)
        .all()
    ]

    if not allowed_product_ids:
        return []

    q = db.query(Order).filter(
        Order.assigned_agent_id == user.id,
        Order.product_id.in_(allowed_product_ids),
    )

    bucket = bucket.upper()

    if bucket == "FOLLOW_UP":
        q = q.filter(
            Order.call_status.in_([
                "NO_ANSWER",
                "VOICEMAIL",
                "BUSY",
                "CALLBACK",
            ])
        )

    elif bucket in {"READY", "READY_TO_SEND"}:
        q = q.filter(
            Order.call_status == "CONFIRMED",
            Order.delivery_status == "READY",
        )

    elif bucket in {"CLOSED", "DRAFT"}:
        q = q.filter(
            Order.call_status.in_([
                "CANCELLED",
                "WRONG_NUMBER",
                "DUPLICATE",
                "NOT_INTERESTED",
            ])
        )

    elif bucket == "CONFIRMED":
        q = q.filter(
            Order.call_status == "CONFIRMED"
        )

    elif bucket != "ALL":
        q = q.filter(
            Order.call_status == bucket
        )
    return [order_to_dict(db, x) for x in q.order_by(Order.created_at.asc()).limit(min(limit, 200)).all()]





# ============================================================
# AGENT BOARD — TAWAZONE-STYLE OPERATIONAL API
# ============================================================

AGENT_FOLLOW_UP_STATUSES = {
    "NO_ANSWER",
    "VOICEMAIL",
    "BUSY",
    "CALLBACK",
}

AGENT_CLOSED_STATUSES = {
    "CANCELLED",
    "WRONG_NUMBER",
    "DUPLICATE",
    "NOT_INTERESTED",
}

AGENT_ALLOWED_OUTCOMES = {
    "CONFIRMED",
    "NO_ANSWER",
    "VOICEMAIL",
    "BUSY",
    "CALLBACK",
    "CANCELLED",
    "WRONG_NUMBER",
    "DUPLICATE",
    "NOT_INTERESTED",
}

AGENT_LOCKED_DELIVERY_STATUSES = {
    "DISPATCHED",
    "IN_TRANSIT",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
}


def _agent_allowed_product_ids(
    db: Session,
    agent_id: str,
) -> list[str]:
    return [
        x.product_id
        for x in (
            db.query(AgentProduct)
            .filter(
                AgentProduct.agent_id == agent_id
            )
            .all()
        )
    ]


def _apply_agent_bucket(query, bucket: str):
    bucket = (bucket or "NEW").upper()

    if bucket == "NEW":
        return query.filter(
            Order.call_status == "NEW"
        )

    if bucket == "FOLLOW_UP":
        return query.filter(
            Order.call_status.in_(
                list(AGENT_FOLLOW_UP_STATUSES)
            )
        )

    if bucket in {"READY", "READY_TO_SEND"}:
        return query.filter(
            Order.call_status == "CONFIRMED",
            Order.delivery_status == "READY",
        )

    if bucket == "BLACKLIST":
        return query.filter(
            Order.call_status == "BLACKLIST"
        )

    if bucket in {"CLOSED", "DRAFT"}:
        return query.filter(
            Order.call_status.in_(
                list(AGENT_CLOSED_STATUSES)
            )
        )

    if bucket == "SENT":
        return query.filter(
            Order.delivery_status.in_([
                "DISPATCHED",
                "IN_TRANSIT",
                "OUT_FOR_DELIVERY",
                "DELIVERED",
            ])
        )

    if bucket == "ALL":
        return query

    raise HTTPException(
        400,
        "Invalid agent board bucket",
    )


def _agent_board_order(
    db: Session,
    order: Order,
) -> dict:
    data = order_to_dict(db, order)

    active_offers = (
        db.query(ProductOffer)
        .filter(
            ProductOffer.product_id == order.product_id,
            ProductOffer.is_active.is_(True),
        )
        .order_by(
            ProductOffer.quantity.asc(),
            ProductOffer.created_at.asc(),
        )
        .all()
    )

    attempts = (
        db.query(CallAttempt)
        .filter(
            CallAttempt.order_id == order.id
        )
        .order_by(
            CallAttempt.created_at.desc()
        )
        .all()
    )

    data["attempt_count"] = len(attempts)

    data["last_attempt"] = (
        {
            "outcome": attempts[0].outcome,
            "note": attempts[0].note,
            "created_at": attempts[0].created_at,
        }
        if attempts
        else None
    )

    data["available_offers"] = [
        {
            "id": offer.id,
            "name": offer.name,
            "quantity": offer.quantity,
            "price": offer.price,
        }
        for offer in active_offers
    ]

    data["editable"] = (
        order.delivery_status
        not in AGENT_LOCKED_DELIVERY_STATUSES
        and not data.get("delivery_tracking")
    )

    return data


@router.get("/agent-board")
def agent_board(
    bucket: str = "NEW",
    product_id: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("AGENT")),
):
    """
    One API for the entire Agent Workspace.

    Returns:
    - current bucket orders
    - dynamic product filters
    - queue counts
    - active Product Offers
    - call attempt count
    """

    allowed_product_ids = _agent_allowed_product_ids(
        db,
        user.id,
    )

    if not allowed_product_ids:
        return {
            "counts": {
                "new": 0,
                "follow_up": 0,
                "ready": 0,
                "blacklist": 0,
                "closed": 0,
                "sent": 0,
                "all": 0,
            },
            "products": [],
            "orders": [],
        }

    base = db.query(Order).filter(
        Order.assigned_agent_id == user.id,
        Order.product_id.in_(
            allowed_product_ids
        ),
    )

    def count_bucket(name: str) -> int:
        return _apply_agent_bucket(
            base,
            name,
        ).count()

    counts = {
        "new": count_bucket("NEW"),
        "follow_up": count_bucket("FOLLOW_UP"),
        "ready": count_bucket("READY"),
        "blacklist": count_bucket("BLACKLIST"),
        "closed": count_bucket("CLOSED"),
        "sent": count_bucket("SENT"),
        "all": base.count(),
    }

    q = _apply_agent_bucket(
        base,
        bucket,
    )

    # Product counters follow the selected tab/bucket.
    product_count_rows = q.all()

    product_counts: dict[str, int] = {}

    for row in product_count_rows:
        product_counts[row.product_id] = (
            product_counts.get(
                row.product_id,
                0,
            )
            + 1
        )

    products = (
        db.query(Product)
        .filter(
            Product.id.in_(
                allowed_product_ids
            ),
            Product.status == "ACTIVE",
        )
        .order_by(Product.name.asc())
        .all()
    )

    product_filters = [
        {
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "image_url": product.image_url,
            "currency": product.currency,
            "count": product_counts.get(
                product.id,
                0,
            ),
        }
        for product in products
    ]

    if product_id:
        if product_id not in allowed_product_ids:
            raise HTTPException(
                403,
                "You do not have access to this product",
            )

        q = q.filter(
            Order.product_id == product_id
        )

    if search:
        term = search.strip()

        if term:
            customer_ids = [
                customer.id
                for customer in (
                    db.query(Customer)
                    .filter(
                        or_(
                            Customer.name.ilike(
                                f"%{term}%"
                            ),
                            Customer.phone_e164.ilike(
                                f"%{term}%"
                            ),
                            Customer.phone_raw.ilike(
                                f"%{term}%"
                            ),
                        )
                    )
                    .all()
                )
            ]

            q = q.filter(
                or_(
                    Order.order_number.ilike(
                        f"%{term}%"
                    ),
                    Order.city.ilike(
                        f"%{term}%"
                    ),
                    Order.address.ilike(
                        f"%{term}%"
                    ),
                    Order.customer_id.in_(
                        customer_ids
                    ),
                )
            )

    rows = (
        q.order_by(
            Order.created_at.asc()
        )
        .offset(max(offset, 0))
        .limit(
            min(
                max(limit, 1),
                200,
            )
        )
        .all()
    )

    return {
        "bucket": bucket.upper(),
        "counts": counts,
        "products": product_filters,
        "orders": [
            _agent_board_order(
                db,
                row,
            )
            for row in rows
        ],
    }


@router.post("/agent-workflow/{order_id}")
def agent_workflow(
    order_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("AGENT")),
):
    """
    Atomic Agent Workspace save / call-result action.

    Product Offers are the only source of truth for
    offer quantity and total price.
    """

    allowed_fields = {
        "customer_name",
        "phone",
        "city",
        "address",
        "offer_id",
        "call_note",
        "outcome",
    }

    unknown = (
        set(payload.keys())
        - allowed_fields
    )

    if unknown:
        raise HTTPException(
            400,
            "Unsupported fields: "
            + ", ".join(
                sorted(unknown)
            ),
        )

    row = (
        db.query(Order)
        .filter(
            Order.id == order_id
        )
        .first()
    )

    if not row:
        raise HTTPException(
            404,
            "Order not found",
        )

    assert_order_access(
        row,
        user,
    )

    allowed_product = (
        db.query(AgentProduct)
        .filter(
            AgentProduct.agent_id == user.id,
            AgentProduct.product_id
            == row.product_id,
        )
        .first()
    )

    if not allowed_product:
        raise HTTPException(
            403,
            "You no longer have access to this product",
        )

    shipment = (
        db.query(DeliveryShipment)
        .filter(
            DeliveryShipment.order_id
            == row.id
        )
        .order_by(
            DeliveryShipment.created_at.desc()
        )
        .first()
    )

    if (
        row.delivery_status
        in AGENT_LOCKED_DELIVERY_STATUSES
        or (
            shipment
            and shipment.tracking_number
        )
    ):
        raise HTTPException(
            409,
            "This order was already sent to delivery and is locked for agent editing",
        )

    customer = (
        db.query(Customer)
        .filter(
            Customer.id == row.customer_id
        )
        .first()
    )

    store = (
        db.query(Store)
        .filter(
            Store.id == row.store_id
        )
        .first()
    )

    product = (
        db.query(Product)
        .filter(
            Product.id == row.product_id
        )
        .first()
    )

    if not customer or not store or not product:
        raise HTTPException(
            400,
            "Order customer/store/product data is incomplete",
        )

    previous_call = row.call_status
    previous_delivery = (
        row.delivery_status
    )

    # ----------------------------------------------
    # Customer name
    # ----------------------------------------------

    if "customer_name" in payload:
        name = str(
            payload.get(
                "customer_name"
            )
            or ""
        ).strip()

        if not name:
            raise HTTPException(
                400,
                "Customer name is required",
            )

        customer.name = name

    # ----------------------------------------------
    # Phone
    # ----------------------------------------------

    if "phone" in payload:
        raw_phone = str(
            payload.get("phone")
            or ""
        ).strip()

        if not raw_phone:
            raise HTTPException(
                400,
                "Phone number is required",
            )

        normalized = normalize_phone(
            raw_phone,
            store.country,
        )

        duplicate_customer = (
            db.query(Customer)
            .filter(
                Customer.phone_e164
                == normalized,
                Customer.id
                != customer.id,
            )
            .first()
        )

        if duplicate_customer:
            raise HTTPException(
                409,
                "Another customer already uses this phone number",
            )

        customer.phone_raw = raw_phone
        customer.phone_e164 = normalized

    # ----------------------------------------------
    # Digylog City
    # ----------------------------------------------

    if "city" in payload:
        city_input = str(
            payload.get("city")
            or ""
        ).strip()

        if city_input:
            city = canonical_digylog_city(
                city_input
            )

            if not city:
                raise HTTPException(
                    400,
                    "Select a valid Digylog city",
                )

            row.city = city
            customer.city = city

        else:
            row.city = None
            customer.city = None

    # ----------------------------------------------
    # Address
    # ----------------------------------------------

    if "address" in payload:
        address = str(
            payload.get("address")
            or ""
        ).strip()

        row.address = (
            address or None
        )
        customer.address = (
            address or None
        )

    # ----------------------------------------------
    # Note
    # ----------------------------------------------

    if "call_note" in payload:
        note = str(
            payload.get("call_note")
            or ""
        ).strip()

        row.call_note = (
            note or None
        )

    # ----------------------------------------------
    # Product Offer
    # ----------------------------------------------

    if "offer_id" in payload:
        offer_id = (
            str(
                payload.get(
                    "offer_id"
                )
                or ""
            ).strip()
        )

        if not offer_id:
            row.offer_id = None

        else:
            offer = (
                db.query(ProductOffer)
                .filter(
                    ProductOffer.id
                    == offer_id,
                    ProductOffer.product_id
                    == row.product_id,
                    ProductOffer.is_active.is_(
                        True
                    ),
                )
                .first()
            )

            if not offer:
                raise HTTPException(
                    400,
                    "Invalid or inactive offer for this product",
                )

            row.offer_id = offer.id
            row.quantity = offer.quantity

            # Offer price is the full bundle/order total.
            row.total_price = offer.price

            row.unit_price = (
                offer.price
                / offer.quantity
            )

    # ----------------------------------------------
    # Call outcome
    # ----------------------------------------------

    outcome_raw = payload.get(
        "outcome"
    )

    outcome = (
        str(outcome_raw)
        .strip()
        .upper()
        if outcome_raw
        else None
    )

    if outcome:
        if outcome not in AGENT_ALLOWED_OUTCOMES:
            raise HTTPException(
                400,
                "Invalid agent call outcome",
            )

        # Confirmation requires complete validated data.
        if outcome == "CONFIRMED":
            selected_offer = (
                db.query(ProductOffer)
                .filter(
                    ProductOffer.id
                    == row.offer_id,
                    ProductOffer.product_id
                    == row.product_id,
                    ProductOffer.is_active.is_(
                        True
                    ),
                )
                .first()
                if row.offer_id
                else None
            )

            if not selected_offer:
                raise HTTPException(
                    400,
                    "Select an active product offer before confirmation",
                )

            if not customer.name.strip():
                raise HTTPException(
                    400,
                    "Customer name is required before confirmation",
                )

            if not customer.phone_e164:
                raise HTTPException(
                    400,
                    "Customer phone is required before confirmation",
                )

            if not row.city:
                raise HTTPException(
                    400,
                    "Select the Digylog city before confirmation",
                )

            if not (
                row.address
                and row.address.strip()
            ):
                raise HTTPException(
                    400,
                    "Customer address is required before confirmation",
                )

            # Re-apply current offer from DB.
            # Browser never decides qty or price.
            row.quantity = (
                selected_offer.quantity
            )
            row.total_price = (
                selected_offer.price
            )
            row.unit_price = (
                selected_offer.price
                / selected_offer.quantity
            )

            row.call_status = "CONFIRMED"
            row.delivery_status = "READY"

        elif outcome in AGENT_FOLLOW_UP_STATUSES:
            row.call_status = outcome
            row.delivery_status = "NOT_READY"

        elif outcome in AGENT_CLOSED_STATUSES:
            row.call_status = outcome
            row.delivery_status = "NOT_READY"

        attempt = CallAttempt(
            order_id=row.id,
            agent_id=user.id,
            channel="PHONE",
            outcome=outcome,
            note=row.call_note,
            started_at=utcnow(),
            ended_at=utcnow(),
            duration_seconds=None,
        )

        db.add(attempt)

        if not row.first_call_at:
            row.first_call_at = (
                attempt.started_at
            )

    apply_status_side_effects(
        row,
        previous_call=previous_call,
        previous_delivery=previous_delivery,
    )

    if (
        row.call_status
        != previous_call
        or row.delivery_status
        != previous_delivery
    ):
        db.add(
            OrderStatusHistory(
                order_id=row.id,
                from_call_status=previous_call,
                to_call_status=row.call_status,
                from_delivery_status=previous_delivery,
                to_delivery_status=row.delivery_status,
                changed_by_user_id=user.id,
                reason=row.call_note,
            )
        )

    reconcile_confirmation_payout(
        db,
        row,
    )

    log_action(
        db,
        user_id=user.id,
        action="AGENT_ORDER_WORKFLOW",
        entity_type="ORDER",
        entity_id=row.id,
        before={
            "call_status": previous_call,
            "delivery_status": previous_delivery,
        },
        after={
            "call_status": row.call_status,
            "delivery_status": row.delivery_status,
            "offer_id": row.offer_id,
            "quantity": row.quantity,
            "total_price": str(
                row.total_price
            ),
            "city": row.city,
        },
    )

    db.commit()
    db.refresh(row)

    return _agent_board_order(
        db,
        row,
    )


@lru_cache(maxsize=1)
def load_digylog_cities():
    city_file = Path(__file__).resolve().parents[2] / "data" / "digylog_cities.json"

    with city_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return [
        str(city).strip()
        for city in data
        if str(city).strip()
    ]


def canonical_digylog_city(value):
    value = (value or "").strip()

    if not value:
        return None

    cities = load_digylog_cities()
    city_map = {city.casefold(): city for city in cities}

    return city_map.get(value.casefold())


@router.get("/cities")
def list_digylog_cities(
    user: User = Depends(
        require_roles("OWNER", "ADMIN", "SUPERVISOR", "AGENT")
    ),
):
    return {"cities": load_digylog_cities()}


@router.get("/manual-meta")
def agent_manual_order_meta(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("AGENT")),
):
    links = db.query(AgentProduct).filter(
        AgentProduct.agent_id == user.id
    ).all()

    product_ids = [x.product_id for x in links]

    if not product_ids:
        return {"products": []}

    products = db.query(Product).filter(
        Product.id.in_(product_ids),
        Product.status == "ACTIVE",
    ).all()

    result = []

    for product in products:
        offers = db.query(ProductOffer).filter(
            ProductOffer.product_id == product.id,
            ProductOffer.is_active.is_(True),
        ).all()

        result.append({
            "id": product.id,
            "store_id": product.store_id,
            "name": product.name,
            "sku": product.sku,
            "selling_price": product.selling_price,
            "currency": product.currency,
            "default_qty": product.default_qty,
            "offers": [
                {
                    "id": offer.id,
                    "name": offer.name,
                    "quantity": offer.quantity,
                    "price": offer.price,
                }
                for offer in offers
            ],
        })

    return {"products": result}


@router.post("/manual", response_model=OrderOut)
def create_manual_order(
    payload: ManualOrderCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR", "AGENT")),
):
    store = db.query(Store).filter(Store.id == payload.store_id).first()
    product = db.query(Product).filter(Product.id == payload.product_id, Product.store_id == payload.store_id).first()
    if not store or not product:
        raise HTTPException(400, "Invalid store/product combination")

    city = canonical_digylog_city(payload.city)

    if not city:
        raise HTTPException(
            400,
            "Select a valid Digylog city"
        )

    assigned_agent_id = payload.assigned_agent_id

    if user.role == "AGENT":
        allowed_product = db.query(AgentProduct).filter(
            AgentProduct.agent_id == user.id,
            AgentProduct.product_id == product.id,
        ).first()

        if not allowed_product:
            raise HTTPException(403, "You are not enabled for this product")

        assigned_agent_id = user.id
    offer = db.query(ProductOffer).filter(ProductOffer.id == payload.offer_id, ProductOffer.product_id == product.id, ProductOffer.is_active.is_(True)).first() if payload.offer_id else None
    if payload.offer_id and not offer:
        raise HTTPException(400, "Invalid product offer")

    phone = normalize_phone(payload.phone, store.country)
    customer = db.query(Customer).filter(Customer.phone_e164 == phone).first()
    if not customer:
        customer = Customer(name=payload.customer_name.strip(), phone_raw=payload.phone, phone_e164=phone, city=city, address=payload.address)
        db.add(customer)
        db.flush()
    else:
        customer.name = payload.customer_name.strip() or customer.name
        customer.city = city
        customer.address = payload.address or customer.address

    qty = offer.quantity if offer else payload.quantity
    if user.role == "AGENT":
        unit_price = Decimal(offer.price) / offer.quantity if offer else Decimal(product.selling_price)
        total = Decimal(offer.price) if offer else unit_price * qty
    else:
        unit_price = Decimal(payload.unit_price) if payload.unit_price is not None else (Decimal(offer.price) / offer.quantity if offer else Decimal(product.selling_price))
        total = Decimal(payload.total_price) if payload.total_price is not None else (Decimal(offer.price) if offer else unit_price * qty)
    if assigned_agent_id:
        agent = db.query(User).filter(User.id == assigned_agent_id, User.role == "AGENT", User.is_active.is_(True)).first()
        if not agent:
            raise HTTPException(400, "Invalid agent")
        allowed = db.query(AgentProduct).filter(AgentProduct.agent_id == agent.id, AgentProduct.product_id == product.id).first()
        if not allowed:
            raise HTTPException(400, "Agent is not enabled for this product")

    call_status = "NEW" if user.role == "AGENT" else payload.call_status.upper()
    if call_status not in CALL_STATUSES:
        raise HTTPException(400, "Invalid call status")
    row = Order(
        order_number=new_order_number(),
        store_id=store.id,
        product_id=product.id,
        offer_id=offer.id if offer else None,
        customer_id=customer.id,
        assigned_agent_id=assigned_agent_id,
        quantity=qty,
        unit_price=unit_price,
        total_price=total,
        currency=product.currency or store.currency,
        source=payload.source.upper(),
        call_status=call_status,
        call_note=payload.call_note,
        city=city,
        address=payload.address,
        assigned_at=utcnow() if assigned_agent_id else None,
    )
    db.add(row)
    db.flush()
    if assigned_agent_id:
        db.add(OrderAssignment(order_id=row.id, agent_id=assigned_agent_id, assigned_by_user_id=user.id, assignment_type="MANUAL"))
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

    customer_name_set = "customer_name" in updates
    phone_set = "phone" in updates

    customer_name = updates.pop("customer_name", None)
    phone_raw = updates.pop("phone", None)

    # ----------------------------------------------
    # Agent permissions
    # ----------------------------------------------
    if user.role == "AGENT":
        if (
            "assigned_agent_id" in updates
            and updates["assigned_agent_id"] != user.id
        ):
            raise HTTPException(
                403,
                "Agents cannot reassign orders"
            )

        if "delivery_status" in updates:
            raise HTTPException(
                403,
                "Agents cannot change delivery status"
            )

        locked_delivery_statuses = {
            "DISPATCHED",
            "IN_TRANSIT",
            "OUT_FOR_DELIVERY",
            "DELIVERED",
        }

        if (
            row.delivery_status in locked_delivery_statuses
            or row.delivery_tracking
        ):
            raise HTTPException(
                409,
                "Order was already sent to delivery and can no longer be edited by an agent"
            )

    # ----------------------------------------------
    # Validate statuses
    # ----------------------------------------------
    if "call_status" in updates and updates["call_status"]:
        updates["call_status"] = updates["call_status"].upper()

        if updates["call_status"] not in CALL_STATUSES:
            raise HTTPException(
                400,
                "Invalid call status"
            )

    if "delivery_status" in updates and updates["delivery_status"]:
        updates["delivery_status"] = updates["delivery_status"].upper()

        if updates["delivery_status"] not in DELIVERY_STATUSES:
            raise HTTPException(
                400,
                "Invalid delivery status"
            )

    # ----------------------------------------------
    # Customer + store
    # ----------------------------------------------
    customer = db.query(Customer).filter(
        Customer.id == row.customer_id
    ).first()

    store = db.query(Store).filter(
        Store.id == row.store_id
    ).first()

    if not customer:
        raise HTTPException(
            400,
            "Customer record not found"
        )

    if not store:
        raise HTTPException(
            400,
            "Store record not found"
        )

    before = {
        "call_status": row.call_status,
        "delivery_status": row.delivery_status,
        "assigned_agent_id": row.assigned_agent_id,
        "customer_name": customer.name,
        "customer_phone": customer.phone_e164,
        "quantity": row.quantity,
        "unit_price": str(row.unit_price),
        "total_price": str(row.total_price),
        "city": row.city,
        "address": row.address,
        "call_note": row.call_note,
    }

    # ----------------------------------------------
    # Customer name
    # ----------------------------------------------
    if customer_name_set:
        name = (customer_name or "").strip()

        if not name:
            raise HTTPException(
                400,
                "Customer name is required"
            )

        customer.name = name

    # ----------------------------------------------
    # Customer phone
    # ----------------------------------------------
    if phone_set:
        raw_phone = (phone_raw or "").strip()

        if not raw_phone:
            raise HTTPException(
                400,
                "Phone number is required"
            )

        normalized = normalize_phone(
            raw_phone,
            store.country
        )

        duplicate = db.query(Customer).filter(
            Customer.phone_e164 == normalized,
            Customer.id != customer.id,
        ).first()

        if duplicate:
            raise HTTPException(
                400,
                "This phone number already belongs to another customer"
            )

        customer.phone_raw = raw_phone
        customer.phone_e164 = normalized

    # ----------------------------------------------
    # Digylog City validation
    # ----------------------------------------------
    if "city" in updates:
        city = canonical_digylog_city(
            updates.get("city")
        )

        if not city:
            raise HTTPException(
                400,
                "Select a valid Digylog city"
            )

        updates["city"] = city
        customer.city = city

    # ----------------------------------------------
    # Address sync
    # ----------------------------------------------
    if "address" in updates:
        customer.address = updates.get("address")

    # ----------------------------------------------
    # Price / quantity validation
    # ----------------------------------------------
    if "quantity" in updates:
        if updates["quantity"] is None or updates["quantity"] < 1:
            raise HTTPException(
                400,
                "Quantity must be at least 1"
            )

    if "unit_price" in updates:
        if updates["unit_price"] is None or updates["unit_price"] < 0:
            raise HTTPException(
                400,
                "Invalid unit price"
            )

    if "total_price" in updates:
        if updates["total_price"] is None or updates["total_price"] < 0:
            raise HTTPException(
                400,
                "Invalid total price"
            )

    # Automatically recalculate total when qty/unit price changes
    # unless total_price was manually supplied.
    if (
        ("quantity" in updates or "unit_price" in updates)
        and "total_price" not in updates
    ):
        final_qty = updates.get(
            "quantity",
            row.quantity
        )

        final_unit = updates.get(
            "unit_price",
            row.unit_price
        )

        updates["total_price"] = (
            Decimal(final_unit) * final_qty
        )

    # ----------------------------------------------
    # Assignment security
    # ----------------------------------------------
    if (
        user.role == "AGENT"
        and "assigned_agent_id" in updates
    ):
        updates.pop("assigned_agent_id", None)

    # ----------------------------------------------
    # Remember previous statuses / agent
    # ----------------------------------------------
    previous_call = row.call_status
    previous_delivery = row.delivery_status
    previous_agent = row.assigned_agent_id

    # ----------------------------------------------
    # Apply order fields
    # ----------------------------------------------
    for key, value in updates.items():
        setattr(row, key, value)

    # ----------------------------------------------
    # Assignment history
    # ----------------------------------------------
    if row.assigned_agent_id != previous_agent:
        row.assigned_at = (
            utcnow()
            if row.assigned_agent_id
            else None
        )

        if previous_agent:
            active_assignment = (
                db.query(OrderAssignment)
                .filter(
                    OrderAssignment.order_id == row.id,
                    OrderAssignment.agent_id == previous_agent,
                    OrderAssignment.released_at.is_(None),
                )
                .order_by(
                    OrderAssignment.assigned_at.desc()
                )
                .first()
            )

            if active_assignment:
                active_assignment.released_at = utcnow()

        if row.assigned_agent_id:
            db.add(
                OrderAssignment(
                    order_id=row.id,
                    agent_id=row.assigned_agent_id,
                    assigned_by_user_id=user.id,
                    assignment_type="REASSIGNED",
                )
            )

    # ----------------------------------------------
    # Existing status side effects
    # ----------------------------------------------
    apply_status_side_effects(
        row,
        previous_call,
        previous_delivery
    )

    if (
        row.call_status != previous_call
        or row.delivery_status != previous_delivery
    ):
        db.add(
            OrderStatusHistory(
                order_id=row.id,
                from_call_status=previous_call,
                to_call_status=row.call_status,
                from_delivery_status=previous_delivery,
                to_delivery_status=row.delivery_status,
                changed_by_user_id=user.id,
            )
        )

    # Keep commission / payout correct
    reconcile_confirmation_payout(
        db,
        row
    )

    after = {
        "call_status": row.call_status,
        "delivery_status": row.delivery_status,
        "assigned_agent_id": row.assigned_agent_id,
        "customer_name": customer.name,
        "customer_phone": customer.phone_e164,
        "quantity": row.quantity,
        "unit_price": str(row.unit_price),
        "total_price": str(row.total_price),
        "city": row.city,
        "address": row.address,
        "call_note": row.call_note,
    }

    log_action(
        db,
        user_id=user.id,
        action="ORDER_UPDATED",
        entity_type="ORDER",
        entity_id=row.id,
        before=before,
        after=after,
    )

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
    previous_delivery = row.delivery_status

    row.call_status = outcome
    row.call_note = payload.note or row.call_note

    if not row.first_call_at:
        row.first_call_at = started

    apply_status_side_effects(
        row,
        previous_call=previous,
        previous_delivery=previous_delivery,
    )

    db.add(
        OrderStatusHistory(
            order_id=row.id,
            from_call_status=previous,
            to_call_status=outcome,
            from_delivery_status=previous_delivery,
            to_delivery_status=row.delivery_status,
            changed_by_user_id=user.id,
            reason=payload.note,
        )
    )
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
