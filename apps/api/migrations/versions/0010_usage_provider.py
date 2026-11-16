"""Provider on usage events, for per-provider rate-limit counters."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0010'
down_revision='0009'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('usage_events',sa.Column('provider',sa.String(),nullable=False,server_default=''))
def downgrade():
    safe.drop_column('usage_events','provider')
