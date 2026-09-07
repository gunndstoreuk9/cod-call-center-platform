"""profit center product costs

Revision ID: 0004_profit_product_costs
Revises: 0003_full_delivery
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0004_profit_product_costs"
down_revision = "0003_full_delivery"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()

    return {
        column["name"]
        for column in inspect(bind).get_columns(table_name)
    }


def upgrade() -> None:
    bind = op.get_bind()

    # --------------------------------------------------------
    # PRODUCTS CURRENT COST
    # --------------------------------------------------------

    product_columns = _columns("products")

    if "unit_cost" not in product_columns:
        op.add_column(
            "products",
            sa.Column(
                "unit_cost",
                sa.Numeric(12, 2),
                nullable=False,
                server_default="0",
            ),
        )

    product_columns = _columns("products")

    if "packaging_cost" not in product_columns:
        op.add_column(
            "products",
            sa.Column(
                "packaging_cost",
                sa.Numeric(12, 2),
                nullable=False,
                server_default="0",
            ),
        )

    # --------------------------------------------------------
    # PRODUCT COST HISTORY
    # --------------------------------------------------------

    inspector = inspect(bind)

    if not inspector.has_table("product_cost_history"):
        op.create_table(
            "product_cost_history",

            sa.Column(
                "id",
                sa.String(length=36),
                nullable=False,
            ),

            sa.Column(
                "product_id",
                sa.String(length=36),
                nullable=False,
            ),

            sa.Column(
                "unit_cost",
                sa.Numeric(12, 2),
                nullable=False,
                server_default="0",
            ),

            sa.Column(
                "packaging_cost",
                sa.Numeric(12, 2),
                nullable=False,
                server_default="0",
            ),

            sa.Column(
                "effective_from",
                sa.DateTime(timezone=True),
                nullable=False,
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
        )

        op.create_index(
            "ix_product_cost_history_product_id",
            "product_cost_history",
            ["product_id"],
        )

        op.create_index(
            "ix_product_cost_history_effective_from",
            "product_cost_history",
            ["effective_from"],
        )

        op.create_index(
            "ix_product_cost_history_created_at",
            "product_cost_history",
            ["created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table("product_cost_history"):
        op.drop_table("product_cost_history")

    product_columns = _columns("products")

    if "packaging_cost" in product_columns:
        op.drop_column(
            "products",
            "packaging_cost"
        )

    product_columns = _columns("products")

    if "unit_cost" in product_columns:
        op.drop_column(
            "products",
            "unit_cost"
        )
