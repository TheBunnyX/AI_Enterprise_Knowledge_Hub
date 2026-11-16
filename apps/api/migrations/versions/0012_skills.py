"""Skills: reusable AI instructions per user, optionally shared with the organization."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0012'
down_revision='0011'
branch_labels=None
depends_on=None
def upgrade():
    safe.create_table('skills',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('created_at',sa.String(),nullable=False),
        sa.Column('tenant_id',sa.String(),nullable=False,index=True),
        sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False,index=True),
        sa.Column('name',sa.String(),nullable=False),
        sa.Column('description',sa.String(),nullable=False,server_default=''),
        sa.Column('instructions',sa.Text(),nullable=False),
        sa.Column('icon',sa.String(),nullable=False,server_default='✨'),
        sa.Column('use_documents',sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column('shared',sa.Boolean(),nullable=False,server_default=sa.false()),
        sa.Column('uses',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('updated_at',sa.String(),nullable=False))
def downgrade():
    op.drop_table('skills')
