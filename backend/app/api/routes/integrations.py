from __future__ import annotations

import secrets as pysecrets
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import current_user, require_roles
from app.core.time import utcnow
from app.models import DeliveryShipment, IntegrationConfig, IntegrationEvent, Order, Store, User
from app.schemas import IntegrationCreate, IntegrationOut, IntegrationUpdate, SheetWebhookBatch
from app.services.audit import log_action
from app.services.digylog import DigylogError, apply_webhook, dispatch_order, test_connection
from app.services.google_sheets import apps_script, import_sheet_order
from app.services.integration_crypto import decrypt_secret_dict, encrypt_secret_dict

router = APIRouter(prefix="/integrations", tags=["integrations"])
SUPPORTED_PROVIDERS = {"DIGYLOG", "GOOGLE_SHEETS"}


def _provider(value: str) -> str:
    provider = (value or "").strip().upper()
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(400, f"Unsupported provider. Use one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}")
    return provider


def _secret_values(row: IntegrationConfig) -> dict:
    try:
        return decrypt_secret_dict(row.secrets_encrypted)
    except Exception as exc:
        raise HTTPException(500, "Integration secrets cannot be decrypted. APP_SECRET may have changed.") from exc


def _public_webhook(row: IntegrationConfig) -> str:
    base = settings.public_api_base_url.rstrip("/")
    if row.provider == "DIGYLOG":
        return f"{base}/api/v1/integrations/digylog/{row.id}/webhook"
    if row.provider == "GOOGLE_SHEETS":
        return f"{base}/api/v1/integrations/google-sheets/{row.id}/webhook"
    return ""


def _out(row: IntegrationConfig) -> dict:
    secret_values = _secret_values(row)
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    data["secret_keys"] = sorted(secret_values.keys())
    data["webhook_url"] = _public_webhook(row)
    data.pop("secrets_encrypted", None)
    data.pop("created_by_user_id", None)
    return data


def _verify_webhook_token(row: IntegrationConfig, supplied: str | None) -> None:
    expected = str(_secret_values(row).get("webhook_token") or "")
    if not expected or not supplied or not pysecrets.compare_digest(expected, supplied):
        raise HTTPException(401, "Invalid webhook token")


def _integration_or_404(db: Session, integration_id: str, provider: str | None = None) -> IntegrationConfig:
    row = db.query(IntegrationConfig).filter(IntegrationConfig.id == integration_id).first()
    if not row:
        raise HTTPException(404, "Integration not found")
    if provider and row.provider != provider:
        raise HTTPException(400, f"Integration is not {provider}")
    return row


@router.get("", response_model=list[IntegrationOut])
def list_integrations(
    provider: str | None = None,
    store_id: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    q = db.query(IntegrationConfig)
    if provider:
        q = q.filter(IntegrationConfig.provider == _provider(provider))
    if store_id:
        q = q.filter(IntegrationConfig.store_id == store_id)
    return [_out(x) for x in q.order_by(IntegrationConfig.created_at.desc()).all()]


@router.post("", response_model=IntegrationOut)
def create_integration(
    payload: IntegrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    provider = _provider(payload.provider)
    if payload.store_id and not db.query(Store).filter(Store.id == payload.store_id).first():
        raise HTTPException(400, "Invalid store")
    if provider == "GOOGLE_SHEETS" and not payload.store_id:
        raise HTTPException(400, "Google Sheets integration requires a store")

    secret_values = {k: v for k, v in (payload.secrets or {}).items() if v not in (None, "")}
    secret_values.setdefault("webhook_token", pysecrets.token_urlsafe(32))
    if provider == "DIGYLOG" and not secret_values.get("api_token"):
        raise HTTPException(400, "Digylog API token is required")

    config = dict(payload.config or {})
    if provider == "DIGYLOG":
        config.setdefault("api_base_url", "https://api.digylog.com/api/v2/seller")
        config.setdefault("orders_url", "https://api.digylog.com/api/v2/seller/orders")
        config.setdefault("auth_header", "Authorization")
        config.setdefault("auth_prefix", "Bearer ")
        config.setdefault("referer", "https://apiseller.digylog.com")
        config.setdefault("network", 1)
        config.setdefault("port", 1)
        config.setdefault("add_status", 1)
        config.setdefault("check_duplicate", True)
    else:
        config.setdefault("sheet_name", "Sheet1")
        config.setdefault("auto_assign", True)

    row = IntegrationConfig(
        store_id=payload.store_id,
        provider=provider,
        name=payload.name.strip(),
        is_active=payload.is_active,
        config=config,
        secrets_encrypted=encrypt_secret_dict(secret_values),
        created_by_user_id=user.id,
    )
    db.add(row)
    db.flush()
    log_action(db, user_id=user.id, action="INTEGRATION_CREATED", entity_type="INTEGRATION", entity_id=row.id, after={"provider": provider, "name": row.name, "store_id": row.store_id})
    db.commit()
    db.refresh(row)
    return _out(row)


@router.patch("/{integration_id}", response_model=IntegrationOut)
def update_integration(
    integration_id: str,
    payload: IntegrationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    row = _integration_or_404(db, integration_id)
    updates = payload.model_dump(exclude_unset=True)
    before = {"name": row.name, "store_id": row.store_id, "is_active": row.is_active, "config": row.config}
    if "store_id" in updates:
        store_id = updates.pop("store_id")
        if store_id and not db.query(Store).filter(Store.id == store_id).first():
            raise HTTPException(400, "Invalid store")
        if row.provider == "GOOGLE_SHEETS" and not store_id:
            raise HTTPException(400, "Google Sheets integration requires a store")
        row.store_id = store_id
    if "name" in updates and updates["name"] is not None:
        row.name = str(updates.pop("name")).strip()
    if "is_active" in updates and updates["is_active"] is not None:
        row.is_active = bool(updates.pop("is_active"))
    if "config" in updates and updates["config"] is not None:
        merged = dict(row.config or {})
        merged.update(updates.pop("config"))
        row.config = merged
    if "secrets" in updates and updates["secrets"] is not None:
        current = _secret_values(row)
        for key, value in updates.pop("secrets").items():
            if value not in (None, ""):
                current[key] = value
        row.secrets_encrypted = encrypt_secret_dict(current)
    log_action(db, user_id=user.id, action="INTEGRATION_UPDATED", entity_type="INTEGRATION", entity_id=row.id, before=before, after={"name": row.name, "store_id": row.store_id, "is_active": row.is_active, "config": row.config})
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/{integration_id}/webhook-config")
def webhook_config(
    integration_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    row = _integration_or_404(db, integration_id)
    values = _secret_values(row)
    token = str(values.get("webhook_token") or "")
    if not token:
        raise HTTPException(500, "Webhook token is missing")
    return {"webhook_url": f"{_public_webhook(row)}?token={token}", "provider": row.provider}


@router.post("/{integration_id}/rotate-webhook-token")
def rotate_webhook_token(
    integration_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN")),
):
    row = _integration_or_404(db, integration_id)
    values = _secret_values(row)
    values["webhook_token"] = pysecrets.token_urlsafe(32)
    row.secrets_encrypted = encrypt_secret_dict(values)
    log_action(db, user_id=user.id, action="INTEGRATION_WEBHOOK_ROTATED", entity_type="INTEGRATION", entity_id=row.id)
    db.commit()
    return {"ok": True, "message": "Webhook token rotated. Generate/copy the new webhook configuration before using it."}


@router.post("/{integration_id}/test")
def test_integration(
    integration_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    row = _integration_or_404(db, integration_id)
    if row.provider == "DIGYLOG":
        result = test_connection(row)
    else:
        result = {"ok": True, "message": "Google Sheets webhook is ready. Generate the Apps Script and run sendNewLeadsToCallCenter once to test the full connection."}
    row.last_test_status = "SUCCESS" if result.get("ok") else "FAILED"
    row.last_test_message = str(result.get("message") or "")[:2000]
    row.last_test_at = utcnow()
    db.add(IntegrationEvent(integration_id=row.id, provider=row.provider, direction="OUTBOUND", event_type="CONNECTION_TEST", status=row.last_test_status, payload={"message": row.last_test_message}, error=None if result.get("ok") else row.last_test_message))
    log_action(db, user_id=user.id, action="INTEGRATION_TESTED", entity_type="INTEGRATION", entity_id=row.id, after={"status": row.last_test_status})
    db.commit()
    return result


@router.get("/events")
def list_events(
    integration_id: str | None = None,
    provider: str | None = None,
    limit: int = Query(default=50, ge=1, le=300),
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    q = db.query(IntegrationEvent)
    if integration_id:
        q = q.filter(IntegrationEvent.integration_id == integration_id)
    if provider:
        q = q.filter(IntegrationEvent.provider == _provider(provider))
    rows = q.order_by(IntegrationEvent.created_at.desc()).limit(limit).all()
    return [{c.name: getattr(x, c.name) for c in x.__table__.columns} for x in rows]


@router.get("/google-sheets/{integration_id}/script")
def google_sheets_script(
    integration_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("OWNER", "ADMIN", "SUPERVISOR")),
):
    row = _integration_or_404(db, integration_id, "GOOGLE_SHEETS")
    values = _secret_values(row)
    token = str(values.get("webhook_token") or "")
    if not token:
        raise HTTPException(500, "Google Sheets webhook token is missing")
    url = f"{_public_webhook(row)}?token={token}"
    return {"script": apps_script(row, token), "webhook_url": url, "sheet_name": (row.config or {}).get("sheet_name", "Sheet1")}


@router.post("/google-sheets/{integration_id}/webhook")
def google_sheets_webhook(
    integration_id: str,
    payload: SheetWebhookBatch,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    row = _integration_or_404(db, integration_id, "GOOGLE_SHEETS")
    if not row.is_active:
        raise HTTPException(409, "Integration is disabled")
    _verify_webhook_token(row, token)
    results = []
    for item in payload.orders:
        try:
            with db.begin_nested():
                result = import_sheet_order(db, row, item.model_dump())
                if result.get("status") == "ERROR":
                    db.add(IntegrationEvent(
                        integration_id=row.id, provider="GOOGLE_SHEETS", direction="INBOUND",
                        event_type="ORDER_IMPORT", status="FAILED",
                        payload={"row_number": item.row_number, "sku": item.sku},
                        error=str(result.get("error") or "Import rejected"),
                    ))
            results.append(result)
        except Exception as exc:
            results.append({"status": "ERROR", "error": str(exc), "row_number": item.row_number})
            db.add(IntegrationEvent(integration_id=row.id, provider="GOOGLE_SHEETS", direction="INBOUND", event_type="ORDER_IMPORT", status="FAILED", payload={"row_number": item.row_number, "sku": item.sku}, error=str(exc)))
    db.commit()
    return {"ok": True, "results": results}


@router.api_route("/digylog/{integration_id}/webhook", methods=["POST", "PUT"])
async def digylog_webhook(
    integration_id: str,
    request: Request,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    row = _integration_or_404(db, integration_id, "DIGYLOG")
    if not row.is_active:
        raise HTTPException(409, "Integration is disabled")
    supplied = token or request.headers.get("X-Webhook-Token") or request.headers.get("X-Digylog-Token")
    _verify_webhook_token(row, supplied)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Webhook body must be JSON") from exc

    # Digylog webhook verification handshake.
    # Digylog sends a key and expects the same key in the response.
    verification_key = None
    if isinstance(body, dict):
        verification_key = body.get("key")

    # Also support verification key sent as a query parameter.
    if verification_key is None:
        verification_key = request.query_params.get("key")

    if verification_key is not None:
        return {"key": verification_key}

    # Temporary Digylog payload-shape diagnostic.
    # Logs field names only — no customer values.
    if isinstance(body, dict):
        print("DIGYLOG_WEBHOOK_KEYS:", sorted(body.keys()))
        for key, value in body.items():
            if isinstance(value, dict):
                print(
                    f"DIGYLOG_WEBHOOK_NESTED_KEYS[{key}]:",
                    sorted(value.keys())
                )

    result = apply_webhook(db, row, body)
    db.commit()
    return result



def _is_digylog_blacklist_error(message: str) -> bool:
    text = (message or "").casefold()

    blacklist_markers = (
        "blacklist",
        "blacklisted",
        "black list",
        "liste noire",
        "القائمة السوداء",
        "لائحة سوداء",
    )

    return any(marker in text for marker in blacklist_markers)


def _raise_digylog_dispatch_error(
    db: Session,
    order: Order,
    user: User,
    exc: Exception,
):
    message = str(exc)

    if _is_digylog_blacklist_error(message):
        previous_call_status = order.call_status

        order.call_status = "BLACKLIST"

        # A blacklisted order is no longer an accepted confirmation
        # until the agent corrects it and Digylog accepts it.
        from app.services.payouts import reconcile_confirmation_payout
        reconcile_confirmation_payout(db, order)

        log_action(
            db,
            user_id=user.id,
            action="ORDER_DIGYLOG_BLACKLISTED",
            entity_type="ORDER",
            entity_id=order.id,
            before={
                "call_status": previous_call_status,
            },
            after={
                "call_status": "BLACKLIST",
                "digylog_error": message[:500],
            },
        )

        # Also preserves FAILED Digylog shipment/event
        db.commit()

        raise HTTPException(
            409,
            f"DIGYLOG_BLACKLIST: {message}"
        ) from exc

    # Normal Digylog errors are NOT blacklist
    db.commit()

    raise HTTPException(
        502,
        message
    ) from exc


@router.post("/digylog/{integration_id}/dispatch/{order_id}")
def dispatch_to_digylog(
    integration_id: str,
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {"OWNER", "ADMIN", "SUPERVISOR", "AGENT"}:
        raise HTTPException(403, "Insufficient permissions")
    row = _integration_or_404(db, integration_id, "DIGYLOG")
    if not row.is_active:
        raise HTTPException(409, "Digylog integration is disabled")
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    if user.role == "AGENT" and order.assigned_agent_id != user.id:
        raise HTTPException(403, "This order is not assigned to you")
    if row.store_id and row.store_id != order.store_id:
        raise HTTPException(400, "This Digylog integration is linked to a different store")
    try:
        shipment = dispatch_order(db, row, order)

        if order.call_status == "BLACKLIST":
            order.call_status = "CONFIRMED"

            from app.services.payouts import reconcile_confirmation_payout
            reconcile_confirmation_payout(db, order)
        log_action(db, user_id=user.id, action="ORDER_DISPATCHED_DIGYLOG", entity_type="ORDER", entity_id=order.id, after={"integration_id": row.id, "tracking": shipment.tracking_number})
        db.commit()
        db.refresh(shipment)
        return {"ok": True, "shipment_id": shipment.id, "tracking_number": shipment.tracking_number, "delivery_status": order.delivery_status}
    except DigylogError as exc:
        _raise_digylog_dispatch_error(
            db,
            order,
            user,
            exc,
        )


@router.post("/digylog/dispatch/{order_id}")
def dispatch_to_default_digylog(
    order_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    if user.role not in {"OWNER", "ADMIN", "SUPERVISOR", "AGENT"}:
        raise HTTPException(403, "Insufficient permissions")
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Order not found")
    if user.role == "AGENT" and order.assigned_agent_id != user.id:
        raise HTTPException(403, "This order is not assigned to you")
    row = (
        db.query(IntegrationConfig)
        .filter(IntegrationConfig.provider == "DIGYLOG", IntegrationConfig.is_active.is_(True), IntegrationConfig.store_id == order.store_id)
        .order_by(IntegrationConfig.created_at.asc())
        .first()
    )
    if not row:
        raise HTTPException(409, "No active Digylog integration is configured for this store")
    try:
        shipment = dispatch_order(db, row, order)

        if order.call_status == "BLACKLIST":
            order.call_status = "CONFIRMED"

            from app.services.payouts import reconcile_confirmation_payout
            reconcile_confirmation_payout(db, order)
        log_action(db, user_id=user.id, action="ORDER_DISPATCHED_DIGYLOG", entity_type="ORDER", entity_id=order.id, after={"integration_id": row.id, "tracking": shipment.tracking_number})
        db.commit()
        db.refresh(shipment)
        return {"ok": True, "integration_id": row.id, "shipment_id": shipment.id, "tracking_number": shipment.tracking_number, "delivery_status": order.delivery_status}
    except DigylogError as exc:
        _raise_digylog_dispatch_error(
            db,
            order,
            user,
            exc,
        )
