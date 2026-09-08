from __future__ import annotations

import uuid
from datetime import timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.time import date_bounds, utcnow
from app.models import (
    AdAccount,
    AdFinanceTransaction,
    AdFundingAccount,
    AdTopupRule,
)


def money(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        return Decimal("0")


def auto_total(
    db: Session,
    account_id: str,
    start,
    end,
) -> Decimal:
    value = (
        db.query(
            func.coalesce(
                func.sum(
                    AdFinanceTransaction.amount
                ),
                0,
            )
        )
        .filter(
            AdFinanceTransaction.ad_account_id
            == account_id,

            AdFinanceTransaction.transaction_type
            == "DEMO_AUTO_TOPUP",

            AdFinanceTransaction.status
            == "SUCCESS",

            AdFinanceTransaction.created_at
            >= start,

            AdFinanceTransaction.created_at
            < end,
        )
        .scalar()
    )

    return money(value)


def evaluate_demo_auto_rule(
    db: Session,
    account_id: str,
    initiated_by_user_id: str | None = None,
    trigger_source: str = "MANUAL_CHECK",
) -> dict:

    # Row lock protects against:
    # scheduler + scheduler
    # scheduler + manual check
    # manual check + manual check
    account = (
        db.query(AdAccount)
        .filter(
            AdAccount.id == account_id
        )
        .with_for_update()
        .first()
    )

    if not account:
        return {
            "ok": False,
            "triggered": False,
            "reason": "ACCOUNT_NOT_FOUND",
            "message": "Ad account not found.",
        }

    account_payload = dict(
        account.provider_payload or {}
    )

    if not account_payload.get("demo"):
        return {
            "ok": False,
            "triggered": False,
            "reason": "NOT_DEMO",
            "message": "Automatic demo funding is demo-only.",
        }

    rule = (
        db.query(AdTopupRule)
        .filter(
            AdTopupRule.ad_account_id
            == account.id
        )
        .first()
    )

    if not rule:
        return {
            "ok": True,
            "triggered": False,
            "reason": "NO_RULE",
            "message": "No funding rule configured.",
        }

    balance = money(
        account.current_balance
    )

    threshold = money(
        rule.threshold_balance
    )

    amount = money(
        rule.refill_amount
    )

    if balance > threshold:
        return {
            "ok": True,
            "triggered": False,
            "reason": "BALANCE_ABOVE_THRESHOLD",
            "message": "Balance is above the funding threshold.",
            "balance": str(balance),
            "threshold": str(threshold),
        }

    if amount <= 0:
        return {
            "ok": True,
            "triggered": False,
            "reason": "INVALID_REFILL_AMOUNT",
            "message": "Refill amount must be greater than zero.",
        }

    if not rule.funding_account_id:
        return {
            "ok": True,
            "triggered": False,
            "reason": "NO_FUNDING_SOURCE",
            "message": "No funding source selected.",
        }

    funding = (
        db.query(AdFundingAccount)
        .filter(
            AdFundingAccount.id
            == rule.funding_account_id
        )
        .with_for_update()
        .first()
    )

    if not funding:
        return {
            "ok": True,
            "triggered": False,
            "reason": "FUNDING_SOURCE_NOT_FOUND",
            "message": "Funding source not found.",
        }

    funding_payload = dict(
        funding.provider_payload or {}
    )

    if not funding_payload.get("demo"):
        return {
            "ok": True,
            "triggered": False,
            "reason": "FUNDING_SOURCE_NOT_DEMO",
            "message": "Demo scheduler requires a demo funding source.",
        }

    if (
        not funding.is_active
        or funding.status != "ACTIVE"
    ):
        return {
            "ok": True,
            "triggered": False,
            "reason": "FUNDING_SOURCE_INACTIVE",
            "message": "Funding source is not active.",
        }

    if funding.currency != account.currency:
        return {
            "ok": True,
            "triggered": False,
            "reason": "CURRENCY_MISMATCH",
            "message": "Funding source currency does not match ad account.",
        }

    now = utcnow()

    # Cooldown
    if rule.last_triggered_at:
        last_triggered = (
            rule.last_triggered_at
        )

        if getattr(
            last_triggered,
            "tzinfo",
            None,
        ) is None:
            last_triggered = (
                last_triggered.replace(
                    tzinfo=timezone.utc
                )
            )

        cooldown_until = (
            last_triggered
            + timedelta(
                minutes=rule.cooldown_minutes
            )
        )

        if now < cooldown_until:
            seconds = max(
                0,
                int(
                    (
                        cooldown_until
                        - now
                    ).total_seconds()
                ),
            )

            return {
                "ok": True,
                "triggered": False,
                "reason": "COOLDOWN_ACTIVE",
                "message": "Cooldown is still active.",
                "seconds_remaining": seconds,
            }

    day_start, day_end = date_bounds(
        "today"
    )

    month_start, month_end = (
        date_bounds(
            "this_month"
        )
    )

    daily_used = auto_total(
        db,
        account.id,
        day_start,
        day_end,
    )

    monthly_used = auto_total(
        db,
        account.id,
        month_start,
        month_end,
    )

    daily_cap = (
        money(rule.daily_cap)
        if rule.daily_cap is not None
        else None
    )

    monthly_cap = (
        money(rule.monthly_cap)
        if rule.monthly_cap is not None
        else None
    )

    if (
        daily_cap is not None
        and daily_used + amount
        > daily_cap
    ):
        return {
            "ok": True,
            "triggered": False,
            "reason": "DAILY_CAP_EXCEEDED",
            "message": "Daily automatic funding cap would be exceeded.",
            "used": str(daily_used),
            "cap": str(daily_cap),
        }

    if (
        monthly_cap is not None
        and monthly_used + amount
        > monthly_cap
    ):
        return {
            "ok": True,
            "triggered": False,
            "reason": "MONTHLY_CAP_EXCEEDED",
            "message": "Monthly automatic funding cap would be exceeded.",
            "used": str(monthly_used),
            "cap": str(monthly_cap),
        }

    funding_before = money(
        funding.current_balance
    )

    if funding_before < amount:
        return {
            "ok": True,
            "triggered": False,
            "reason": "INSUFFICIENT_FUNDING_BALANCE",
            "message": "Insufficient funding wallet balance.",
            "funding_balance":
                str(funding_before),
        }

    ad_before = balance
    ad_after = ad_before + amount

    funding_after = (
        funding_before
        - amount
    )

    transaction = (
        AdFinanceTransaction(
            integration_id=
                account.integration_id,

            ad_account_id=
                account.id,

            funding_account_id=
                funding.id,

            provider=
                account.provider,

            transaction_type=
                "DEMO_AUTO_TOPUP",

            direction="CREDIT",

            amount=amount,

            currency=
                account.currency,

            balance_before=
                ad_before,

            balance_after=
                ad_after,

            idempotency_key=(
                "demo-auto-"
                + uuid.uuid4().hex
            ),

            provider_transaction_id=(
                "DEMO-AUTO-"
                + uuid.uuid4().hex[:16]
            ),

            provider_reference=(
                f"{trigger_source} | "
                f"{funding.name} | "
                f"{funding_before} -> "
                f"{funding_after}"
            ),

            status="SUCCESS",

            attempt_count=1,

            initiated_by_user_id=
                initiated_by_user_id,

            last_checked_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
    )

    account.current_balance = (
        ad_after
    )

    account.balance_synced_at = now

    funding.current_balance = (
        funding_after
    )

    funding.balance_synced_at = now
    funding.updated_at = now

    rule.last_triggered_at = now
    rule.updated_at = now

    if initiated_by_user_id:
        rule.updated_by_user_id = (
            initiated_by_user_id
        )

    db.add(transaction)
    db.flush()

    return {
        "ok": True,
        "triggered": True,
        "reason": "TOPUP_COMPLETED",
        "message": "Demo automatic top-up completed.",
        "trigger_source": trigger_source,
        "amount": str(amount),
        "currency": account.currency,
        "ad_balance_before":
            str(ad_before),
        "ad_balance_after":
            str(ad_after),
        "funding_balance_before":
            str(funding_before),
        "funding_balance_after":
            str(funding_after),
        "transaction_id":
            transaction.id,
        "last_triggered_at":
            rule.last_triggered_at,
    }
