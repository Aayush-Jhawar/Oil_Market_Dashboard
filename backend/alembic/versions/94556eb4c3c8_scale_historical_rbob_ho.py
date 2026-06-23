"""scale_historical_rbob_ho

Revision ID: 94556eb4c3c8
Revises: adbe9131f9ef
Create Date: 2026-06-09 03:16:45.672402

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94556eb4c3c8'
down_revision: Union[str, Sequence[str], None] = 'adbe9131f9ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Scale RBOB and HO prices from $/gal to $/bbl."""
    # Scale values in the prices table
    op.execute('''
        UPDATE prices
        SET open = open * 42.0,
            high = high * 42.0,
            low = low * 42.0,
            close = close * 42.0
        WHERE symbol IN ('RBOB', 'HO') AND close < 10.0
    ''')

    # Scale values in the price_history table
    op.execute('''
        UPDATE price_history
        SET open = open * 42.0,
            high = high * 42.0,
            low = low * 42.0,
            close = close * 42.0
        WHERE symbol IN ('RBOB', 'HO') AND close < 10.0
    ''')


def downgrade() -> None:
    """Downgrade schema: Revert RBOB and HO prices to $/gal."""
    op.execute('''
        UPDATE prices
        SET open = open / 42.0,
            high = high / 42.0,
            low = low / 42.0,
            close = close / 42.0
        WHERE symbol IN ('RBOB', 'HO') AND close > 10.0
    ''')

    op.execute('''
        UPDATE price_history
        SET open = open / 42.0,
            high = high / 42.0,
            low = low / 42.0,
            close = close / 42.0
        WHERE symbol IN ('RBOB', 'HO') AND close > 10.0
    ''')
