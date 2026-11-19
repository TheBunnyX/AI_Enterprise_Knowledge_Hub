"""A user's budget can be set per day, week or month."""
import sqlalchemy as sa
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
revision='0024'
down_revision='0023'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('users',sa.Column('budget_period',sa.String(),nullable=False,server_default='month'))
def downgrade():
    safe.drop_column('users','budget_period')
