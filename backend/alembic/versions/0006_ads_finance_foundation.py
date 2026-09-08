"""ads finance foundation

Revision ID: 0006_ads_finance_foundation
Revises: 0005_profit_ad_spend
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0006_ads_finance_foundation"
down_revision = "0005_profit_ad_spend"
branch_labels = None
depends_on = None


def has_table(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:

    if not has_table("ad_accounts"):
        op.create_table(
            "ad_accounts",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("integration_id", sa.String(36), nullable=True),
            sa.Column("store_id", sa.String(36), nullable=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("external_account_id", sa.String(180), nullable=False),
            sa.Column("external_business_id", sa.String(180), nullable=True),
            sa.Column("external_business_name", sa.String(180), nullable=True),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
            sa.Column("current_balance", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("status", sa.String(40), nullable=False, server_default="UNKNOWN"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("provider_payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("balance_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("spend_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

            sa.ForeignKeyConstraint(
                ["integration_id"],
                ["integration_configs.id"],
                ondelete="SET NULL",
            ),

            sa.ForeignKeyConstraint(
                ["store_id"],
                ["stores.id"],
                ondelete="SET NULL",
            ),

            sa.PrimaryKeyConstraint("id"),

            sa.UniqueConstraint(
                "provider",
                "external_account_id",
                name="uq_ad_accounts_provider_external",
            ),
        )

        op.create_index(
            "ix_ad_accounts_integration_id",
            "ad_accounts",
            ["integration_id"],
        )

        op.create_index(
            "ix_ad_accounts_store_id",
            "ad_accounts",
            ["store_id"],
        )

        op.create_index(
            "ix_ad_accounts_provider",
            "ad_accounts",
            ["provider"],
        )

        op.create_index(
            "ix_ad_accounts_external_account_id",
            "ad_accounts",
            ["external_account_id"],
        )

        op.create_index(
            "ix_ad_accounts_external_business_id",
            "ad_accounts",
            ["external_business_id"],
        )

        op.create_index(
            "ix_ad_accounts_status",
            "ad_accounts",
            ["status"],
        )

        op.create_index(
            "ix_ad_accounts_is_active",
            "ad_accounts",
            ["is_active"],
        )

        op.create_index(
            "ix_ad_accounts_balance_synced_at",
            "ad_accounts",
            ["balance_synced_at"],
        )

        op.create_index(
            "ix_ad_accounts_created_at",
            "ad_accounts",
            ["created_at"],
        )

        op.create_index(
            "ix_ad_accounts_provider_status",
            "ad_accounts",
            ["provider", "status"],
        )


    if not has_table("ad_account_product_maps"):
        op.create_table(
            "ad_account_product_maps",

            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("ad_account_id", sa.String(36), nullable=False),
            sa.Column("product_id", sa.String(36), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by_user_id", sa.String(36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),

            sa.ForeignKeyConstraint(
                ["ad_account_id"],
                ["ad_accounts.id"],
                ondelete="CASCADE",
            ),

            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                ondelete="CASCADE",
            ),

            sa.ForeignKeyConstraint(
                ["created_by_user_id"],
                ["users.id"],
                ondelete="SET NULL",
            ),

            sa.PrimaryKeyConstraint("id"),

            sa.UniqueConstraint(
                "ad_account_id",
                "product_id",
                name="uq_ad_account_product_map",
            ),
        )

        op.create_index(
            "ix_ad_account_product_maps_ad_account_id",
            "ad_account_product_maps",
            ["ad_account_id"],
        )

        op.create_index(
            "ix_ad_account_product_maps_product_id",
            "ad_account_product_maps",
            ["product_id"],
        )

        op.create_index(
            "ix_ad_account_product_maps_is_active",
            "ad_account_product_maps",
            ["is_active"],
        )

        op.create_index(
            "ix_ad_account_product_maps_created_at",
            "ad_account_product_maps",
            ["created_at"],
        )


    if not has_table("ad_funding_accounts"):
        op.create_table(
            "ad_funding_accounts",

            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("integration_id", sa.String(36), nullable=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("external_account_id", sa.String(180), nullable=False),
            sa.Column("name", sa.String(180), nullable=False),
            sa.Column("account_type", sa.String(40), nullable=False, server_default="BALANCE"),
            sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),
            sa.Column("current_balance", sa.Numeric(18, 4), nullable=False, server_default="0"),
            sa.Column("status", sa.String(40), nullable=False, server_default="UNKNOWN"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("provider_payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("balance_synced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),

            sa.ForeignKeyConstraint(
                ["integration_id"],
                ["integration_configs.id"],
                ondelete="SET NULL",
            ),

            sa.PrimaryKeyConstraint("id"),

            sa.UniqueConstraint(
                "provider",
                "external_account_id",
                name="uq_ad_funding_provider_external",
            ),
        )

        for column in [
            "integration_id",
            "provider",
            "external_account_id",
            "account_type",
            "status",
            "is_active",
            "balance_synced_at",
            "created_at",
        ]:
            op.create_index(
                f"ix_ad_funding_accounts_{column}",
                "ad_funding_accounts",
                [column],
            )

        op.create_index(
            "ix_ad_funding_provider_status",
            "ad_funding_accounts",
            ["provider", "status"],
        )


    if not has_table("ad_topup_rules"):
        op.create_table(
            "ad_topup_rules",

            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("ad_account_id", sa.String(36), nullable=False),
            sa.Column("funding_account_id", sa.String(36), nullable=True),

            sa.Column(
                "threshold_balance",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),

            sa.Column(
                "refill_amount",
                sa.Numeric(18, 4),
                nullable=False,
                server_default="0",
            ),

            sa.Column(
                "daily_cap",
                sa.Numeric(18, 4),
                nullable=True,
            ),

            sa.Column(
                "monthly_cap",
                sa.Numeric(18, 4),
                nullable=True,
            ),

            sa.Column(
                "cooldown_minutes",
                sa.Integer(),
                nullable=False,
                server_default="30",
            ),

            # SAFETY:
            # Automatic money movement always starts disabled.
            sa.Column(
                "auto_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),

            sa.Column(
                "last_triggered_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),

            sa.Column(
                "created_by_user_id",
                sa.String(36),
                nullable=True,
            ),

            sa.Column(
                "updated_by_user_id",
                sa.String(36),
                nullable=True,
            ),

            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),

            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),

            sa.ForeignKeyConstraint(
                ["ad_account_id"],
                ["ad_accounts.id"],
                ondelete="CASCADE",
            ),

            sa.ForeignKeyConstraint(
                ["funding_account_id"],
                ["ad_funding_accounts.id"],
                ondelete="SET NULL",
            ),

            sa.ForeignKeyConstraint(
                ["created_by_user_id"],
                ["users.id"],
                ondelete="SET NULL",
            ),

            sa.ForeignKeyConstraint(
                ["updated_by_user_id"],
                ["users.id"],
                ondelete="SET NULL",
            ),

            sa.PrimaryKeyConstraint("id"),

            sa.UniqueConstraint(
                "ad_account_id",
                name="uq_ad_topup_rule_account",
            ),
        )

        for column in [
            "ad_account_id",
            "funding_account_id",
            "auto_enabled",
            "last_triggered_at",
            "created_at",
        ]:
            op.create_index(
                f"ix_ad_topup_rules_{column}",
                "ad_topup_rules",
                [column],
            )


    if not has_table("ad_finance_transactions"):
        op.create_table(
            "ad_finance_transactions",

            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("integration_id", sa.String(36), nullable=True),
            sa.Column("ad_account_id", sa.String(36), nullable=True),
            sa.Column("funding_account_id", sa.String(36), nullable=True),

            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("transaction_type", sa.String(40), nullable=False),
            sa.Column("direction", sa.String(20), nullable=False, server_default="CREDIT"),

            sa.Column("amount", sa.Numeric(18, 4), nullable=False),
            sa.Column("currency", sa.String(10), nullable=False, server_default="USD"),

            sa.Column("balance_before", sa.Numeric(18, 4), nullable=True),
            sa.Column("balance_after", sa.Numeric(18, 4), nullable=True),

            sa.Column("idempotency_key", sa.String(180), nullable=False),

            sa.Column(
                "provider_transaction_id",
                sa.String(180),
                nullable=True,
            ),

            sa.Column(
                "provider_reference",
                sa.String(255),
                nullable=True,
            ),

            sa.Column(
                "status",
                sa.String(40),
                nullable=False,
                server_default="PENDING",
            ),

            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),

            sa.Column("error_code", sa.String(100), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),

            sa.Column(
                "initiated_by_user_id",
                sa.String(36),
                nullable=True,
            ),

            sa.Column(
                "last_checked_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),

            sa.Column(
                "completed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),

            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),

            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),

            sa.ForeignKeyConstraint(
                ["integration_id"],
                ["integration_configs.id"],
                ondelete="SET NULL",
            ),

            sa.ForeignKeyConstraint(
                ["ad_account_id"],
                ["ad_accounts.id"],
                ondelete="SET NULL",
            ),

            sa.ForeignKeyConstraint(
                ["funding_account_id"],
                ["ad_funding_accounts.id"],
                ondelete="SET NULL",
            ),

            sa.ForeignKeyConstraint(
                ["initiated_by_user_id"],
                ["users.id"],
                ondelete="SET NULL",
            ),

            sa.PrimaryKeyConstraint("id"),

            sa.UniqueConstraint(
                "idempotency_key",
                name="uq_ad_finance_transaction_idempotency",
            ),
        )

        for column in [
            "integration_id",
            "ad_account_id",
            "funding_account_id",
            "provider",
            "transaction_type",
            "direction",
            "provider_transaction_id",
            "status",
            "completed_at",
            "created_at",
        ]:
            op.create_index(
                f"ix_ad_finance_transactions_{column}",
                "ad_finance_transactions",
                [column],
            )

        op.create_index(
            "ix_ad_finance_account_created",
            "ad_finance_transactions",
            ["ad_account_id", "created_at"],
        )

        op.create_index(
            "ix_ad_finance_provider_status",
            "ad_finance_transactions",
            ["provider", "status"],
        )


    if not has_table("ad_provider_webhook_events"):
        op.create_table(
            "ad_provider_webhook_events",

            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("integration_id", sa.String(36), nullable=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("external_event_id", sa.String(255), nullable=False),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("status", sa.String(40), nullable=False, server_default="RECEIVED"),
            sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),

            sa.ForeignKeyConstraint(
                ["integration_id"],
                ["integration_configs.id"],
                ondelete="SET NULL",
            ),

            sa.PrimaryKeyConstraint("id"),

            sa.UniqueConstraint(
                "provider",
                "external_event_id",
                name="uq_ad_provider_webhook_event",
            ),
        )

        for column in [
            "integration_id",
            "provider",
            "external_event_id",
            "event_type",
            "status",
            "received_at",
        ]:
            op.create_index(
                f"ix_ad_provider_webhook_events_{column}",
                "ad_provider_webhook_events",
                [column],
            )

        op.create_index(
            "ix_ad_provider_webhook_status",
            "ad_provider_webhook_events",
            ["provider", "status"],
        )


    if not has_table("ad_sync_runs"):
        op.create_table(
            "ad_sync_runs",

            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("integration_id", sa.String(36), nullable=True),
            sa.Column("provider", sa.String(40), nullable=False),
            sa.Column("sync_type", sa.String(40), nullable=False),
            sa.Column("status", sa.String(40), nullable=False, server_default="RUNNING"),
            sa.Column("accounts_scanned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("accounts_updated", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),

            sa.ForeignKeyConstraint(
                ["integration_id"],
                ["integration_configs.id"],
                ondelete="SET NULL",
            ),

            sa.PrimaryKeyConstraint("id"),
        )

        for column in [
            "integration_id",
            "provider",
            "sync_type",
            "status",
            "started_at",
            "finished_at",
        ]:
            op.create_index(
                f"ix_ad_sync_runs_{column}",
                "ad_sync_runs",
                [column],
            )

        op.create_index(
            "ix_ad_sync_provider_started",
            "ad_sync_runs",
            ["provider", "started_at"],
        )


def downgrade() -> None:

    tables = [
        "ad_sync_runs",
        "ad_provider_webhook_events",
        "ad_finance_transactions",
        "ad_topup_rules",
        "ad_account_product_maps",
        "ad_funding_accounts",
        "ad_accounts",
    ]

    for table in tables:
        if has_table(table):
            op.drop_table(table)
