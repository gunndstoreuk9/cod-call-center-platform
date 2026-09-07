from collections import defaultdict
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import require_roles
from app.core.time import date_bounds, utcnow
from app.models import (
    AdSpend,
    DeliveryShipment,
    IntegrationConfig,
    Order,
    PayoutEntry,
    Product,
    ProductCostHistory,
    Store,
    User,
)
from app.services.audit import log_action


router = APIRouter(
    prefix="/profit",
    tags=["profit"]
)


ZERO = Decimal("0")


class AdSpendCreate(BaseModel):
    store_id: str
    product_id: str
    spend_date: date
    amount: Decimal = Field(gt=0)
    platform: str = "META"
    campaign_name: str | None = None
    note: str | None = None


class AdSpendUpdate(BaseModel):
    spend_date: date | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    platform: str | None = None
    campaign_name: str | None = None
    note: str | None = None


def pct(
    num: Decimal | int,
    den: Decimal | int
) -> float:
    if not den:
        return 0.0

    return round(
        float(num) / float(den) * 100,
        2
    )


def ratio(
    num: Decimal | int,
    den: Decimal | int
) -> float:
    if not den:
        return 0.0

    return round(
        float(num) / float(den),
        2
    )


def money(value) -> Decimal:
    if value is None:
        return ZERO

    return Decimal(str(value))


def validate_scope(
    db: Session,
    store_id: str | None,
    product_id: str | None,
):
    store = None
    product = None

    if store_id:
        store = (
            db.query(Store)
            .filter(Store.id == store_id)
            .first()
        )

        if not store:
            raise HTTPException(
                400,
                "Invalid store"
            )

    if product_id:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .first()
        )

        if not product:
            raise HTTPException(
                400,
                "Invalid product"
            )

        if (
            store_id
            and product.store_id != store_id
        ):
            raise HTTPException(
                400,
                "Product does not belong to selected store"
            )

    return store, product


def scoped_products(
    db: Session,
    store_id: str | None,
    product_id: str | None,
):
    q = db.query(Product)

    if store_id:
        q = q.filter(
            Product.store_id == store_id
        )

    if product_id:
        q = q.filter(
            Product.id == product_id
        )

    return q.order_by(
        Product.name.asc()
    ).all()


def cost_maps(
    db: Session,
    products: list[Product],
):
    product_map = {
        p.id: p
        for p in products
    }

    histories = defaultdict(list)

    if product_map:
        rows = (
            db.query(ProductCostHistory)
            .filter(
                ProductCostHistory.product_id.in_(
                    list(product_map.keys())
                )
            )
            .order_by(
                ProductCostHistory.product_id.asc(),
                ProductCostHistory.effective_from.desc(),
            )
            .all()
        )

        for row in rows:
            histories[row.product_id].append(row)

    return product_map, histories


def cost_at(
    product: Product,
    history_rows: list[ProductCostHistory],
    when,
):
    for row in history_rows:
        if row.effective_from <= when:
            return (
                money(row.unit_cost),
                money(row.packaging_cost),
            )

    # Fallback for products that existed before
    # cost history was introduced.
    return (
        money(product.unit_cost),
        money(product.packaging_cost),
    )


def filtered_delivered_orders(
    db: Session,
    start,
    end,
    store_id: str | None,
    product_id: str | None,
):
    q = db.query(Order).filter(
        Order.delivery_status == "DELIVERED",
        Order.delivered_at.is_not(None),
        Order.delivered_at >= start,
        Order.delivered_at < end,
    )

    if store_id:
        q = q.filter(
            Order.store_id == store_id
        )

    if product_id:
        q = q.filter(
            Order.product_id == product_id
        )

    return q.order_by(
        Order.delivered_at.asc()
    ).all()


def confirmation_count(
    db: Session,
    start,
    end,
    store_id: str | None,
    product_id: str | None,
):
    q = db.query(Order).filter(
        Order.confirmed_at.is_not(None),
        Order.confirmed_at >= start,
        Order.confirmed_at < end,
    )

    if store_id:
        q = q.filter(
            Order.store_id == store_id
        )

    if product_id:
        q = q.filter(
            Order.product_id == product_id
        )

    return q.count()


def created_count(
    db: Session,
    start,
    end,
    store_id: str | None,
    product_id: str | None,
):
    q = db.query(Order).filter(
        Order.created_at >= start,
        Order.created_at < end,
    )

    if store_id:
        q = q.filter(
            Order.store_id == store_id
        )

    if product_id:
        q = q.filter(
            Order.product_id == product_id
        )

    return q.count()


def local_date_bounds(start, end):
    tz = ZoneInfo(settings.timezone)

    return (
        start.astimezone(tz).date(),
        end.astimezone(tz).date(),
    )


def spend_rows(
    db: Session,
    start,
    end,
    store_id: str | None,
    product_id: str | None,
):
    start_day, end_day = local_date_bounds(
        start,
        end
    )

    q = db.query(AdSpend).filter(
        AdSpend.spend_date >= start_day,
        AdSpend.spend_date < end_day,
    )

    if store_id:
        q = q.filter(
            AdSpend.store_id == store_id
        )

    if product_id:
        q = q.filter(
            AdSpend.product_id == product_id
        )

    return q.all()


def confirmation_costs_by_product(
    db: Session,
    start,
    end,
    product_ids: list[str],
):
    result = defaultdict(lambda: ZERO)

    if not product_ids:
        return result

    rows = (
        db.query(PayoutEntry)
        .filter(
            PayoutEntry.entry_type == "CONFIRMATION",
            PayoutEntry.product_id.in_(product_ids),
            PayoutEntry.created_at >= start,
            PayoutEntry.created_at < end,
        )
        .all()
    )

    for row in rows:
        if row.product_id:
            result[row.product_id] += money(
                row.amount
            )

    return result


def seller_delivery_costs(
    db: Session,
    order_ids: list[str],
):
    result = defaultdict(lambda: ZERO)

    if not order_ids:
        return result

    shipments = (
        db.query(DeliveryShipment)
        .filter(
            DeliveryShipment.order_id.in_(
                order_ids
            )
        )
        .order_by(
            DeliveryShipment.created_at.desc()
        )
        .all()
    )

    # Latest shipment per order only.
    latest = {}

    for shipment in shipments:
        if shipment.order_id not in latest:
            latest[shipment.order_id] = shipment

    integration_ids = {
        x.integration_id
        for x in latest.values()
        if x.integration_id
    }

    integrations = {}

    if integration_ids:
        integrations = {
            x.id: x
            for x in (
                db.query(IntegrationConfig)
                .filter(
                    IntegrationConfig.id.in_(
                        integration_ids
                    )
                )
                .all()
            )
        }

    for order_id, shipment in latest.items():
        integration = integrations.get(
            shipment.integration_id
        )

        port = None

        if integration:
            config = integration.config or {}

            try:
                port = int(
                    config.get("port", 2)
                )
            except (TypeError, ValueError):
                port = 2

        # Digylog mapping used by CODOPS:
        # 1 = Shipper / seller pays
        # 2 = Consignee / customer pays
        if port == 1:
            result[order_id] = money(
                shipment.delivery_fee
            )

    return result


def refused_returned_counts(
    db: Session,
    start,
    end,
    store_id: str | None,
    product_id: str | None,
):
    base = (
        db.query(DeliveryShipment)
        .join(
            Order,
            Order.id == DeliveryShipment.order_id
        )
    )

    if store_id:
        base = base.filter(
            Order.store_id == store_id
        )

    if product_id:
        base = base.filter(
            Order.product_id == product_id
        )

    refused = (
        base.filter(
            DeliveryShipment.refused_at.is_not(None),
            DeliveryShipment.refused_at >= start,
            DeliveryShipment.refused_at < end,
        )
        .count()
    )

    returned = (
        base.filter(
            DeliveryShipment.returned_at.is_not(None),
            DeliveryShipment.returned_at >= start,
            DeliveryShipment.returned_at < end,
        )
        .count()
    )

    return refused, returned


def build_profit_data(
    db: Session,
    start,
    end,
    store_id: str | None,
    product_id: str | None,
):
    products = scoped_products(
        db,
        store_id,
        product_id
    )

    product_map, histories = cost_maps(
        db,
        products
    )

    delivered_orders = filtered_delivered_orders(
        db,
        start,
        end,
        store_id,
        product_id
    )

    order_ids = [
        o.id
        for o in delivered_orders
    ]

    agent_by_product = confirmation_costs_by_product(
        db,
        start,
        end,
        list(product_map.keys())
    )

    delivery_by_order = seller_delivery_costs(
        db,
        order_ids
    )

    spends = spend_rows(
        db,
        start,
        end,
        store_id,
        product_id
    )

    ad_by_product = defaultdict(
        lambda: ZERO
    )

    for row in spends:
        ad_by_product[row.product_id] += money(
            row.amount
        )

    stats = defaultdict(
        lambda: {
            "delivered": 0,
            "units": 0,
            "revenue": ZERO,
            "product_cost": ZERO,
            "packaging_cost": ZERO,
            "agent_cost": ZERO,
            "delivery_cost": ZERO,
        }
    )

    for order in delivered_orders:
        product = product_map.get(
            order.product_id
        )

        if not product:
            continue

        unit_cost, packaging_cost = cost_at(
            product,
            histories.get(
                order.product_id,
                []
            ),
            order.delivered_at,
        )

        quantity = int(
            order.quantity or 0
        )

        row = stats[order.product_id]

        row["delivered"] += 1
        row["units"] += quantity
        row["revenue"] += money(
            order.total_price
        )

        row["product_cost"] += (
            unit_cost * quantity
        )

        row["packaging_cost"] += (
            packaging_cost
        )

        row["delivery_cost"] += (
            delivery_by_order[order.id]
        )

    for pid, amount in agent_by_product.items():
        if pid in product_map:
            stats[pid]["agent_cost"] += amount

    product_rows = []

    for product in products:
        row = stats[product.id]

        ad_spend = ad_by_product[
            product.id
        ]

        total_cost = (
            row["product_cost"]
            + row["packaging_cost"]
            + ad_spend
            + row["agent_cost"]
            + row["delivery_cost"]
        )

        net_profit = (
            row["revenue"]
            - total_cost
        )

        product_rows.append(
            {
                "product_id": product.id,
                "store_id": product.store_id,
                "name": product.name,
                "sku": product.sku,
                "image_url": product.image_url,
                "currency": product.currency,

                "delivered": row["delivered"],
                "units": row["units"],

                "revenue": str(
                    row["revenue"]
                ),

                "product_cost": str(
                    row["product_cost"]
                ),

                "packaging_cost": str(
                    row["packaging_cost"]
                ),

                "ad_spend": str(
                    ad_spend
                ),

                "agent_cost": str(
                    row["agent_cost"]
                ),

                "delivery_cost": str(
                    row["delivery_cost"]
                ),

                "total_cost": str(
                    total_cost
                ),

                "net_profit": str(
                    net_profit
                ),

                "roas": ratio(
                    row["revenue"],
                    ad_spend
                ),

                "margin": pct(
                    net_profit,
                    row["revenue"]
                ),

                "cost_per_delivered": (
                    round(
                        float(total_cost)
                        / row["delivered"],
                        2
                    )
                    if row["delivered"]
                    else 0.0
                ),
            }
        )

    return product_rows


def selected_currency(
    products: list[dict]
):
    currencies = {
        x["currency"]
        for x in products
    }

    if not currencies:
        return "MAD", None

    if len(currencies) == 1:
        return next(iter(currencies)), None

    return (
        "MIXED",
        "Multiple currencies are selected. Filter by store before using combined financial totals.",
    )


@router.get("/dashboard")
def profit_dashboard(
    range: str = "today",
    from_date: str | None = None,
    to_date: str | None = None,
    store_id: str | None = None,
    product_id: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR"
        )
    ),
):
    validate_scope(
        db,
        store_id,
        product_id
    )

    start, end = date_bounds(
        range,
        from_date,
        to_date
    )

    products = build_profit_data(
        db,
        start,
        end,
        store_id,
        product_id
    )

    currency, warning = selected_currency(
        products
    )

    delivered = sum(
        x["delivered"]
        for x in products
    )

    units = sum(
        x["units"]
        for x in products
    )

    revenue = sum(
        (
            money(x["revenue"])
            for x in products
        ),
        ZERO
    )

    product_cost = sum(
        (
            money(x["product_cost"])
            for x in products
        ),
        ZERO
    )

    packaging_cost = sum(
        (
            money(x["packaging_cost"])
            for x in products
        ),
        ZERO
    )

    ad_spend = sum(
        (
            money(x["ad_spend"])
            for x in products
        ),
        ZERO
    )

    agent_cost = sum(
        (
            money(x["agent_cost"])
            for x in products
        ),
        ZERO
    )

    delivery_cost = sum(
        (
            money(x["delivery_cost"])
            for x in products
        ),
        ZERO
    )

    total_cost = (
        product_cost
        + packaging_cost
        + ad_spend
        + agent_cost
        + delivery_cost
    )

    net_profit = (
        revenue
        - total_cost
    )

    confirmed = confirmation_count(
        db,
        start,
        end,
        store_id,
        product_id
    )

    leads = created_count(
        db,
        start,
        end,
        store_id,
        product_id
    )

    refused, returned = refused_returned_counts(
        db,
        start,
        end,
        store_id,
        product_id
    )

    return {
        "range": range,
        "start": start,
        "end": end,

        "store_id": store_id,
        "product_id": product_id,

        "currency": currency,
        "currency_warning": warning,

        "leads": leads,
        "confirmed": confirmed,
        "delivered": delivered,
        "units_delivered": units,
        "refused": refused,
        "returned": returned,

        "revenue": str(revenue),

        "product_cost": str(
            product_cost
        ),

        "packaging_cost": str(
            packaging_cost
        ),

        "ad_spend": str(
            ad_spend
        ),

        "agent_cost": str(
            agent_cost
        ),

        "delivery_cost": str(
            delivery_cost
        ),

        "total_cost": str(
            total_cost
        ),

        "net_profit": str(
            net_profit
        ),

        "roas": ratio(
            revenue,
            ad_spend
        ),

        "profit_margin": pct(
            net_profit,
            revenue
        ),

        "cpa_confirmed": (
            round(
                float(ad_spend)
                / confirmed,
                2
            )
            if confirmed
            else 0.0
        ),

        "cpa_delivered": (
            round(
                float(ad_spend)
                / delivered,
                2
            )
            if delivered
            else 0.0
        ),

        "average_order_value": (
            round(
                float(revenue)
                / delivered,
                2
            )
            if delivered
            else 0.0
        ),
    }


@router.get("/products")
def profit_products(
    range: str = "today",
    from_date: str | None = None,
    to_date: str | None = None,
    store_id: str | None = None,
    product_id: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR"
        )
    ),
):
    validate_scope(
        db,
        store_id,
        product_id
    )

    start, end = date_bounds(
        range,
        from_date,
        to_date
    )

    return build_profit_data(
        db,
        start,
        end,
        store_id,
        product_id
    )


@router.get("/ad-spend")
def list_ad_spend(
    range: str = "this_month",
    from_date: str | None = None,
    to_date: str | None = None,
    store_id: str | None = None,
    product_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    _=Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR"
        )
    ),
):
    validate_scope(
        db,
        store_id,
        product_id
    )

    start, end = date_bounds(
        range,
        from_date,
        to_date
    )

    q = db.query(AdSpend).filter(
        AdSpend.spend_date >= local_date_bounds(
            start,
            end
        )[0],
        AdSpend.spend_date < local_date_bounds(
            start,
            end
        )[1],
    )

    if store_id:
        q = q.filter(
            AdSpend.store_id == store_id
        )

    if product_id:
        q = q.filter(
            AdSpend.product_id == product_id
        )

    total = q.count()

    rows = (
        q.order_by(
            AdSpend.spend_date.desc(),
            AdSpend.created_at.desc(),
        )
        .offset(
            max(offset, 0)
        )
        .limit(
            min(max(limit, 1), 200)
        )
        .all()
    )

    products = {
        p.id: p
        for p in (
            db.query(Product)
            .filter(
                Product.id.in_(
                    [
                        row.product_id
                        for row in rows
                    ]
                )
            )
            .all()
        )
    } if rows else {}

    return {
        "total": total,

        "items": [
            {
                "id": row.id,
                "store_id": row.store_id,
                "product_id": row.product_id,

                "product_name": (
                    products[
                        row.product_id
                    ].name
                    if row.product_id in products
                    else None
                ),

                "spend_date": row.spend_date,
                "amount": str(row.amount),
                "currency": row.currency,
                "platform": row.platform,
                "campaign_name": row.campaign_name,
                "note": row.note,
                "created_at": row.created_at,
            }
            for row in rows
        ],
    }


@router.post("/ad-spend")
def create_ad_spend(
    payload: AdSpendCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN"
        )
    ),
):
    product = (
        db.query(Product)
        .filter(
            Product.id == payload.product_id
        )
        .first()
    )

    if not product:
        raise HTTPException(
            400,
            "Invalid product"
        )

    if product.store_id != payload.store_id:
        raise HTTPException(
            400,
            "Product does not belong to selected store"
        )

    platform = (
        payload.platform
        .strip()
        .upper()
    )

    if not platform:
        raise HTTPException(
            400,
            "Platform is required"
        )

    row = AdSpend(
        store_id=payload.store_id,
        product_id=payload.product_id,
        spend_date=payload.spend_date,
        amount=payload.amount,
        currency=product.currency,
        platform=platform,
        campaign_name=(
            payload.campaign_name.strip()
            if payload.campaign_name
            else None
        ),
        note=(
            payload.note.strip()
            if payload.note
            else None
        ),
        created_by_user_id=user.id,
        created_at=utcnow(),
    )

    db.add(row)
    db.flush()

    log_action(
        db,
        user_id=user.id,
        action="AD_SPEND_CREATED",
        entity_type="AD_SPEND",
        entity_id=row.id,
        after={
            "product_id": row.product_id,
            "date": str(row.spend_date),
            "amount": str(row.amount),
            "platform": row.platform,
        },
    )

    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "product_id": row.product_id,
        "spend_date": row.spend_date,
        "amount": str(row.amount),
        "currency": row.currency,
        "platform": row.platform,
    }


@router.patch("/ad-spend/{spend_id}")
def update_ad_spend(
    spend_id: str,
    payload: AdSpendUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN"
        )
    ),
):
    row = (
        db.query(AdSpend)
        .filter(
            AdSpend.id == spend_id
        )
        .first()
    )

    if not row:
        raise HTTPException(
            404,
            "Ad spend entry not found"
        )

    before = {
        "spend_date": str(row.spend_date),
        "amount": str(row.amount),
        "platform": row.platform,
        "campaign_name": row.campaign_name,
    }

    updates = payload.model_dump(
        exclude_unset=True
    )

    if "platform" in updates:
        platform = (
            str(
                updates["platform"]
                or ""
            )
            .strip()
            .upper()
        )

        if not platform:
            raise HTTPException(
                400,
                "Platform is required"
            )

        updates["platform"] = platform

    for key, value in updates.items():
        if key in {
            "campaign_name",
            "note",
        }:
            value = (
                value.strip()
                if value
                else None
            )

        setattr(
            row,
            key,
            value
        )

    log_action(
        db,
        user_id=user.id,
        action="AD_SPEND_UPDATED",
        entity_type="AD_SPEND",
        entity_id=row.id,
        before=before,
        after={
            "spend_date": str(row.spend_date),
            "amount": str(row.amount),
            "platform": row.platform,
            "campaign_name": row.campaign_name,
        },
    )

    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "spend_date": row.spend_date,
        "amount": str(row.amount),
        "platform": row.platform,
        "campaign_name": row.campaign_name,
        "note": row.note,
    }


@router.delete("/ad-spend/{spend_id}")
def delete_ad_spend(
    spend_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN"
        )
    ),
):
    row = (
        db.query(AdSpend)
        .filter(
            AdSpend.id == spend_id
        )
        .first()
    )

    if not row:
        raise HTTPException(
            404,
            "Ad spend entry not found"
        )

    before = {
        "product_id": row.product_id,
        "spend_date": str(row.spend_date),
        "amount": str(row.amount),
        "platform": row.platform,
    }

    db.delete(row)

    log_action(
        db,
        user_id=user.id,
        action="AD_SPEND_DELETED",
        entity_type="AD_SPEND",
        entity_id=spend_id,
        before=before,
    )

    db.commit()

    return {
        "ok": True,
        "deleted_id": spend_id,
    }
