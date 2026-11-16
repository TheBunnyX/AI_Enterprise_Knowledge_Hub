"""Reasoning effort per model."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0013'
down_revision='0012'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('ai_models',sa.Column('effort',sa.String(),nullable=False,server_default=''))
def downgrade():
    safe.drop_column('ai_models','effort')
