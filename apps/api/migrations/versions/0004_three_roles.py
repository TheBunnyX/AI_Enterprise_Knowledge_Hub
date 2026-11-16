"""Collapse roles to SUPER_ADMIN, DEPARTMENT_ADMIN and USER."""
from alembic import op
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None
def upgrade():
    op.execute("UPDATE users SET role='DEPARTMENT_ADMIN' WHERE role IN ('TENANT_ADMIN','KNOWLEDGE_MANAGER')")
    op.execute("UPDATE users SET role='USER' WHERE role IN ('MEMBER','VIEWER')")
def downgrade():
    op.execute("UPDATE users SET role='KNOWLEDGE_MANAGER' WHERE role='DEPARTMENT_ADMIN'")
    op.execute("UPDATE users SET role='MEMBER' WHERE role='USER'")
