"""add optional purchased variant to product ratings

Revision ID: c3f271b8d40a
Revises: 7f5a1c2d9e44
Create Date: 2026-10-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3f271b8d40a"
down_revision: Union[str, None] = "7f5a1c2d9e44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("ratings", sa.Column("variant_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ratings_variant_id_pack_types",
        "ratings",
        "pack_types",
        ["variant_id"],
        ["id"],
    )
    op.create_index("ix_ratings_variant_id", "ratings", ["variant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ratings_variant_id", table_name="ratings")
    op.drop_constraint("fk_ratings_variant_id_pack_types", "ratings", type_="foreignkey")
    op.drop_column("ratings", "variant_id")
