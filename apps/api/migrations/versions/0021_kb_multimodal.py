"""Multimodal RAG is opt-in per knowledge base: only libraries with charts and diagrams pay for picture indexing."""
import sqlalchemy as sa
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
revision='0021'
down_revision='0020'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('knowledge_bases',sa.Column('multimodal',sa.Boolean(),nullable=False,server_default=sa.false()))
def downgrade():
    safe.drop_column('knowledge_bases','multimodal')
