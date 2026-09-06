from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import current_user, require_roles
from app.models import Store, User
from app.schemas import StoreCreate, StoreOut, StoreUpdate
from app.services.audit import log_action

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreOut])
def list_stores(db: Session = Depends(get_db), _: User = Depends(current_user)):
    return db.query(Store).order_by(Store.name.asc()).all()


@router.post("", response_model=StoreOut)
def create_store(
    payload: StoreCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    if db.query(Store).filter(Store.code == payload.code.strip().upper()).first():
        raise HTTPException(409, "Store code already exists")
    row = Store(**payload.model_dump())
    row.code = row.code.strip().upper()
    db.add(row)
    db.flush()
    log_action(db, user_id=user.id, action="STORE_CREATED", entity_type="STORE", entity_id=row.id, after={"name": row.name, "code": row.code})
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{store_id}", response_model=StoreOut)
def update_store(
    store_id: str,
    payload: StoreUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    row = db.query(Store).filter(Store.id == store_id).first()
    if not row:
        raise HTTPException(404, "Store not found")
    before = {"name": row.name, "status": row.status}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    log_action(db, user_id=user.id, action="STORE_UPDATED", entity_type="STORE", entity_id=row.id, before=before, after={"name": row.name, "status": row.status})
    db.commit()
    db.refresh(row)
    return row
