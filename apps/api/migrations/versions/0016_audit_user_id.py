"""Audit rows carry the acting user's id, so a user's own log is selected by id instead of by display name.

Older rows are attributed only when exactly one account in the tenant has that name (or the actor column already held an id);
anything ambiguous stays unattributed and is visible to Super Admins only.
"""
from alembic import op
import sqlalchemy as sa
revision='0016'
down_revision='0015'
branch_labels=None
depends_on=None
def upgrade():
    # 0001 creates tables from the current models, so on a database created after this change the column already exists.
    if 'user_id' not in {c['name'] for c in sa.inspect(op.get_bind()).get_columns('audit_logs')}:
        op.add_column('audit_logs',sa.Column('user_id',sa.String(),nullable=False,server_default=''))
    op.execute('CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)')
    op.execute("UPDATE audit_logs SET user_id=actor WHERE user_id='' AND EXISTS (SELECT 1 FROM users u WHERE u.id=audit_logs.actor AND u.tenant_id=audit_logs.tenant_id)")
    op.execute("UPDATE audit_logs SET user_id=(SELECT u.id FROM users u WHERE u.tenant_id=audit_logs.tenant_id AND u.name=audit_logs.actor) "
               "WHERE user_id='' AND (SELECT count(*) FROM users u WHERE u.tenant_id=audit_logs.tenant_id AND u.name=audit_logs.actor)=1")
def downgrade():
    op.execute('DROP INDEX IF EXISTS ix_audit_logs_user_id')
    op.drop_column('audit_logs','user_id')
