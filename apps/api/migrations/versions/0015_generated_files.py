"""Files created by the chat agent (pptx/xlsx/csv), private to the requesting user."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0015'
down_revision='0014'
branch_labels=None
depends_on=None
def upgrade():
    safe.create_table('generated_files',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('created_at',sa.String(),nullable=False),
        sa.Column('tenant_id',sa.String(),nullable=False,index=True),
        sa.Column('user_id',sa.String(),nullable=False,index=True),
        sa.Column('conversation_id',sa.String(),nullable=False,server_default=''),
        sa.Column('name',sa.String(),nullable=False),
        sa.Column('kind',sa.String(),nullable=False),
        sa.Column('size',sa.Integer(),nullable=False),
        sa.Column('storage_key',sa.String(),nullable=False),
        sa.Column('expires_at',sa.String(),nullable=False))
def downgrade():
    op.drop_table('generated_files')
