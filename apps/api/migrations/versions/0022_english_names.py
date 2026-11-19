"""Documents, departments and users get an optional English name beside the Thai one, editable by the people who manage them."""
import sqlalchemy as sa
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
revision='0022'
down_revision='0021'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('documents',sa.Column('name_en',sa.String(),nullable=False,server_default=''))
    safe.add_column('users',sa.Column('name_en',sa.String(),nullable=False,server_default=''))
    safe.add_column('access_groups',sa.Column('name_en',sa.String(),nullable=False,server_default=''))
def downgrade():
    safe.drop_column('users','name_en')
    safe.drop_column('access_groups','name_en')
    safe.drop_column('documents','name_en')
