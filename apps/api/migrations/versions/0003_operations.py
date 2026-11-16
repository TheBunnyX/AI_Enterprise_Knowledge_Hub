"""Non-destructive operations, group/document ACL, sharing and recovery records."""
from alembic import op
from hub.database import Base
from hub import ops_models
revision='0003'
down_revision='0002'
branch_labels=None
depends_on=None
TABLES=['access_groups','group_members','resource_policies','conversation_shares','task_runs','system_alerts','alert_reads','backups']
def upgrade():
    for name in TABLES:Base.metadata.tables[name].create(op.get_bind(),checkfirst=True)
def downgrade():
    for name in reversed(TABLES):Base.metadata.tables[name].drop(op.get_bind(),checkfirst=True)
