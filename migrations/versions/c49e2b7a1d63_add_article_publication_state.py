"""add reversible article publication state

Revision ID: c49e2b7a1d63
Revises: 7f5a1c2d9e44
Create Date: 2026-10-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c49e2b7a1d63"
down_revision: Union[str, None] = "7f5a1c2d9e44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "articles",
        sa.Column("is_published", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.execute(
        """
        UPDATE articles
        SET is_published = FALSE
        WHERE title IN (
            'Informasi Terbaru Akan Segera Hadir',
            'Informasi Terbaru Akan Segera Hadir !!!'
        )
        AND (
            description ILIKE '%halaman informasi terbaru saat ini belum tersedia%'
            OR description ILIKE '%sedang dalam proses pembaruan%'
        )
        """
    )


def downgrade() -> None:
    op.drop_column("articles", "is_published")
