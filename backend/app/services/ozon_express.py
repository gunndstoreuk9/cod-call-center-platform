from __future__ import annotations

from decimal import Decimal
import json
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import func
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


class OzonExpressError(Exception):
    pass


OZON_STATUS_MAP = {
    "CREATED": "DISPATCHED",
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


def _url(template: str, config: dict, secrets: dict) -> str:
    client_id = str(secrets.get("client_id") or "").strip()
    api_key = str(secrets.get("api_key") or "").strip()
    if not client_id or not api_key:
        raise OzonExpressError("Ozon Express Client ID and API Key are required")
    return (template or "").replace("{client_id}", quote(client_id, safe="")).replace("{api_key}", quote(api_key, safe=""))


def _headers(config: dict, secrets: dict) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if str(config.get("auth_mode") or "path").lower() == "headers":
        headers[str(config.get("client_id_header") or "Client-Id")] = str(secrets.get("client_id") or "")
        headers[str(config.get("api_key_header") or "Api-Key")] = str(secrets.get("api_key") or "")
    return headers


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
    config, _ = _settings(integration)
    url = str(config.get("cities_url") or "https://api.ozonexpress.ma/cities")
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            response = client.get(url, headers={"Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise OzonExpressError(f"Could not load Ozon Express cities: {exc}") from exc

    cities = data.get("CITIES") if isinstance(data, dict) else None
    values = list(cities.values()) if isinstance(cities, dict) else cities if isinstance(cities, list) else []
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
                provider="OZON_EXPRESS",
                external_city_id=city_id,
                city_name=city_name,
            )
            db.add(row)
        row.provider = "OZON_EXPRESS"
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
        raise OzonExpressError("Order city is required for Ozon Express")
    if value.isdigit():
        return value
    row = db.query(DeliveryDestination).filter(
        DeliveryDestination.integration_id == integration.id,
        func.lower(DeliveryDestination.city_name) == value.lower(),
        DeliveryDestination.is_active.is_(True),
    ).first()
    if not row:
        sync_cities(db, integration)
        row = db.query(DeliveryDestination).filter(
            DeliveryDestination.integration_id == integration.id,
            func.lower(DeliveryDestination.city_name) == value.lower(),
            DeliveryDestination.is_active.is_(True),
        ).first()
    if not row:
        raise OzonExpressError(
            f"Ozon Express city ID not found for '{value}'. Use the exact city name from the Ozon Express cities list."
        )
    return row.external_city_id


def build_payload(db: Session, integration: IntegrationConfig, order: Order) -> dict:
    config, _ = _settings(integration)
    customer = db.query(Customer).filter(Customer.id == order.customer_id).first()
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if not customer or not product:
        raise OzonExpressError("Order customer or product is missing")
    price = Decimal(order.total_price)
    payload = {
        "parcel-receiver": customer.name,
        "parcel-phone": _local_phone(customer.phone_e164),
        "parcel-city": _city_id(db, integration, order.city or customer.city),
        "parcel-address": order.address or customer.address or order.city or customer.city or "",
        "parcel-note": order.call_note or "",
        "parcel-price": str(price),
        "parcel-nature": product.delivery_product_ref or product.name or product.sku,
        "parcel-stock": str(int(config.get("parcel_stock", 0))),
        "parcel-open": str(int(config.get("parcel_open", 1))),
        "parcel-fragile": str(int(config.get("parcel_fragile", 0))),
        "parcel-replace": str(int(config.get("parcel_replace", 0))),
        "products": json.dumps([{"ref": product.sku, "qnty": int(order.quantity)}]),
    }
    if config.get("use_order_number_as_tracking", False):
        payload["tracking-number"] = order.order_number
    if price <= 0 or price > 5000:
        payload["parcel-declared-value"] = str(max(price, Decimal("50")))
    return payload


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
    config, secrets = _settings(integration)
    target_template = str(config.get("cities_url") or "https://api.ozonexpress.ma/cities")
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(target_template, headers={"Accept": "application/json"})
        if response.status_code >= 400:
            return {"ok": False, "message": f"Ozon Express returned HTTP {response.status_code}: {response.text[:300]}"}
        data = response.json()
        cities = data.get("CITIES") if isinstance(data, dict) else None
        count = len(cities or {})
        return {"ok": True, "message": f"Ozon Express API is reachable ({count} cities). Credentials will be validated on the first parcel."}
    except Exception as exc:
        return {"ok": False, "message": _safe_error(exc, secrets)}


def dispatch_order(db: Session, integration: IntegrationConfig, order: Order) -> DeliveryShipment:
    if order.call_status != "CONFIRMED":
        raise OzonExpressError("Order must be CONFIRMED before dispatch")
    existing = (
        db.query(DeliveryShipment)
        .filter(
            DeliveryShipment.order_id == order.id,
            DeliveryShipment.provider == "OZON_EXPRESS",
            DeliveryShipment.status.notin_(["FAILED", "CANCELLED"]),
        )
        .order_by(DeliveryShipment.created_at.desc())
        .first()
    )
    if existing:
        raise OzonExpressError(f"Order already has an Ozon Express shipment ({existing.tracking_number or existing.id})")

    config, secrets = _settings(integration)
    endpoint = str(config.get("create_parcel_url") or "https://api.ozonexpress.ma/customers/{client_id}/{api_key}/add-parcel").strip()
    api_url = _url(endpoint, config, secrets)
    payload = build_payload(db, integration, order)
    event = IntegrationEvent(
        integration_id=integration.id, provider="OZON_EXPRESS", direction="OUTBOUND",
        event_type="CREATE_PARCEL", status="PENDING", entity_type="ORDER", entity_id=order.id,
        payload=payload,
    )
    db.add(event)
    db.flush()
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as client:
            files = {key: (None, str(value)) for key, value in payload.items() if value not in (None, "")}
            response = client.post(api_url, files=files, headers=_headers(config, secrets))
        if response.status_code >= 400:
            raise OzonExpressError(f"Ozon Express rejected parcel ({response.status_code}): {response.text[:400]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise OzonExpressError(f"Ozon Express returned non-JSON response: {response.text[:300]}") from exc
        tracking = _find_value(data, ("TRACKING-NUMBER", "tracking-number", "tracking_number", "tracking", "parcel_code", "parcelCode", "code", "barcode"))
        if not tracking:
            raise OzonExpressError("Ozon Express accepted the request but no parcel tracking code was found")
        tracking = str(tracking)
        shipment = DeliveryShipment(
            order_id=order.id, integration_id=integration.id, provider="OZON_EXPRESS",
            external_id=tracking, external_reference=order.order_number, tracking_number=tracking,
            status="DISPATCHED", cod_amount=order.total_price, destination_city=order.city,
            delivery_fee=_find_value(data, ("DELIVERED-PRICE", "delivered-price", "delivery_fee")),
            accepted_at=utcnow(), last_synced_at=utcnow(), last_attempt_at=utcnow(), payload=data,
        )
        db.add(shipment)
        db.flush()
        db.add(DeliveryEvent(
            shipment_id=shipment.id, order_id=order.id, integration_id=integration.id,
            provider="OZON_EXPRESS", event_type="CREATE_PARCEL",
            external_order_number=order.order_number, tracking_number=tracking,
            internal_status="DISPATCHED", event_at=utcnow(), raw_payload={"request": payload, "response": data},
        ))
        previous = order.delivery_status
        order.delivery_status = "DISPATCHED"
        order.dispatched_at = order.dispatched_at or utcnow()
        db.add(OrderStatusHistory(
            order_id=order.id, from_call_status=order.call_status, to_call_status=order.call_status,
            from_delivery_status=previous, to_delivery_status="DISPATCHED", reason="Dispatched to Ozon Express",
        ))
        event.status = "SUCCESS"
        event.payload = {"request": payload, "response": data}
        db.flush()
        return shipment
    except Exception as exc:
        safe_error = _safe_error(exc, secrets)
        event.status = "FAILED"
        event.error = safe_error
        db.add(DeliveryShipment(
            order_id=order.id, integration_id=integration.id, provider="OZON_EXPRESS",
            status="FAILED", cod_amount=order.total_price, destination_city=order.city,
            payload=payload, error=safe_error, retry_count=1, last_attempt_at=utcnow(),
        ))
        db.flush()
        if isinstance(exc, OzonExpressError):
            raise OzonExpressError(safe_error) from exc
        raise OzonExpressError(safe_error) from exc


def apply_webhook(db: Session, integration: IntegrationConfig, body: dict) -> dict:
    tracking_value = _find_value(body, ("tracking_number", "tracking", "parcel_code", "parcelCode", "code", "barcode"))
    reference_value = _find_value(body, ("reference", "order_number", "orderNumber", "merchant_reference"))
    status_value = _find_value(body, ("status", "parcel_status", "parcelStatus", "state", "situation"))
    tracking = str(tracking_value or "").strip()
    reference = str(reference_value or "").strip()
    raw_status = str(status_value or "").strip()
    normalized = raw_status.upper().replace(" ", "_").replace("É", "E").replace("È", "E")
    mapped = OZON_STATUS_MAP.get(normalized)

    order = db.query(Order).filter(Order.order_number == reference).first() if reference else None
    shipment = None
    if tracking:
        shipment = db.query(DeliveryShipment).filter(
            DeliveryShipment.provider == "OZON_EXPRESS", DeliveryShipment.tracking_number == tracking
        ).first()
        if not order and shipment:
            order = db.query(Order).filter(Order.id == shipment.order_id).first()
    if order and not shipment:
        shipment = db.query(DeliveryShipment).filter(
            DeliveryShipment.provider == "OZON_EXPRESS", DeliveryShipment.order_id == order.id
        ).order_by(DeliveryShipment.created_at.desc()).first()

    db.add(IntegrationEvent(
        integration_id=integration.id, provider="OZON_EXPRESS", direction="INBOUND",
        event_type="PARCEL_STATUS", status="SUCCESS" if order else "IGNORED",
        entity_type="ORDER" if order else None, entity_id=order.id if order else None,
        payload=body, error=None if order else "No matching order",
    ))
    delivery_event = DeliveryEvent(
        shipment_id=shipment.id if shipment else None, order_id=order.id if order else None,
        integration_id=integration.id, provider="OZON_EXPRESS", event_type="PARCEL_STATUS",
        external_order_number=reference or None, tracking_number=tracking or None,
        external_status_name=raw_status or None, internal_status=mapped, event_at=utcnow(),
        matched=bool(order), processed=bool(order), processing_error=None if order else "No matching order",
        raw_payload=body,
    )
    db.add(delivery_event)
    if not order:
        db.flush()
        return {"ok": True, "matched": False}
    if not shipment:
        shipment = DeliveryShipment(
            order_id=order.id, integration_id=integration.id, provider="OZON_EXPRESS",
            tracking_number=tracking or None, external_id=tracking or None,
            external_reference=reference or order.order_number, status=mapped or normalized or "CREATED",
            cod_amount=order.total_price, destination_city=order.city, payload=body,
        )
        db.add(shipment)
        db.flush()
        delivery_event.shipment_id = shipment.id
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
            reason=f"Ozon Express status {raw_status}",
        ))
    db.flush()
    return {"ok": True, "matched": True, "order_id": order.id, "delivery_status": mapped, "tracking": tracking or shipment.tracking_number}
