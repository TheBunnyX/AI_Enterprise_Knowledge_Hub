"""Client IP on audit rows, sessions and the user's last sign-in."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0011'
down_revision='0010'
branch_labels=None
depends_on=None
def upgrade():
    for table,col in (('audit_logs','ip'),('sessions','ip'),('users','last_ip')):
        safe.add_column(table,sa.Column(col,sa.String(),nullable=False,server_default=''))
def downgrade():
    for table,col in (('audit_logs','ip'),('sessions','ip'),('users','last_ip')):
        safe.drop_column(table,col)
