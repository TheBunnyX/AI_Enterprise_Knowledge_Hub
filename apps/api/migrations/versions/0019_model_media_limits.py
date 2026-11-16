"""Per-model limits on the options users may pick when generating images and videos (resolution, aspect ratio, duration)."""
import sqlalchemy as sa
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
revision='0019'
down_revision='0018'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('ai_models',sa.Column('media_limits',sa.JSON(),nullable=False,server_default='{}'))
def downgrade():
    safe.drop_column('ai_models','media_limits')
