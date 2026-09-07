from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import current_user, require_roles
from app.core.time import utcnow
from app.models import Order, Product, ProductCostHistory, ProductOffer, Store, User
from app.schemas import OfferCreate, OfferOut, ProductCreate, ProductOut, ProductUpdate
from app.services.audit import log_action

router = APIRouter(prefix="/products", tags=["products"])


def product_payload(db: Session, product: Product) -> dict:
    offers = db.query(ProductOffer).filter(ProductOffer.product_id == product.id).order_by(ProductOffer.quantity.asc()).all()
    data = {c.name: getattr(product, c.name) for c in product.__table__.columns}
    data["offers"] = offers
    return data


@router.get("", response_model=list[ProductOut])
def list_products(
    status: str | None = None,
    store_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    q = db.query(Product)
    if status:
        q = q.filter(Product.status == status.upper())
    if store_id:
        q = q.filter(Product.store_id == store_id)
    return [product_payload(db, p) for p in q.order_by(Product.created_at.desc()).all()]


@router.post("", response_model=ProductOut)
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    if not db.query(Store).filter(Store.id == payload.store_id).first():
        raise HTTPException(400, "Invalid store")
    sku = payload.sku.strip().upper()
    if db.query(Product).filter(Product.sku == sku).first():
        raise HTTPException(409, "SKU already exists")
    data = payload.model_dump(exclude={"offers"})
    data["sku"] = sku
    row = Product(**data)
    db.add(row)
    db.flush()

    # First product cost history
    db.add(
        ProductCostHistory(
            product_id=row.id,
            unit_cost=row.unit_cost,
            packaging_cost=row.packaging_cost,
            effective_from=row.created_at or utcnow(),
            created_by_user_id=user.id,
        )
    )
    for offer in payload.offers:
        db.add(ProductOffer(product_id=row.id, **offer.model_dump()))
    log_action(db, user_id=user.id, action="PRODUCT_CREATED", entity_type="PRODUCT", entity_id=row.id, after={"name": row.name, "sku": row.sku})
    db.commit()
    db.refresh(row)
    return product_payload(db, row)


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    row = db.query(Product).filter(Product.id == product_id).first()
    if not row:
        raise HTTPException(404, "Product not found")
    before = {"name": row.name, "sku": row.sku, "status": row.status, "price": str(row.selling_price)}
    previous_unit_cost = row.unit_cost
    previous_packaging_cost = row.packaging_cost

    updates = payload.model_dump(exclude_unset=True)
    if "sku" in updates and updates["sku"]:
        updates["sku"] = updates["sku"].strip().upper()
        exists = db.query(Product).filter(Product.sku == updates["sku"], Product.id != product_id).first()
        if exists:
            raise HTTPException(409, "SKU already exists")
    for key, value in updates.items():
        setattr(row, key, value)

    cost_changed = (
        row.unit_cost != previous_unit_cost
        or row.packaging_cost != previous_packaging_cost
    )

    if cost_changed:
        existing_history = (
            db.query(ProductCostHistory)
            .filter(
                ProductCostHistory.product_id == row.id
            )
            .first()
        )

        effective_from = (
            row.created_at
            if existing_history is None
            else utcnow()
        )

        db.add(
            ProductCostHistory(
                product_id=row.id,
                unit_cost=row.unit_cost,
                packaging_cost=row.packaging_cost,
                effective_from=effective_from,
                created_by_user_id=user.id,
            )
        )
    log_action(db, user_id=user.id, action="PRODUCT_UPDATED", entity_type="PRODUCT", entity_id=row.id, before=before, after={"name": row.name, "sku": row.sku, "status": row.status, "price": str(row.selling_price)})
    db.commit()
    db.refresh(row)
    return product_payload(db, row)


@router.get("/{product_id}/cost-history")
def product_cost_history(
    product_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles("OWNER", "ADMIN")
    ),
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            404,
            "Product not found"
        )

    rows = (
        db.query(ProductCostHistory)
        .filter(
            ProductCostHistory.product_id == product_id
        )
        .order_by(
            ProductCostHistory.effective_from.desc()
        )
        .all()
    )

    return [
        {
            "id": row.id,
            "product_id": row.product_id,
            "unit_cost": row.unit_cost,
            "packaging_cost": row.packaging_cost,
            "effective_from": row.effective_from,
            "created_by_user_id": row.created_by_user_id,
            "created_at": row.created_at,
        }
        for row in rows
    ]

@router.post("/{product_id}/offers", response_model=OfferOut)
def create_offer(
    product_id: str,
    payload: OfferCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    if not db.query(Product).filter(Product.id == product_id).first():
        raise HTTPException(404, "Product not found")
    row = ProductOffer(product_id=product_id, **payload.model_dump())
    db.add(row)
    db.flush()
    log_action(db, user_id=user.id, action="PRODUCT_OFFER_CREATED", entity_type="PRODUCT", entity_id=product_id, after={"offer": row.name, "quantity": row.quantity, "price": str(row.price)})
    db.commit()
    db.refresh(row)
    return row


def _offer_or_404(
    db: Session,
    product_id: str,
    offer_id: str,
) -> ProductOffer:
    row = (
        db.query(ProductOffer)
        .filter(
            ProductOffer.id == offer_id,
            ProductOffer.product_id == product_id,
        )
        .first()
    )

    if not row:
        raise HTTPException(404, "Offer not found")

    return row


@router.patch("/{product_id}/offers/{offer_id}", response_model=OfferOut)
def update_offer(
    product_id: str,
    offer_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    """
    Update one Product Offer.

    Product offers are the single source of truth
    for quantity and offer pricing used by Agent Workspace.
    """

    row = _offer_or_404(
        db,
        product_id,
        offer_id,
    )

    before = {
        "name": row.name,
        "quantity": row.quantity,
        "price": str(row.price),
        "commission_override": (
            str(row.commission_override)
            if row.commission_override is not None
            else None
        ),
        "is_active": row.is_active,
    }

    allowed = {
        "name",
        "quantity",
        "price",
        "commission_override",
        "is_active",
    }

    unknown = set(payload.keys()) - allowed

    if unknown:
        raise HTTPException(
            400,
            f"Unsupported offer fields: {', '.join(sorted(unknown))}",
        )

    if "name" in payload:
        name = str(payload["name"] or "").strip()

        if not name:
            raise HTTPException(
                400,
                "Offer name is required",
            )

        if len(name) > 120:
            raise HTTPException(
                400,
                "Offer name is too long",
            )

        row.name = name

    if "quantity" in payload:
        try:
            quantity = int(payload["quantity"])
        except (TypeError, ValueError):
            raise HTTPException(
                400,
                "Quantity must be a number",
            )

        if quantity < 1 or quantity > 1000:
            raise HTTPException(
                400,
                "Quantity must be between 1 and 1000",
            )

        row.quantity = quantity

    if "price" in payload:
        try:
            price = Decimal(str(payload["price"]))
        except (InvalidOperation, TypeError, ValueError):
            raise HTTPException(
                400,
                "Invalid offer price",
            )

        if price < 0:
            raise HTTPException(
                400,
                "Offer price cannot be negative",
            )

        row.price = price

    if "commission_override" in payload:
        value = payload["commission_override"]

        if value in (None, ""):
            row.commission_override = None
        else:
            try:
                commission = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError):
                raise HTTPException(
                    400,
                    "Invalid commission override",
                )

            if commission < 0:
                raise HTTPException(
                    400,
                    "Commission cannot be negative",
                )

            row.commission_override = commission

    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            raise HTTPException(
                400,
                "is_active must be true or false",
            )

        row.is_active = payload["is_active"]

    log_action(
        db,
        user_id=user.id,
        action="PRODUCT_OFFER_UPDATED",
        entity_type="PRODUCT",
        entity_id=product_id,
        before=before,
        after={
            "offer_id": row.id,
            "name": row.name,
            "quantity": row.quantity,
            "price": str(row.price),
            "commission_override": (
                str(row.commission_override)
                if row.commission_override is not None
                else None
            ),
            "is_active": row.is_active,
        },
    )

    db.commit()
    db.refresh(row)

    return row


@router.delete("/{product_id}/offers/{offer_id}")
def delete_offer(
    product_id: str,
    offer_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    """
    Delete an unused offer.

    Historical orders keep their offer relationship,
    so offers already used by an order cannot be deleted.
    Disable them instead.
    """

    row = _offer_or_404(
        db,
        product_id,
        offer_id,
    )

    used = (
        db.query(Order)
        .filter(Order.offer_id == row.id)
        .first()
    )

    if used:
        raise HTTPException(
            409,
            "This offer is already used by existing orders. Disable it instead.",
        )

    before = {
        "offer_id": row.id,
        "name": row.name,
        "quantity": row.quantity,
        "price": str(row.price),
    }

    db.delete(row)

    log_action(
        db,
        user_id=user.id,
        action="PRODUCT_OFFER_DELETED",
        entity_type="PRODUCT",
        entity_id=product_id,
        before=before,
    )

    db.commit()

    return {
        "ok": True,
        "deleted_id": offer_id,
    }

