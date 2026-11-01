"""unique Google Sheets external order id per store

Revision ID: 0007_gsheets_external_id_unique
Revises: 0006_ads_finance_foundation
Create Date: 2026-11-01

Non-destructive: only adds a partial unique index. Verified on production data first (0 existing duplicates).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0007_gsheets_external_id_unique"
down_revision = "0006_ads_finance_foundation"
branch_labels = None
depends_on = None

INDEX = "uq_orders_gsheets_ext"


def upgrade() -> None:
    bind = op.get_bind()
    if any(ix["name"] == INDEX for ix in inspect(bind).get_indexes("orders")):
        return
    op.create_index(
        INDEX, "orders", ["store_id", "external_order_id"], unique=True,
        postgresql_where=sa.text("source = 'GOOGLE_SHEETS' AND external_order_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="orders")
