"""Knowledge bases belong to a department, and can mirror files from the web (automatic sync).

Existing knowledge bases keep department_id = '' (the organisation's): Super Admins and, as before, department admins manage them
until a Super Admin assigns each one to a department.
"""
import sqlalchemy as sa
from hub import migration_helpers as safe
from hub.database import Base
from hub import sync_models  # noqa: F401 - registers kb_sources
revision='0018'
down_revision='0017'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('knowledge_bases',sa.Column('department_id',sa.String(),nullable=False,server_default=''))
    safe.create_index('ix_knowledge_bases_department_id','knowledge_bases',['department_id'])
    from alembic import op
    Base.metadata.tables['kb_sources'].create(op.get_bind(),checkfirst=True)
def downgrade():
    from alembic import op
    Base.metadata.tables['kb_sources'].drop(op.get_bind(),checkfirst=True)
    op.drop_index('ix_knowledge_bases_department_id','knowledge_bases')
    op.drop_column('knowledge_bases','department_id')
