"""Knowledge bases get an optional English name beside the Thai one."""
import sqlalchemy as sa
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
revision='0023'
down_revision='0022'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('knowledge_bases',sa.Column('name_en',sa.String(),nullable=False,server_default=''))
def downgrade():
    safe.drop_column('knowledge_bases','name_en')
