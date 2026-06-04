"""Remove case-level reference simulation column.

Revision ID: 20260603_120000
Revises: 20260601_112110_e1a37fccb0f7
Create Date: 2026-06-03 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260603_120000"
down_revision: Union[str, Sequence[str], None] = "e1a37fccb0f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_cases_reference_sim", "cases", type_="foreignkey")
    op.drop_column("cases", "reference_simulation_id")


def downgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "reference_simulation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_cases_reference_sim",
        "cases",
        "simulations",
        ["reference_simulation_id"],
        ["id"],
    )
