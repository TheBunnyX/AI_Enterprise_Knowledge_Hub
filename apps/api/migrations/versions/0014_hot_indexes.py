"""Composite indexes for hot list queries (audit, usage, conversations)."""
from alembic import op
revision='0014'
down_revision='0013'
branch_labels=None
depends_on=None
IDX=[('ix_audit_tenant_created','audit_logs','tenant_id, created_at DESC'),('ix_usage_tenant_created','usage_events','tenant_id, created_at'),('ix_conv_user_created','conversations','user_id, created_at DESC')]
def upgrade():
    for n,t,c in IDX: op.execute(f'CREATE INDEX IF NOT EXISTS {n} ON {t} ({c})')
def downgrade():
    for n,_,_ in IDX: op.execute(f'DROP INDEX IF EXISTS {n}')
