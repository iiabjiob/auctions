"""add lot search text trigram index

Revision ID: 202605090002
Revises: 202605090001
Create Date: 2026-05-09

"""
from typing import Sequence, Union

from alembic import op


revision: str = "202605090002"
down_revision: Union[str, None] = "202605090001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_search_text_trgm
            ON auction_lot_records
            USING gin (lower(search_text) gin_trgm_ops)
            """
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_search_text_trgm")
