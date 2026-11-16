"""Per-user monthly request quota (0 = unlimited)."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('users',sa.Column('monthly_quota',sa.Integer(),nullable=False,server_default='0'))
def downgrade():
    safe.drop_column('users','monthly_quota')
