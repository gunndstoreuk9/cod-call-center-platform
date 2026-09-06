from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import current_user, require_roles
from app.models import Product, ProductOffer, Store, User
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
    updates = payload.model_dump(exclude_unset=True)
    if "sku" in updates and updates["sku"]:
        updates["sku"] = updates["sku"].strip().upper()
        exists = db.query(Product).filter(Product.sku == updates["sku"], Product.id != product_id).first()
        if exists:
            raise HTTPException(409, "SKU already exists")
    for key, value in updates.items():
        setattr(row, key, value)
    log_action(db, user_id=user.id, action="PRODUCT_UPDATED", entity_type="PRODUCT", entity_id=row.id, before=before, after={"name": row.name, "sku": row.sku, "status": row.status, "price": str(row.selling_price)})
    db.commit()
    db.refresh(row)
    return product_payload(db, row)


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
