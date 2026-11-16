"""Answer cache, embedding cache and savings events."""
from alembic import op
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
import sqlalchemy as sa
revision='0007'
down_revision='0006'
branch_labels=None
depends_on=None
def base():
    return [sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.String(),nullable=False)]
def upgrade():
    safe.create_table('answer_cache',*base(),sa.Column('tenant_id',sa.String(),nullable=False),sa.Column('cache_key',sa.String(),nullable=False,unique=True),sa.Column('question',sa.Text(),nullable=False),sa.Column('answer',sa.Text(),nullable=False),sa.Column('citations',sa.JSON(),nullable=False),sa.Column('model',sa.String(),nullable=False),sa.Column('cost',sa.Float(),nullable=False),sa.Column('hits',sa.Integer(),nullable=False),sa.Column('expires_at',sa.String(),nullable=False))
    safe.create_index('ix_answer_cache_tenant_id','answer_cache',['tenant_id'])
    safe.create_table('embedding_cache',*base(),sa.Column('cache_key',sa.String(),nullable=False,unique=True),sa.Column('vector',sa.JSON(),nullable=False))
    safe.create_table('savings_events',*base(),sa.Column('tenant_id',sa.String(),nullable=False),sa.Column('user_id',sa.String(),nullable=False),sa.Column('kind',sa.String(),nullable=False),sa.Column('saved',sa.Float(),nullable=False),sa.Column('detail',sa.String(),nullable=False))
    safe.create_index('ix_savings_events_tenant_id','savings_events',['tenant_id'])
    safe.create_index('ix_savings_events_kind','savings_events',['kind'])
def downgrade():
    op.drop_table('savings_events');op.drop_table('embedding_cache');op.drop_table('answer_cache')
