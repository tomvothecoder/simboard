"""Seed status lookup table

Revision ID: d666c49ea3bd
Revises: 708f26079ad0
Create Date: 2025-10-07 10:26:37.112566

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d666c49ea3bd"
down_revision: Union[str, Sequence[str], None] = "708f26079ad0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute(
        sa.text(
            """
            INSERT INTO status_lookup (code, label) VALUES
              ('created','Created'),
              ('queued','Queued'),
              ('running','Running'),
              ('failed','Failed'),
              ('completed','Completed')
            ON CONFLICT (code) DO NOTHING;
            """
        )
    )


def downgrade():
    op.execute(
        sa.text(
            "DELETE FROM status_lookup WHERE code IN ('created','queued','running','failed','completed');"
        )
    )
