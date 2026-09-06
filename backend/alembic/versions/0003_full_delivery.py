"""full delivery operations schema

Revision ID: 0003_full_delivery
Revises: 0002_integrations
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from app.core.db import Base
import app.models  # noqa: F401

revision = "0003_full_delivery"
down_revision = "0002_integrations"
branch_labels = None
depends_on = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    bind = op.get_bind()
    existing = {c["name"] for c in inspect(bind).get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing("delivery_shipments", sa.Column("integration_id", sa.String(length=36), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("external_reference", sa.String(length=180), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("barcode", sa.String(length=140), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("external_status_id", sa.Integer(), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("external_status_name", sa.String(length=180), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("cod_amount", sa.Numeric(12, 2), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("delivery_fee", sa.Numeric(12, 2), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("destination_city", sa.String(length=140), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("hub", sa.String(length=140), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("first_attempt_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("refused_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("delivery_shipments", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    _add_column_if_missing("delivery_shipments", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())
    for name in ["delivery_events", "delivery_status_mappings", "delivery_destinations", "delivery_sync_runs"]:
        if name not in existing_tables:
            Base.metadata.tables[name].create(bind=bind, checkfirst=True)

    # Foreign key/index creation is best-effort because SQLite test migrations have limited ALTER support.
    if bind.dialect.name != "sqlite":
        existing_fks = {fk.get("name") for fk in inspect(bind).get_foreign_keys("delivery_shipments")}
        if "fk_delivery_shipments_integration_id" not in existing_fks:
            op.create_foreign_key(
                "fk_delivery_shipments_integration_id", "delivery_shipments", "integration_configs",
                ["integration_id"], ["id"], ondelete="SET NULL"
            )
        existing_indexes = {ix.get("name") for ix in inspect(bind).get_indexes("delivery_shipments")}
        indexes = [
            ("ix_delivery_shipments_integration_id", ["integration_id"]),
            ("ix_delivery_shipments_external_reference", ["external_reference"]),
            ("ix_delivery_shipments_barcode", ["barcode"]),
            ("ix_delivery_shipments_external_status_id", ["external_status_id"]),
            ("ix_delivery_shipments_destination_city", ["destination_city"]),
            ("ix_delivery_shipments_hub", ["hub"]),
            ("ix_delivery_shipments_last_synced_at", ["last_synced_at"]),
            ("ix_delivery_provider_status", ["provider", "status"]),
        ]
        for name, cols in indexes:
            if name not in existing_indexes:
                op.create_index(name, "delivery_shipments", cols)


def downgrade() -> None:
    bind = op.get_bind()
    existing_tables = set(inspect(bind).get_table_names())
    for name in ["delivery_sync_runs", "delivery_destinations", "delivery_status_mappings", "delivery_events"]:
        if name in existing_tables:
            Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
    # Keep added shipment columns on downgrade to avoid data loss in production.
