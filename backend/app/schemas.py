from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(ORMModel):
    id: str
    username: str
    display_name: str
    role: str
    is_active: bool
    phone: str | None = None
    email: str | None = None
    commission_default: Decimal


class StoreCreate(BaseModel):
    name: str
    code: str
    country: str = "MA"
    currency: str = "MAD"
    timezone: str = "Africa/Casablanca"
    shopify_domain: str | None = None
    status: str = "ACTIVE"


class StoreUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    currency: str | None = None
    timezone: str | None = None
    shopify_domain: str | None = None
    status: str | None = None


class StoreOut(ORMModel):
    id: str
    name: str
    code: str
    country: str
    currency: str
    timezone: str
    shopify_domain: str | None
    status: str
    created_at: datetime


class OfferCreate(BaseModel):
    name: str
    quantity: int = Field(ge=1, le=1000)
    price: Decimal = Field(ge=0)
    commission_override: Decimal | None = Field(default=None, ge=0)
    is_active: bool = True


class OfferOut(ORMModel):
    id: str
    product_id: str
    name: str
    quantity: int
    price: Decimal
    commission_override: Decimal | None
    is_active: bool


class ProductCreate(BaseModel):
    store_id: str
    name: str
    sku: str
    image_url: str | None = None
    selling_price: Decimal = Field(ge=0)
    currency: str = "MAD"
    default_qty: int = Field(default=1, ge=1)
    delivery_product_ref: str | None = None
    commission_per_confirmation: Decimal | None = Field(default=None, ge=0)
    status: str = "ACTIVE"
    offers: list[OfferCreate] = []


class ProductUpdate(BaseModel):
    store_id: str | None = None
    name: str | None = None
    sku: str | None = None
    image_url: str | None = None
    selling_price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = None
    default_qty: int | None = Field(default=None, ge=1)
    delivery_product_ref: str | None = None
    commission_per_confirmation: Decimal | None = Field(default=None, ge=0)
    status: str | None = None


class ProductOut(ORMModel):
    id: str
    store_id: str
    name: str
    sku: str
    image_url: str | None
    selling_price: Decimal
    currency: str
    default_qty: int
    delivery_product_ref: str | None
    commission_per_confirmation: Decimal | None
    status: str
    created_at: datetime
    offers: list[OfferOut] = []


class AgentCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    display_name: str
    phone: str | None = None
    email: str | None = None
    role: str = "AGENT"
    commission_default: Decimal = Field(default=Decimal("5.00"), ge=0)
    product_ids: list[str] = []


class AgentUpdate(BaseModel):
    username: str | None = None
    password: str | None = Field(default=None, min_length=8)
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool | None = None
    commission_default: Decimal | None = Field(default=None, ge=0)
    product_ids: list[str] | None = None


class AgentOut(UserOut):
    product_ids: list[str] = []
    current_balance: Decimal = Decimal("0")


class ManualOrderCreate(BaseModel):
    store_id: str
    product_id: str
    offer_id: str | None = None
    customer_name: str
    phone: str
    city: str | None = None
    address: str | None = None
    quantity: int = Field(default=1, ge=1, le=1000)
    unit_price: Decimal | None = Field(default=None, ge=0)
    total_price: Decimal | None = Field(default=None, ge=0)
    assigned_agent_id: str | None = None
    source: str = "MANUAL"
    call_status: str = "NEW"
    call_note: str | None = None


class OrderUpdate(BaseModel):
    customer_name: str | None = None
    phone: str | None = None
    assigned_agent_id: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    unit_price: Decimal | None = Field(default=None, ge=0)
    total_price: Decimal | None = Field(default=None, ge=0)
    call_status: str | None = None
    delivery_status: str | None = None
    call_note: str | None = None
    city: str | None = None
    address: str | None = None
    cancellation_reason: str | None = None
    refusal_reason: str | None = None


class OrderOut(ORMModel):
    id: str
    order_number: str
    store_id: str
    product_id: str
    offer_id: str | None
    customer_id: str
    assigned_agent_id: str | None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    currency: str
    source: str
    external_order_id: str | None
    call_status: str
    delivery_status: str
    call_note: str | None
    city: str | None
    address: str | None
    cancellation_reason: str | None
    refusal_reason: str | None
    assigned_at: datetime | None
    first_call_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    customer_name: str | None = None
    customer_phone: str | None = None
    product_name: str | None = None
    product_sku: str | None = None
    agent_name: str | None = None
    delivery_provider: str | None = None
    delivery_tracking: str | None = None
    delivery_error: str | None = None


class AssignRequest(BaseModel):
    agent_id: str
    assignment_type: str = "MANUAL"


class CallAttemptCreate(BaseModel):
    outcome: str
    note: str | None = None
    channel: str = "PHONE"
    duration_seconds: int | None = Field(default=None, ge=0)
    started_at: datetime | None = None


class CallbackCreate(BaseModel):
    scheduled_at: datetime
    reason: str | None = None
    note: str | None = None
    agent_id: str | None = None


class CallbackUpdate(BaseModel):
    status: str


class PayoutPayRequest(BaseModel):
    payment_method: str = "CASH"
    payment_reference: str | None = None
    note: str | None = None


class AdjustmentCreate(BaseModel):
    amount: Decimal
    description: str = Field(min_length=2, max_length=255)

    @field_validator("amount")
    @classmethod
    def non_zero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("Adjustment amount cannot be zero")
        return value


class IntegrationCreate(BaseModel):
    provider: str
    store_id: str | None = None
    name: str
    is_active: bool = True
    config: dict = {}
    secrets: dict = {}


class IntegrationUpdate(BaseModel):
    store_id: str | None = None
    name: str | None = None
    is_active: bool | None = None
    config: dict | None = None
    secrets: dict | None = None


class IntegrationOut(ORMModel):
    id: str
    provider: str
    store_id: str | None
    name: str
    is_active: bool
    config: dict
    secret_keys: list[str] = []
    webhook_url: str | None = None
    last_test_status: str | None = None
    last_test_message: str | None = None
    last_test_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class SheetWebhookOrder(BaseModel):
    row_number: int | None = None
    sku: str | None = None
    customer_name: str
    phone: str
    city: str | None = None
    address: str | None = None
    quantity: int = Field(default=1, ge=1, le=1000)
    total_price: Decimal | None = Field(default=None, ge=0)
    product_name: str | None = None
    external_order_id: str | None = None
    note: str | None = None


class SheetWebhookBatch(BaseModel):
    orders: list[SheetWebhookOrder]
