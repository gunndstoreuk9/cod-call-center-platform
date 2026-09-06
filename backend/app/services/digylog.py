from __future__ import annotations

from decimal import Decimal
from typing import Any
import httpx
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import (
    Customer, DeliveryDestination, DeliveryEvent, DeliveryShipment, DeliveryStatusMapping,
    DeliverySyncRun, IntegrationConfig, IntegrationEvent, Order, OrderStatusHistory, Product
)
from app.services.integration_crypto import decrypt_secret_dict


class DigylogError(Exception):
    pass


# Based on Digylog Seller API status ids used by the previous production integration.
# Unknown statuses are recorded on the shipment without overwriting our internal delivery status.
DIGYLOG_DELIVERY_STATUS_MAP = {
    1: "DISPATCHED", 2: "IN_TRANSIT", 3: "IN_TRANSIT", 4: "ISSUE", 5: "IN_TRANSIT",
    6: "DELIVERED", 7: "CANCELLED", 8: "RETURNED", 9: "REFUSED", 10: "RETURNED",
    11: "RETURNED", 13: "CANCELLED", 14: "IN_TRANSIT", 15: "IN_TRANSIT", 16: "IN_TRANSIT",
    17: "IN_TRANSIT", 18: "IN_TRANSIT", 19: "IN_TRANSIT", 20: "NOT_READY", 21: "ISSUE",
    22: "ISSUE", 23: "IN_TRANSIT", 24: "CANCELLED", 25: "CANCELLED", 26: "READY",
    30: "RETURNED", 31: "IN_TRANSIT", 32: "RETURNED", 38: "CANCELLED", 39: "IN_TRANSIT",
    40: "RETURNED", 41: "RETURNED", 42: "RETURNED", 43: "ISSUE", 44: "IN_TRANSIT",
    45: "DELIVERED", 46: "CANCELLED", 47: "REFUSED", 49: "IN_TRANSIT", 50: "IN_TRANSIT",
    51: "RETURNED", 52: "CANCELLED", 53: "IN_TRANSIT", 54: "IN_TRANSIT", 55: "CANCELLED",
}


def resolve_internal_status(db: Session, status_id: int | None) -> str | None:
    if status_id is None:
        return None
    row = (db.query(DeliveryStatusMapping)
           .filter(DeliveryStatusMapping.provider == "DIGYLOG",
                   DeliveryStatusMapping.external_status_id == status_id,
                   DeliveryStatusMapping.is_active.is_(True))
           .first())
    return row.internal_status if row else DIGYLOG_DELIVERY_STATUS_MAP.get(status_id)


def seed_status_mappings(db: Session) -> int:
    finals = {6: ("DELIVERED", True), 45: ("DELIVERED", True), 7: ("CANCELLED", False),
              8: ("RETURNED", False), 9: ("REFUSED", False), 10: ("RETURNED", False),
              11: ("RETURNED", False), 13: ("CANCELLED", False), 24: ("CANCELLED", False),
              25: ("CANCELLED", False), 30: ("RETURNED", False), 32: ("RETURNED", False),
              38: ("CANCELLED", False), 40: ("RETURNED", False), 41: ("RETURNED", False),
              42: ("RETURNED", False), 46: ("CANCELLED", False), 47: ("REFUSED", False),
              51: ("RETURNED", False), 52: ("CANCELLED", False), 55: ("CANCELLED", False)}
    created = 0
    for external_id, internal in DIGYLOG_DELIVERY_STATUS_MAP.items():
        if db.query(DeliveryStatusMapping).filter(DeliveryStatusMapping.provider == "DIGYLOG", DeliveryStatusMapping.external_status_id == external_id).first():
            continue
        final_status, success = finals.get(external_id, (internal, False))
        db.add(DeliveryStatusMapping(provider="DIGYLOG", external_status_id=external_id,
                                     internal_status=internal, is_final=external_id in finals,
                                     is_success=bool(success)))
        created += 1
    db.flush()
    return created


def _settings(integration: IntegrationConfig) -> tuple[dict, dict]:
    config = dict(integration.config or {})
    secrets = decrypt_secret_dict(integration.secrets_encrypted)
    return config, secrets


def _headers(config: dict, secrets: dict) -> dict[str, str]:
    token = str(secrets.get("api_token") or "").strip()
    if not token:
        raise DigylogError("Digylog API token is missing")
    header = str(config.get("auth_header") or "Authorization")
    prefix = str(config.get("auth_prefix") if config.get("auth_prefix") is not None else "Bearer ")
    headers = {"Accept": "application/json", "Content-Type": "application/json", header: f"{prefix}{token}"}
    referer = str(config.get("referer") or "https://apiseller.digylog.com").strip()
    if referer:
        headers["Referer"] = referer
    return headers


def _local_phone(phone_e164: str) -> str:
    phone = (phone_e164 or "").replace("+", "").strip()
    if phone.startswith("212"):
        return "0" + phone[3:]
    return phone


def build_payload(db: Session, integration: IntegrationConfig, order: Order) -> dict:
    config, _ = _settings(integration)
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if not customer or not product:
        raise DigylogError("Order customer or product is missing")
    designation = product.delivery_product_ref or product.name or product.sku
    entry = {
        "num": order.order_number,
        "type": 1,
        "name": customer.name,
        "phone": _local_phone(customer.phone_e164),
        "address": order.address or customer.address or order.city or customer.city or "",
        "city": order.city or customer.city or "",
        "price": float(Decimal(order.total_price)),
        "openproduct": int(config.get("open_product", 1)),
        "port": int(config.get("port", 1)),
        "note": order.call_note or "",
        "refs": [{"designation": designation, "quantity": int(order.quantity)}],
    }
    payload = {
        "mode": int(config.get("mode", 1)),
        "network": int(config.get("network", 1)),
        "fc": int(config.get("fc", 0)),
        "status": int(config.get("add_status", 1)),
        "checkDuplicate": 1 if config.get("check_duplicate", True) else 0,
        "orders": [entry],
    }
    store = str(config.get("digylog_store") or "").strip()
    if store:
        payload["store"] = store
    return payload


def _search_tracking(node: Any, order_num: str) -> str | None:
    keys = ("tracking", "traking", "trackingNumber", "code", "barcode", "ref", "reference")
    if isinstance(node, dict):
        if str(node.get("num") or "") == order_num:
            for key in keys:
                if node.get(key):
                    return str(node[key])
        for key in keys:
            if node.get(key):
                return str(node[key])
        for value in node.values():
            found = _search_tracking(value, order_num)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _search_tracking(value, order_num)
            if found:
                return found
    return None


def _extract_errors(node: Any, order_num: str) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        if str(node.get("num") or "") == order_num and isinstance(node.get("errors"), list):
            found.extend(str(x) for x in node["errors"])
        for value in node.values():
            found.extend(_extract_errors(value, order_num))
    elif isinstance(node, list):
        for value in node:
            found.extend(_extract_errors(value, order_num))
    return found


def test_connection(integration: IntegrationConfig) -> dict:
    config, secrets = _settings(integration)
    base = str(config.get("api_base_url") or "https://api.digylog.com/api/v2/seller").rstrip("/")
    test_url = str(config.get("test_url") or f"{base}/stores")
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(test_url, headers=_headers(config, secrets))
        if response.status_code >= 400:
            return {"ok": False, "message": f"Digylog returned HTTP {response.status_code}: {response.text[:300]}"}
        try:
            data = response.json()
        except ValueError:
            data = response.text[:300]
        return {"ok": True, "message": "Digylog connection succeeded", "preview": data}
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def dispatch_order(db: Session, integration: IntegrationConfig, order: Order) -> DeliveryShipment:
    if order.call_status != "CONFIRMED":
        raise DigylogError("Order must be CONFIRMED before dispatch")
    existing = (
        db.query(DeliveryShipment)
        .filter(DeliveryShipment.order_id == order.id, DeliveryShipment.provider == "DIGYLOG", DeliveryShipment.status.notin_(["FAILED", "CANCELLED"]))
        .order_by(DeliveryShipment.created_at.desc())
        .first()
    )
    if existing:
        raise DigylogError(f"Order already has a Digylog shipment ({existing.tracking_number or existing.external_id or existing.id})")

    config, secrets = _settings(integration)
    api_url = str(config.get("orders_url") or "https://api.digylog.com/api/v2/seller/orders")
    payload = build_payload(db, integration, order)
    event = IntegrationEvent(integration_id=integration.id, provider="DIGYLOG", direction="OUTBOUND", event_type="CREATE_ORDER", status="PENDING", entity_type="ORDER", entity_id=order.id, payload=payload)
    db.add(event)
    db.flush()
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            response = client.post(api_url, json=payload, headers=_headers(config, secrets))
        if response.status_code >= 400:
            raise DigylogError(f"Digylog rejected order ({response.status_code}): {response.text[:400]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise DigylogError(f"Digylog returned non-JSON response: {response.text[:300]}") from exc
        tracking = _search_tracking(data, order.order_number)
        if not tracking:
            errors = _extract_errors(data, order.order_number)
            raise DigylogError(" | ".join(errors) if errors else "Digylog accepted the request but no tracking number was found")
        shipment = DeliveryShipment(
            order_id=order.id, integration_id=integration.id, provider="DIGYLOG",
            external_id=tracking, external_reference=order.order_number, tracking_number=tracking,
            status="DISPATCHED", cod_amount=order.total_price, destination_city=order.city,
            accepted_at=utcnow(), last_synced_at=utcnow(), last_attempt_at=utcnow(), payload=data
        )
        db.add(shipment)
        db.flush()
        db.add(DeliveryEvent(
            shipment_id=shipment.id, order_id=order.id, integration_id=integration.id, provider="DIGYLOG",
            event_type="CREATE_ORDER", external_order_number=order.order_number, tracking_number=tracking,
            internal_status="DISPATCHED", event_at=utcnow(), raw_payload={"request": payload, "response": data}
        ))
        previous = order.delivery_status
        order.delivery_status = "DISPATCHED"
        order.dispatched_at = order.dispatched_at or utcnow()
        db.add(OrderStatusHistory(order_id=order.id, from_call_status=order.call_status, to_call_status=order.call_status, from_delivery_status=previous, to_delivery_status=order.delivery_status, reason="Dispatched to Digylog"))
        event.status = "SUCCESS"
        event.payload = {"request": payload, "response": data}
        db.flush()
        return shipment
    except Exception as exc:
        event.status = "FAILED"
        event.error = str(exc)
        shipment = DeliveryShipment(order_id=order.id, integration_id=integration.id, provider="DIGYLOG", status="FAILED", cod_amount=order.total_price, destination_city=order.city, payload=payload, error=str(exc), retry_count=1, last_attempt_at=utcnow())
        db.add(shipment)
        db.flush()
        if isinstance(exc, DigylogError):
            raise
        raise DigylogError(str(exc)) from exc


def apply_webhook(db: Session, integration: IntegrationConfig, body: dict) -> dict:
    event_type = str((body or {}).get("type") or "unknown")
    integration_event = IntegrationEvent(integration_id=integration.id, provider="DIGYLOG", direction="INBOUND", event_type=event_type, status="SUCCESS", payload=body)
    db.add(integration_event)

    payload = body.get("payload") or {}
    num = str(payload.get("num") or "").strip()
    tracking = str(payload.get("traking") or payload.get("tracking") or "").strip()
    raw_status = payload.get("idStatus")
    try:
        status_id = int(raw_status) if raw_status is not None else None
    except (TypeError, ValueError):
        status_id = None

    order = db.query(Order).filter(Order.order_number == num).first() if num else None
    shipment = None
    if order:
        shipment = (db.query(DeliveryShipment)
                    .filter(DeliveryShipment.order_id == order.id, DeliveryShipment.provider == "DIGYLOG")
                    .order_by(DeliveryShipment.created_at.desc()).first())
    if order is None and tracking:
        shipment = (db.query(DeliveryShipment)
                    .filter(DeliveryShipment.tracking_number == tracking, DeliveryShipment.provider == "DIGYLOG").first())
        order = db.query(Order).filter(Order.id == shipment.order_id).first() if shipment else None

    mapped = resolve_internal_status(db, status_id)
    delivery_event = DeliveryEvent(
        shipment_id=shipment.id if shipment else None,
        order_id=order.id if order else None,
        integration_id=integration.id, provider="DIGYLOG", event_type=event_type,
        external_order_number=num or None, tracking_number=tracking or None,
        external_status_id=status_id, internal_status=mapped, event_at=utcnow(),
        matched=bool(order), processed=bool(order),
        processing_error=None if order else "No matching order", raw_payload=body
    )
    db.add(delivery_event)

    if event_type != "order-status-changed":
        db.flush()
        return {"ok": True, "ignored": event_type}

    if not order:
        integration_event.status = "IGNORED"
        integration_event.error = "No matching order"
        db.flush()
        return {"ok": True, "matched": False}

    if not shipment:
        shipment = DeliveryShipment(
            order_id=order.id, integration_id=integration.id, provider="DIGYLOG",
            tracking_number=tracking or None, external_id=tracking or None, external_reference=num or order.order_number,
            status="CREATED", cod_amount=order.total_price, destination_city=order.city, payload=body
        )
        db.add(shipment)
        db.flush()
        delivery_event.shipment_id = shipment.id
    if tracking:
        shipment.tracking_number = tracking
        shipment.external_id = shipment.external_id or tracking
    shipment.external_status_id = status_id
    shipment.status = mapped or f"DIGYLOG_{raw_status or 'UNKNOWN'}"
    shipment.payload = body
    shipment.last_synced_at = utcnow()
    shipment.last_attempt_at = utcnow()

    if mapped in {"DISPATCHED", "IN_TRANSIT"}:
        shipment.accepted_at = shipment.accepted_at or utcnow()
    if mapped == "ISSUE":
        shipment.first_attempt_at = shipment.first_attempt_at or utcnow()
    elif mapped == "DELIVERED":
        shipment.delivered_at = shipment.delivered_at or utcnow()
    elif mapped == "REFUSED":
        shipment.refused_at = shipment.refused_at or utcnow()
    elif mapped == "RETURNED":
        shipment.returned_at = shipment.returned_at or utcnow()

    if mapped and mapped != order.delivery_status:
        previous = order.delivery_status
        order.delivery_status = mapped
        if mapped == "DISPATCHED":
            order.dispatched_at = order.dispatched_at or utcnow()
        if mapped == "DELIVERED":
            order.delivered_at = order.delivered_at or utcnow()
        db.add(OrderStatusHistory(order_id=order.id, from_call_status=order.call_status, to_call_status=order.call_status,
                                  from_delivery_status=previous, to_delivery_status=mapped,
                                  reason=f"Digylog webhook status {raw_status}"))
    integration_event.entity_type = "ORDER"
    integration_event.entity_id = order.id
    db.flush()
    return {"ok": True, "matched": True, "order_id": order.id, "delivery_status": mapped,
            "external_status_id": status_id, "tracking": tracking or shipment.tracking_number}
