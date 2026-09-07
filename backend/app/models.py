from __future__ import annotations

import uuid
from decimal import Decimal
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.time import utcnow


def uuid4_str() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(30), default="AGENT", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(180), nullable=True)
    commission_default: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("5.00"))
    last_login_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SessionToken(Base):
    __tablename__ = "session_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
    last_seen_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(140))
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(2), default="MA")
    currency: Mapped[str] = mapped_column(String(3), default="MAD")
    timezone: Mapped[str] = mapped_column(String(60), default="Africa/Casablanca")
    shopify_domain: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))

    # Profit Center current cost snapshot.
    # Historical changes are stored in product_cost_history.
    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0")
    )
    packaging_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0")
    )

    currency: Mapped[str] = mapped_column(String(3), default="MAD")
    default_qty: Mapped[int] = mapped_column(Integer, default=1)
    delivery_product_ref: Mapped[str | None] = mapped_column(String(150), nullable=True)
    commission_per_confirmation: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ProductCostHistory(Base):
    __tablename__ = "product_cost_history"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=uuid4_str
    )

    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        index=True
    )

    unit_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0")
    )

    packaging_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        default=Decimal("0")
    )

    effective_from: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        index=True
    )

    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        index=True
    )


class ProductOffer(Base):
    __tablename__ = "product_offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    commission_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentProduct(Base):
    __tablename__ = "agent_products"
    __table_args__ = (UniqueConstraint("agent_id", "product_id", name="uq_agent_product"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    agent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    commission_override: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    name: Mapped[str] = mapped_column(String(160))
    phone_raw: Mapped[str] = mapped_column(String(60))
    phone_e164: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    is_blacklisted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_created_call", "created_at", "call_status"),
        Index("ix_orders_agent_created", "assigned_agent_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    order_number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    store_id: Mapped[str] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    offer_id: Mapped[str | None] = mapped_column(ForeignKey("product_offers.id", ondelete="SET NULL"), nullable=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="MAD")

    source: Mapped[str] = mapped_column(String(40), default="MANUAL", index=True)
    external_order_id: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    call_status: Mapped[str] = mapped_column(String(30), default="NEW", index=True)
    delivery_status: Mapped[str] = mapped_column(String(30), default="NOT_READY", index=True)
    call_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)

    assigned_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_opened_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_call_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dispatched_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OrderStatusHistory(Base):
    __tablename__ = "order_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_call_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_call_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    from_delivery_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_delivery_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    changed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class OrderAssignment(Base):
    __tablename__ = "order_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assigned_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assignment_type: Mapped[str] = mapped_column(String(30), default="MANUAL")
    assigned_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    channel: Mapped[str] = mapped_column(String(30), default="PHONE")
    outcome: Mapped[str] = mapped_column(String(30), index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Callback(Base):
    __tablename__ = "callbacks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scheduled_at: Mapped[object] = mapped_column(DateTime(timezone=True), index=True)
    reason: Mapped[str | None] = mapped_column(String(180), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeliveryShipment(Base):
    __tablename__ = "delivery_shipments"
    __table_args__ = (Index("ix_delivery_provider_status", "provider", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    integration_id: Mapped[str | None] = mapped_column(ForeignKey("integration_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(60), default="MANUAL")
    external_id: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    external_reference: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    tracking_number: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    external_status_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    external_status_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="CREATED", index=True)
    cod_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    delivery_fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    destination_city: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    hub: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    accepted_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_attempt_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refused_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_synced_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DeliveryEvent(Base):
    __tablename__ = "delivery_events"
    __table_args__ = (Index("ix_delivery_event_shipment_created", "shipment_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    shipment_id: Mapped[str | None] = mapped_column(ForeignKey("delivery_shipments.id", ondelete="CASCADE"), nullable=True, index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=True, index=True)
    integration_id: Mapped[str | None] = mapped_column(ForeignKey("integration_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(60), default="DIGYLOG", index=True)
    event_type: Mapped[str] = mapped_column(String(80), default="STATUS_CHANGED", index=True)
    external_order_number: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    tracking_number: Mapped[str | None] = mapped_column(String(140), nullable=True, index=True)
    external_status_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    external_status_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    internal_status: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    event_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    received_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    matched: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DeliveryStatusMapping(Base):
    __tablename__ = "delivery_status_mappings"
    __table_args__ = (UniqueConstraint("provider", "external_status_id", name="uq_delivery_provider_external_status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    provider: Mapped[str] = mapped_column(String(60), default="DIGYLOG", index=True)
    external_status_id: Mapped[int] = mapped_column(Integer, index=True)
    external_status_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    internal_status: Mapped[str] = mapped_column(String(40), index=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_success: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DeliveryDestination(Base):
    __tablename__ = "delivery_destinations"
    __table_args__ = (UniqueConstraint("integration_id", "external_city_id", name="uq_delivery_integration_city"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    integration_id: Mapped[str] = mapped_column(ForeignKey("integration_configs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(60), default="DIGYLOG", index=True)
    external_city_id: Mapped[str] = mapped_column(String(100), index=True)
    city_name: Mapped[str] = mapped_column(String(180), index=True)
    hub: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    fee: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    min_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_synced_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class DeliverySyncRun(Base):
    __tablename__ = "delivery_sync_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    integration_id: Mapped[str] = mapped_column(ForeignKey("integration_configs.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(60), default="DIGYLOG", index=True)
    sync_type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(30), default="RUNNING", index=True)
    scanned_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class PayoutBatch(Base):
    __tablename__ = "payout_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    agent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    period_start: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entries_count: Mapped[int] = mapped_column(Integer, default=0)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    payment_method: Mapped[str] = mapped_column(String(50), default="CASH")
    payment_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    paid_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class PayoutEntry(Base):
    __tablename__ = "payout_entries"
    __table_args__ = (Index("ix_payout_agent_status", "agent_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    agent_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(30), default="CONFIRMATION")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default="UNPAID", index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_batch_id: Mapped[str | None] = mapped_column(ForeignKey("payout_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    paid_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class BlacklistEntry(Base):
    __tablename__ = "blacklist_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    phone_e164: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    reason: Mapped[str] = mapped_column(String(255))
    added_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    before_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    __table_args__ = (Index("ix_integration_provider_store", "provider", "store_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    store_id: Mapped[str | None] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(140))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    secrets_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    last_test_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_test_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class IntegrationEvent(Base):
    __tablename__ = "integration_events"
    __table_args__ = (Index("ix_integration_event_created", "integration_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    integration_id: Mapped[str | None] = mapped_column(ForeignKey("integration_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), index=True)
    direction: Mapped[str] = mapped_column(String(20), default="OUTBOUND", index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default="SUCCESS", index=True)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(60), nullable=True, index=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
