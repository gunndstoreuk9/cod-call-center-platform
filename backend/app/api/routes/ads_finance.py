from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_roles
from app.core.time import utcnow
from app.models import (
    AdAccount,
    AdAccountProductMap,
    AdFinanceTransaction,
    AdTopupRule,
    IntegrationConfig,
    Product,
    Store,
    User,
)
from app.services.audit import log_action


router = APIRouter(
    prefix="/ads-finance",
    tags=["ads-finance"],
)


class ProductMapRequest(BaseModel):
    product_id: str | None = None


class TopupRuleRequest(BaseModel):
    threshold_balance: Decimal = Field(
        default=Decimal("10"),
        ge=0,
    )

    refill_amount: Decimal = Field(
        default=Decimal("20"),
        ge=0,
    )

    daily_cap: Decimal | None = Field(
        default=None,
        ge=0,
    )

    monthly_cap: Decimal | None = Field(
        default=None,
        ge=0,
    )

    cooldown_minutes: int = Field(
        default=30,
        ge=5,
        le=1440,
    )


class DemoMetricsRequest(BaseModel):
    balance: Decimal = Field(
        ge=0,
    )

    spend_today: Decimal = Field(
        ge=0,
    )


def money(value) -> Decimal:
    try:
        return Decimal(
            str(value or 0)
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return Decimal("0")


def account_or_404(
    db: Session,
    account_id: str,
) -> AdAccount:

    row = (
        db.query(AdAccount)
        .filter(
            AdAccount.id == account_id
        )
        .first()
    )

    if not row:
        raise HTTPException(
            404,
            "Ad account not found",
        )

    return row


def active_product_map(
    db: Session,
    account_id: str,
) -> AdAccountProductMap | None:

    return (
        db.query(
            AdAccountProductMap
        )
        .filter(
            AdAccountProductMap.ad_account_id
            == account_id,

            AdAccountProductMap.is_active
            == True,
        )
        .order_by(
            AdAccountProductMap.created_at.desc()
        )
        .first()
    )


def account_rule(
    db: Session,
    account_id: str,
) -> AdTopupRule | None:

    return (
        db.query(AdTopupRule)
        .filter(
            AdTopupRule.ad_account_id
            == account_id
        )
        .first()
    )


def rule_out(
    row: AdTopupRule | None,
) -> dict | None:

    if not row:
        return None

    return {
        "id":
            row.id,

        "threshold_balance":
            str(row.threshold_balance),

        "refill_amount":
            str(row.refill_amount),

        "daily_cap":
            (
                str(row.daily_cap)
                if row.daily_cap is not None
                else None
            ),

        "monthly_cap":
            (
                str(row.monthly_cap)
                if row.monthly_cap is not None
                else None
            ),

        "cooldown_minutes":
            row.cooldown_minutes,

        # Intentionally locked in Phase 2.
        "auto_enabled":
            False,

        "last_triggered_at":
            row.last_triggered_at,

        "created_at":
            row.created_at,

        "updated_at":
            row.updated_at,
    }


def account_out(
    db: Session,
    row: AdAccount,
) -> dict:

    integration = None

    if row.integration_id:
        integration = (
            db.query(IntegrationConfig)
            .filter(
                IntegrationConfig.id
                == row.integration_id
            )
            .first()
        )

    store = None

    if row.store_id:
        store = (
            db.query(Store)
            .filter(
                Store.id == row.store_id
            )
            .first()
        )

    mapping = active_product_map(
        db,
        row.id,
    )

    product = None

    if mapping:
        product = (
            db.query(Product)
            .filter(
                Product.id
                == mapping.product_id
            )
            .first()
        )

    rule = account_rule(
        db,
        row.id,
    )

    payload = dict(
        row.provider_payload or {}
    )

    balance = money(
        row.current_balance
    )

    spend_today = money(
        payload.get(
            "spend_today"
        )
    )

    threshold = (
        money(
            rule.threshold_balance
        )
        if rule
        else Decimal("0")
    )

    low_balance = bool(
        rule
        and threshold > 0
        and balance <= threshold
    )

    return {
        "id":
            row.id,

        "provider":
            row.provider,

        "advertiser_id":
            row.external_account_id,

        "business_center_id":
            row.external_business_id,

        "name":
            row.name,

        "currency":
            row.currency,

        "balance":
            str(balance),

        "spend_today":
            str(spend_today),

        "status":
            row.status,

        "is_active":
            row.is_active,

        "demo":
            bool(
                payload.get("demo")
            ),

        "low_balance":
            low_balance,

        "balance_synced_at":
            row.balance_synced_at,

        "spend_synced_at":
            row.spend_synced_at,

        "last_error":
            row.last_error,

        "connection": (
            {
                "id":
                    integration.id,

                "name":
                    integration.name,

                "provider":
                    integration.provider,

                "mode":
                    (
                        integration.config
                        or {}
                    ).get("mode"),
            }
            if integration
            else None
        ),

        "store": (
            {
                "id":
                    store.id,

                "name":
                    store.name,
            }
            if store
            else None
        ),

        "product": (
            {
                "id":
                    product.id,

                "name":
                    product.name,

                "sku":
                    product.sku,

                "image_url":
                    product.image_url,
            }
            if product
            else None
        ),

        "rule":
            rule_out(rule),
    }


def filtered_accounts(
    db: Session,
    store_id: str | None = None,
    product_id: str | None = None,
    provider: str | None = None,
) -> list[AdAccount]:

    q = db.query(AdAccount)

    if store_id:
        q = q.filter(
            AdAccount.store_id
            == store_id
        )

    if provider:
        q = q.filter(
            AdAccount.provider
            == provider.strip().upper()
        )

    rows = (
        q.order_by(
            AdAccount.created_at.desc()
        )
        .all()
    )

    if not product_id:
        return rows

    mapped_ids = {
        mapping.ad_account_id
        for mapping in (
            db.query(
                AdAccountProductMap
            )
            .filter(
                AdAccountProductMap.product_id
                == product_id,

                AdAccountProductMap.is_active
                == True,
            )
            .all()
        )
    }

    return [
        row
        for row in rows
        if row.id in mapped_ids
    ]


@router.get("/dashboard")
def ads_finance_dashboard(
    store_id: str | None = None,
    product_id: str | None = None,
    provider: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    rows = filtered_accounts(
        db,
        store_id=store_id,
        product_id=product_id,
        provider=provider,
    )

    accounts = [
        account_out(
            db,
            row,
        )
        for row in rows
    ]

    currency_totals = {}

    for account in accounts:
        currency = (
            account["currency"]
            or "USD"
        )

        bucket = (
            currency_totals
            .setdefault(
                currency,
                {
                    "currency":
                        currency,

                    "balance":
                        Decimal("0"),

                    "spend_today":
                        Decimal("0"),

                    "accounts":
                        0,
                },
            )
        )

        bucket["balance"] += money(
            account["balance"]
        )

        bucket["spend_today"] += money(
            account["spend_today"]
        )

        bucket["accounts"] += 1

    currency_rows = [
        {
            "currency":
                value["currency"],

            "balance":
                str(
                    value["balance"]
                ),

            "spend_today":
                str(
                    value["spend_today"]
                ),

            "accounts":
                value["accounts"],
        }
        for value in currency_totals.values()
    ]

    return {
        "accounts_count":
            len(accounts),

        "active_accounts":
            sum(
                1
                for account in accounts
                if (
                    account["is_active"]
                    and account["status"]
                    == "ACTIVE"
                )
            ),

        "low_balance_accounts":
            sum(
                1
                for account in accounts
                if account["low_balance"]
            ),

        "mapped_accounts":
            sum(
                1
                for account in accounts
                if account["product"]
            ),

        "currency_totals":
            currency_rows,

        "accounts":
            accounts,
    }


@router.get("/accounts")
def list_ad_accounts(
    store_id: str | None = None,
    product_id: str | None = None,
    provider: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    rows = filtered_accounts(
        db,
        store_id=store_id,
        product_id=product_id,
        provider=provider,
    )

    return [
        account_out(
            db,
            row,
        )
        for row in rows
    ]


@router.put(
    "/accounts/{account_id}/product"
)
def map_account_product(
    account_id: str,
    payload: ProductMapRequest,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    account = account_or_404(
        db,
        account_id,
    )

    current_maps = (
        db.query(
            AdAccountProductMap
        )
        .filter(
            AdAccountProductMap.ad_account_id
            == account.id
        )
        .all()
    )

    before_product_ids = [
        row.product_id
        for row in current_maps
        if row.is_active
    ]

    for row in current_maps:
        row.is_active = False

    if payload.product_id:
        product = (
            db.query(Product)
            .filter(
                Product.id
                == payload.product_id
            )
            .first()
        )

        if not product:
            raise HTTPException(
                400,
                "Invalid product",
            )

        if (
            account.store_id
            and product.store_id
            != account.store_id
        ):
            raise HTTPException(
                400,
                "Product must belong to the same store as the ad account",
            )

        existing = next(
            (
                row
                for row in current_maps
                if row.product_id
                == product.id
            ),
            None,
        )

        if existing:
            existing.is_active = True

        else:
            db.add(
                AdAccountProductMap(
                    ad_account_id=
                        account.id,

                    product_id=
                        product.id,

                    is_active=True,

                    created_by_user_id=
                        user.id,

                    created_at=
                        utcnow(),
                )
            )

    log_action(
        db,
        user_id=user.id,
        action="AD_ACCOUNT_PRODUCT_MAPPED",
        entity_type="AD_ACCOUNT",
        entity_id=account.id,
        before={
            "product_ids":
                before_product_ids,
        },
        after={
            "product_id":
                payload.product_id,
        },
    )

    db.commit()

    return account_out(
        db,
        account,
    )


@router.put(
    "/accounts/{account_id}/rule"
)
def save_topup_rule(
    account_id: str,
    payload: TopupRuleRequest,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    account = account_or_404(
        db,
        account_id,
    )

    row = account_rule(
        db,
        account.id,
    )

    if not row:
        row = AdTopupRule(
            ad_account_id=
                account.id,

            threshold_balance=
                payload.threshold_balance,

            refill_amount=
                payload.refill_amount,

            daily_cap=
                payload.daily_cap,

            monthly_cap=
                payload.monthly_cap,

            cooldown_minutes=
                payload.cooldown_minutes,

            # Money movement is intentionally
            # disabled in Phase 2.
            auto_enabled=False,

            created_by_user_id=
                user.id,

            updated_by_user_id=
                user.id,

            created_at=
                utcnow(),

            updated_at=
                utcnow(),
        )

        db.add(row)

    else:
        row.threshold_balance = (
            payload.threshold_balance
        )

        row.refill_amount = (
            payload.refill_amount
        )

        row.daily_cap = (
            payload.daily_cap
        )

        row.monthly_cap = (
            payload.monthly_cap
        )

        row.cooldown_minutes = (
            payload.cooldown_minutes
        )

        # Keep locked OFF until the
        # funding phase is installed.
        row.auto_enabled = False

        row.updated_by_user_id = (
            user.id
        )

        row.updated_at = utcnow()

    log_action(
        db,
        user_id=user.id,
        action="AD_TOPUP_RULE_SAVED",
        entity_type="AD_ACCOUNT",
        entity_id=account.id,
        after={
            "threshold_balance":
                str(
                    payload.threshold_balance
                ),

            "refill_amount":
                str(
                    payload.refill_amount
                ),

            "daily_cap":
                (
                    str(payload.daily_cap)
                    if payload.daily_cap
                    is not None
                    else None
                ),

            "monthly_cap":
                (
                    str(payload.monthly_cap)
                    if payload.monthly_cap
                    is not None
                    else None
                ),

            "cooldown_minutes":
                payload.cooldown_minutes,

            "auto_enabled":
                False,
        },
    )

    db.commit()
    db.refresh(row)

    return rule_out(row)


@router.delete(
    "/accounts/{account_id}/rule"
)
def delete_topup_rule(
    account_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    account = account_or_404(
        db,
        account_id,
    )

    row = account_rule(
        db,
        account.id,
    )

    if row:
        db.delete(row)

    log_action(
        db,
        user_id=user.id,
        action="AD_TOPUP_RULE_DELETED",
        entity_type="AD_ACCOUNT",
        entity_id=account.id,
    )

    db.commit()

    return {
        "ok": True,
    }


@router.post(
    "/accounts/{account_id}/demo-metrics"
)
def update_demo_metrics(
    account_id: str,
    payload: DemoMetricsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    account = account_or_404(
        db,
        account_id,
    )

    provider_payload = dict(
        account.provider_payload
        or {}
    )

    if not provider_payload.get(
        "demo"
    ):
        raise HTTPException(
            400,
            "Demo metrics can only be changed on demo accounts",
        )

    before = {
        "balance":
            str(
                account.current_balance
            ),

        "spend_today":
            str(
                provider_payload.get(
                    "spend_today",
                    "0",
                )
            ),
    }

    account.current_balance = (
        payload.balance
    )

    provider_payload[
        "spend_today"
    ] = str(
        payload.spend_today
    )

    account.provider_payload = (
        provider_payload
    )

    account.balance_synced_at = (
        utcnow()
    )

    account.spend_synced_at = (
        utcnow()
    )

    log_action(
        db,
        user_id=user.id,
        action="AD_DEMO_METRICS_UPDATED",
        entity_type="AD_ACCOUNT",
        entity_id=account.id,
        before=before,
        after={
            "balance":
                str(payload.balance),

            "spend_today":
                str(
                    payload.spend_today
                ),
        },
    )

    db.commit()
    db.refresh(account)

    return account_out(
        db,
        account,
    )


@router.get("/transactions")
def list_ad_finance_transactions(
    account_id: str | None = None,
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    q = db.query(
        AdFinanceTransaction
    )

    if account_id:
        q = q.filter(
            AdFinanceTransaction.ad_account_id
            == account_id
        )

    rows = (
        q.order_by(
            AdFinanceTransaction.created_at.desc()
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "id":
                row.id,

            "ad_account_id":
                row.ad_account_id,

            "provider":
                row.provider,

            "transaction_type":
                row.transaction_type,

            "direction":
                row.direction,

            "amount":
                str(row.amount),

            "currency":
                row.currency,

            "balance_before":
                (
                    str(row.balance_before)
                    if row.balance_before
                    is not None
                    else None
                ),

            "balance_after":
                (
                    str(row.balance_after)
                    if row.balance_after
                    is not None
                    else None
                ),

            "status":
                row.status,

            "provider_transaction_id":
                row.provider_transaction_id,

            "error_message":
                row.error_message,

            "completed_at":
                row.completed_at,

            "created_at":
                row.created_at,
        }
        for row in rows
    ]
