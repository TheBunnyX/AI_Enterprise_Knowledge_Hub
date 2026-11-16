"""Provider rate limits (requests/minute, tokens/minute, requests/day; 0 = unknown) per model."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0008'
down_revision='0007'
branch_labels=None
depends_on=None
def upgrade():
    for name in ('rpm','tpm','rpd'):safe.add_column('ai_models',sa.Column(name,sa.Integer(),nullable=False,server_default='0'))
def downgrade():
    for name in ('rpm','tpm','rpd'):safe.drop_column('ai_models',name)
