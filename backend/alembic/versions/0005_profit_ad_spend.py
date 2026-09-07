"""profit center ad spend

Revision ID: 0005_profit_ad_spend
Revises: 0004_profit_product_costs
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0005_profit_ad_spend"
down_revision = "0004_profit_product_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    if inspect(bind).has_table("ad_spend"):
        return

    op.create_table(
        "ad_spend",

        sa.Column(
            "id",
            sa.String(length=36),
            nullable=False,
        ),

        sa.Column(
            "store_id",
            sa.String(length=36),
            nullable=False,
        ),

        sa.Column(
            "product_id",
            sa.String(length=36),
            nullable=False,
        ),

        sa.Column(
            "spend_date",
            sa.Date(),
            nullable=False,
        ),

        sa.Column(
            "amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="MAD",
        ),

        sa.Column(
            "platform",
            sa.String(length=40),
            nullable=False,
            server_default="META",
        ),

        sa.Column(
            "campaign_name",
            sa.String(length=180),
            nullable=True,
        ),

        sa.Column(
            "note",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_ad_spend_store_id",
        "ad_spend",
        ["store_id"],
    )

    op.create_index(
        "ix_ad_spend_product_id",
        "ad_spend",
        ["product_id"],
    )

    op.create_index(
        "ix_ad_spend_spend_date",
        "ad_spend",
        ["spend_date"],
    )

    op.create_index(
        "ix_ad_spend_platform",
        "ad_spend",
        ["platform"],
    )

    op.create_index(
        "ix_ad_spend_created_at",
        "ad_spend",
        ["created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    if inspect(bind).has_table("ad_spend"):
        op.drop_table("ad_spend")
