from __future__ import annotations

from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.models import (
    Customer,
    DeliveryDestination,
    DeliveryEvent,
    DeliveryShipment,
    IntegrationConfig,
    IntegrationEvent,
    Order,
    OrderStatusHistory,
    Product,
)
from app.services.integration_crypto import decrypt_secret_dict


class AmeexError(Exception):
    pass


AMEEX_STATUS_MAP = {
    "CREATED": "DISPATCHED",
    "IN_PROGRESS": "IN_TRANSIT",
    "NEW": "DISPATCHED",
    "PICKED_UP": "IN_TRANSIT",
    "PICKUP": "IN_TRANSIT",
    "IN_TRANSIT": "IN_TRANSIT",
    "IN_DELIVERY": "IN_TRANSIT",
    "OUT_FOR_DELIVERY": "OUT_FOR_DELIVERY",
    "DELIVERED": "DELIVERED",
    "LIVRE": "DELIVERED",
    "REFUSED": "REFUSED",
    "REFUSE": "REFUSED",
    "RETURNED": "RETURNED",
    "RETOURNE": "RETURNED",
    "CANCELLED": "CANCELLED",
    "CANCELED": "CANCELLED",
    "ANNULE": "CANCELLED",
    "ISSUE": "ISSUE",
    "PROBLEM": "ISSUE",
}


def _settings(integration: IntegrationConfig) -> tuple[dict, dict]:
    return dict(integration.config or {}), decrypt_secret_dict(integration.secrets_encrypted)


BASE_URL = "https://api.ameex.app/customer"


def _request(integration: IntegrationConfig, method: str, path: str, payload: dict | None = None):
    _, secrets = _settings(integration)
    if not secrets.get("client_id") or not secrets.get("api_key"):
        raise AmeexError("AMEEX Client ID and API Key are required")
    headers = {"Accept": "application/json", "C-Api-Id": str(secrets["client_id"]),
               "C-Api-Key": str(secrets["api_key"])}
    try:
        with httpx.Client(timeout=25, follow_redirects=False) as client:
            response = client.request(method, BASE_URL + path, headers=headers, data=payload)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and (data.get("success") is False or data.get("SUCCESS") is False):
            raise AmeexError("AMEEX rejected the request")
        return data
    except Exception as exc:
        raise AmeexError(_safe_error(exc, secrets)) from exc


def _collection(data, name):
    # Response envelopes are not specified; support lists and named/data envelopes.
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in (name, name.lower(), "data", "DATA"):
            if key in data:
                return _collection(data[key], name)
        if data and all(isinstance(v, dict) for v in data.values()):
            return list(data.values())
    raise AmeexError(f"Unrecognized AMEEX {name} response; provide a sandbox response sample")


def _safe_error(value: object, secrets: dict) -> str:
    message = str(value)
    for key in ("client_id", "api_key"):
        secret = str(secrets.get(key) or "")
        if secret:
            message = message.replace(secret, "[redacted]").replace(quote(secret, safe=""), "[redacted]")
    return message


def _local_phone(phone_e164: str) -> str:
    phone = (phone_e164 or "").replace("+", "").strip()
    return "0" + phone[3:] if phone.startswith("212") else phone


def sync_cities(db: Session, integration: IntegrationConfig) -> int:
    data = _request(integration, "GET", "/Delivery/Cities")
    values = _collection(data, "CITIES")
    count = 0
    for item in values:
        if not isinstance(item, dict):
            continue
        city_id = str(item.get("ID") or item.get("id") or "").strip()
        city_name = str(item.get("NAME") or item.get("name") or "").strip()
        if not city_id or not city_name:
            continue
        row = db.query(DeliveryDestination).filter(
            DeliveryDestination.integration_id == integration.id,
            DeliveryDestination.external_city_id == city_id,
        ).first()
        if not row:
            row = DeliveryDestination(
                integration_id=integration.id,
                provider="AMEEX",
                external_city_id=city_id,
                city_name=city_name,
            )
            db.add(row)
        row.provider = "AMEEX"
        row.city_name = city_name
        row.fee = item.get("DELIVERED-PRICE")
        row.raw_payload = item
        row.last_synced_at = utcnow()
        row.is_active = True
        count += 1
    db.flush()
    return count


def _city_id(db: Session, integration: IntegrationConfig, city: str | None) -> str:
    value = str(city or "").strip()
    if not value:
        raise AmeexError("Order city is required for AMEEX")
    row = db.query(DeliveryDestination).filter(
        DeliveryDestination.integration_id == integration.id,
        or_(func.lower(DeliveryDestination.city_name) == value.lower(),
                DeliveryDestination.external_city_id == value),
        DeliveryDestination.is_active.is_(True),
    ).first()
    if not row:
        sync_cities(db, integration)
        row = db.query(DeliveryDestination).filter(
            DeliveryDestination.integration_id == integration.id,
            or_(func.lower(DeliveryDestination.city_name) == value.lower(),
                DeliveryDestination.external_city_id == value),
            DeliveryDestination.is_active.is_(True),
        ).first()
    if not row:
        raise AmeexError(
            f"AMEEX city ID not found for '{value}'. Use the exact city name from the AMEEX cities list."
        )
    return row.external_city_id


def build_payload(db: Session, integration: IntegrationConfig, order: Order) -> dict:
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if not customer or not product:
        raise AmeexError("Order customer or product is missing")
    phone = _local_phone(customer.phone_e164)
    if len(phone) < 9 or not phone.isdigit():
        raise AmeexError("AMEEX requires a phone number with at least 9 digits")
    if not customer.name or Decimal(order.total_price) < 0:
        raise AmeexError("Receiver and non-negative COD are required")
    return {"type": "SIMPLE", "receiver": customer.name, "phone": phone,
            "city": _city_id(db, integration, order.city or customer.city),
            "cod": str(Decimal(order.total_price)),
            "address": order.address or customer.address or "",
            "product": f"{product.delivery_product_ref or product.name or product.sku} x{order.quantity}",
            "comment": order.call_note or "", "order_num": order.order_number}


def _find_value(node: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(node, dict):
        for key in keys:
            if node.get(key) not in (None, ""):
                return node[key]
        for value in node.values():
            found = _find_value(value, keys)
            if found not in (None, ""):
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_value(value, keys)
            if found not in (None, ""):
                return found
    return None


def test_connection(integration: IntegrationConfig) -> dict:
    try:
        _collection(_request(integration, "GET", "/Delivery/Cities"), "CITIES")
        return {"ok": True, "message": "AMEEX authenticated cities endpoint is reachable"}
    except AmeexError as exc:
        return {"ok": False, "message": str(exc)}


def get_statuses(integration):
    return _request(integration, "GET", "/Delivery/Parcels/Statuts")


def get_tracking(integration, code):
    return _request(integration, "GET", "/Delivery/Parcels/Tracking/ParcelCode/" + quote(code, safe=""))


def bulk_lookup(integration, codes, info=False):
    if not 1 <= len(codes) <= 100 or any(not c or "," in c for c in codes):
        raise AmeexError("Provide 1–100 parcel codes without commas")
    path = "/Delivery/Parcels/MassInfo" if info else "/Delivery/Parcels/MassTracking"
    return _request(integration, "POST", path, {"codes": ",".join(codes)})


def dispatch_order(db: Session, integration: IntegrationConfig, order: Order) -> DeliveryShipment:
    db.query(Order).filter(Order.id == order.id).populate_existing().with_for_update().one()
    if order.call_status != "CONFIRMED":
        raise AmeexError("Order must be CONFIRMED before dispatch")
    existing = (
        db.query(DeliveryShipment)
        .filter(
            DeliveryShipment.order_id == order.id,
            DeliveryShipment.provider == "AMEEX",
            DeliveryShipment.status.notin_(["FAILED", "CANCELLED"]),
        )
        .order_by(DeliveryShipment.created_at.desc())
        .first()
    )
    if existing:
        raise AmeexError(f"Order already has an AMEEX shipment ({existing.tracking_number or existing.id})")

    _, secrets = _settings(integration)
    payload = build_payload(db, integration, order)
    event = IntegrationEvent(
        integration_id=integration.id, provider="AMEEX", direction="OUTBOUND",
        event_type="CREATE_PARCEL", status="PENDING", entity_type="ORDER", entity_id=order.id,
        payload=payload,
    )
    db.add(event)
    db.flush()
    try:
        data = _request(integration, "POST", "/Delivery/Parcels/Action/Type/Add", payload)
        tracking = _find_value(data, ("PARCEL_CODE", "parcel_code", "ParcelCode", "CODE"))
        if not isinstance(tracking, (str, int)) or isinstance(tracking, bool) or not str(tracking).strip():
            raise AmeexError("AMEEX response has no parcel code; reconcile in AMEEX before retrying")
        tracking = str(tracking)
    except Exception as exc:
        safe_error = _safe_error(exc, secrets)
        event.status = "UNKNOWN"
        event.error = safe_error
        db.add(DeliveryShipment(
            order_id=order.id, integration_id=integration.id, provider="AMEEX",
            status="UNKNOWN", cod_amount=order.total_price, destination_city=order.city,
            payload=payload, error=safe_error, retry_count=1, last_attempt_at=utcnow(),
        ))
        db.flush()
        raise AmeexError(safe_error) from exc

    shipment = DeliveryShipment(
        order_id=order.id, integration_id=integration.id, provider="AMEEX",
        external_id=tracking, external_reference=order.order_number, tracking_number=tracking,
        status="DISPATCHED", cod_amount=order.total_price, destination_city=order.city,
        delivery_fee=_find_value(data, ("DELIVERED-PRICE", "delivered-price", "delivery_fee")),
        accepted_at=utcnow(), last_synced_at=utcnow(), last_attempt_at=utcnow(), payload=data,
    )
    db.add(shipment)
    db.flush()
    db.add(DeliveryEvent(
        shipment_id=shipment.id, order_id=order.id, integration_id=integration.id,
        provider="AMEEX", event_type="CREATE_PARCEL",
        external_order_number=order.order_number, tracking_number=tracking,
        internal_status="DISPATCHED", event_at=utcnow(), raw_payload={"request": payload, "response": data},
    ))
    previous = order.delivery_status
    order.delivery_status = "DISPATCHED"
    order.dispatched_at = order.dispatched_at or utcnow()
    db.add(OrderStatusHistory(
        order_id=order.id, from_call_status=order.call_status, to_call_status=order.call_status,
        from_delivery_status=previous, to_delivery_status="DISPATCHED", reason="Dispatched to AMEEX",
    ))
    event.status = "SUCCESS"
    event.payload = {"request": payload, "response": data}
    db.flush()
    return shipment


def apply_webhook(db: Session, integration: IntegrationConfig, body: dict) -> dict:
    _, secrets = _settings(integration)
    sandbox = str(body.get("SANDBOX") or "0") == "1"
    if sandbox != str(secrets.get("api_key") or "").startswith("test_"):
        raise AmeexError("Webhook sandbox environment does not match API key")
    tracking = str(body.get("CODE") or "").strip()
    raw_status = str(body.get("STATUT") or "").strip()
    if not tracking or not raw_status:
        raise AmeexError("Webhook CODE and STATUT are required")
    normalized = raw_status.upper()
    mapped = AMEEX_STATUS_MAP.get(normalized)
    shipment = db.query(DeliveryShipment).filter(
        DeliveryShipment.provider == "AMEEX",
        DeliveryShipment.integration_id == integration.id,
        DeliveryShipment.tracking_number == tracking,
    ).first()
    order = db.query(Order).filter(Order.id == shipment.order_id).populate_existing().with_for_update().first() if shipment else None
    if shipment:
        db.query(DeliveryShipment).filter(DeliveryShipment.id == shipment.id).populate_existing().with_for_update().one()
    reference = order.order_number if order else ""
    duplicate = db.query(DeliveryEvent).filter(
        DeliveryEvent.integration_id == integration.id,
        DeliveryEvent.tracking_number == tracking,
        DeliveryEvent.event_type == "PARCEL_STATUS",
    ).all()
    if any(event.raw_payload == body for event in duplicate):
        return {"ok": True, "matched": bool(order), "duplicate": True}

    db.add(IntegrationEvent(
        integration_id=integration.id, provider="AMEEX", direction="INBOUND",
        event_type="PARCEL_STATUS", status="SUCCESS" if order else "IGNORED",
        entity_type="ORDER" if order else None, entity_id=order.id if order else None,
        payload=body, error=None if order else "No matching order",
    ))
    delivery_event = DeliveryEvent(
        shipment_id=shipment.id if shipment else None, order_id=order.id if order else None,
        integration_id=integration.id, provider="AMEEX", event_type="PARCEL_STATUS",
        external_order_number=reference or None, tracking_number=tracking or None,
        external_status_name=raw_status or None, internal_status=mapped, event_at=utcnow(),
        matched=bool(order), processed=bool(order), processing_error=None if order else "No matching order",
        raw_payload=body,
    )
    db.add(delivery_event)
    if not order:
        db.flush()
        return {"ok": True, "matched": False}
    shipment.tracking_number = tracking or shipment.tracking_number
    shipment.external_id = shipment.external_id or tracking or None
    shipment.external_status_name = raw_status or None
    shipment.status = mapped or normalized or "UNKNOWN"
    shipment.payload = body
    shipment.last_synced_at = utcnow()
    shipment.last_attempt_at = utcnow()
    if mapped == "DELIVERED":
        shipment.delivered_at = shipment.delivered_at or utcnow()
    elif mapped == "REFUSED":
        shipment.refused_at = shipment.refused_at or utcnow()
    elif mapped == "RETURNED":
        shipment.returned_at = shipment.returned_at or utcnow()
    if mapped and mapped != order.delivery_status:
        previous = order.delivery_status
        order.delivery_status = mapped
        if mapped == "DELIVERED":
            order.delivered_at = order.delivered_at or utcnow()
        db.add(OrderStatusHistory(
            order_id=order.id, from_call_status=order.call_status, to_call_status=order.call_status,
            from_delivery_status=previous, to_delivery_status=mapped,
            reason=f"AMEEX status {raw_status}",
        ))
    db.flush()
    return {"ok": True, "matched": True, "order_id": order.id, "delivery_status": mapped, "tracking": tracking or shipment.tracking_number}
