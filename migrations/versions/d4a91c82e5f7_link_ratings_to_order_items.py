"""link ratings to completed purchased order items

Revision ID: d4a91c82e5f7
Revises: c3f271b8d40a
Create Date: 2026-10-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a91c82e5f7"
down_revision: Union[str, None] = "c3f271b8d40a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ratings", sa.Column("order_item_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ratings_order_item_id_order_items",
        "ratings",
        "order_items",
        ["order_item_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_ratings_order_item_id",
        "ratings",
        ["order_item_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_ratings_order_item_id", "ratings", type_="unique")
    op.drop_constraint(
        "fk_ratings_order_item_id_order_items",
        "ratings",
        type_="foreignkey",
    )
    op.drop_column("ratings", "order_item_id")
