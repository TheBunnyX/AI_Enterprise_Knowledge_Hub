"""Per-user monthly budget in USD (0 = unlimited), replacing the request-count quota."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('users',sa.Column('monthly_budget',sa.Float(),nullable=False,server_default='0'))
    safe.drop_column('users','monthly_quota')
def downgrade():
    safe.add_column('users',sa.Column('monthly_quota',sa.Integer(),nullable=False,server_default='0'))
    safe.drop_column('users','monthly_budget')
