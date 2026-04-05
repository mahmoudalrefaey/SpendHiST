"""Index receipt_items.receipt_id for join performance.

Revision ID: 001_ix_receipt_items_receipt_id
Revises:
Create Date: 2026-04-05

"""

from typing import Sequence, Union

from alembic import op

revision: str = "001_ix_receipt_items_receipt_id"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_receipt_items_receipt_id",
        "receipt_items",
        ["receipt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_receipt_items_receipt_id", table_name="receipt_items")
