"""integration configs and events

Revision ID: 0002_integrations
Revises: 0001_initial
Create Date: 2026-09-05
"""
from alembic import op
from sqlalchemy import inspect
from app.core.db import Base
import app.models  # noqa: F401

revision = "0002_integrations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    wanted = [Base.metadata.tables["integration_configs"], Base.metadata.tables["integration_events"]]
    for table in wanted:
        if table.name not in existing:
            table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    for name in ["integration_events", "integration_configs"]:
        if name in existing:
            Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
