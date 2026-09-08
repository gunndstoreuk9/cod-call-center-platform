from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.db import (
    SessionLocal,
    engine,
)
from app.models import (
    AdAccount,
    AdTopupRule,
)
from app.services.demo_auto_funding import (
    evaluate_demo_auto_rule,
)


logger = logging.getLogger(__name__)

SCHEDULER_LOCK_ID = 2609080601


def run_demo_auto_cycle() -> dict:
    checked = 0
    triggered = 0
    skipped = 0
    errors = 0

    # This session owns the scheduler-cycle lock.
    with SessionLocal() as lock_db:

        if (
            engine.dialect.name
            == "postgresql"
        ):
            acquired = (
                lock_db.execute(
                    text(
                        "SELECT "
                        "pg_try_advisory_xact_lock"
                        "(:lock_id)"
                    ),
                    {
                        "lock_id":
                            SCHEDULER_LOCK_ID
                    },
                )
                .scalar()
            )

            if not acquired:
                lock_db.rollback()

                return {
                    "locked": True,
                    "checked": 0,
                    "triggered": 0,
                    "skipped": 0,
                    "errors": 0,
                }

        rows = (
            lock_db.query(
                AdAccount.id,
            )
            .join(
                AdTopupRule,
                AdTopupRule.ad_account_id
                == AdAccount.id,
            )
            .filter(
                AdAccount.is_active
                == True,
            )
            .all()
        )

        account_ids = [
            row[0]
            for row in rows
        ]

        for account_id in account_ids:

            with SessionLocal() as db:
                try:
                    account = (
                        db.query(
                            AdAccount
                        )
                        .filter(
                            AdAccount.id
                            == account_id
                        )
                        .first()
                    )

                    if not account:
                        skipped += 1
                        continue

                    payload = dict(
                        account.provider_payload
                        or {}
                    )

                    # Hard safety gates.
                    if not payload.get("demo"):
                        skipped += 1
                        continue

                    if not payload.get(
                        "demo_scheduler_enabled"
                    ):
                        skipped += 1
                        continue

                    checked += 1

                    result = (
                        evaluate_demo_auto_rule(
                            db,
                            account_id,
                            initiated_by_user_id=None,
                            trigger_source=
                                "SCHEDULER",
                        )
                    )

                    db.commit()

                    if result.get(
                        "triggered"
                    ):
                        triggered += 1

                    else:
                        skipped += 1

                except Exception:
                    db.rollback()
                    errors += 1

                    logger.exception(
                        "Demo auto funding "
                        "check failed for %s",
                        account_id,
                    )

        # Releases pg advisory xact lock.
        lock_db.commit()

    return {
        "locked": False,
        "checked": checked,
        "triggered": triggered,
        "skipped": skipped,
        "errors": errors,
    }


async def demo_auto_scheduler_loop(
    stop_event: asyncio.Event,
) -> None:

    interval = max(
        60,
        int(
            settings.demo_auto_scheduler_interval_seconds
        ),
    )

    # Avoid changing anything immediately
    # during app deployment/startup.
    try:
        await asyncio.wait_for(
            stop_event.wait(),
            timeout=20,
        )
        return

    except asyncio.TimeoutError:
        pass

    while not stop_event.is_set():

        try:
            result = await asyncio.to_thread(
                run_demo_auto_cycle
            )

            logger.info(
                "Demo auto funding cycle: %s",
                result,
            )

        except Exception:
            logger.exception(
                "Demo auto funding cycle failed"
            )

        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=interval,
            )

        except asyncio.TimeoutError:
            pass
