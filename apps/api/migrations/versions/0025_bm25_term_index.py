"""BM25 term index: an inverted index in PostgreSQL, so searching no longer reads every chunk into memory."""
import sqlalchemy as sa
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
revision='0025'
down_revision='0024'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('document_chunks',sa.Column('length',sa.Integer(),nullable=False,server_default='-1'))
    safe.create_table('chunk_terms',
        sa.Column('chunk_id',sa.String(36),sa.ForeignKey('document_chunks.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('term',sa.String(),primary_key=True),
        sa.Column('tenant_id',sa.String(),nullable=False),
        sa.Column('document_id',sa.String(),nullable=False),
        sa.Column('tf',sa.Integer(),nullable=False))
    safe.create_index('ix_chunk_terms_tenant_term','chunk_terms',['tenant_id','term'])
    safe.create_index('ix_chunk_terms_document_id','chunk_terms',['document_id'])
    safe.create_index('ix_chunk_terms_tenant_id','chunk_terms',['tenant_id'])
    # the terms of existing chunks are built by `python -m hub.terms` (run on every start, resumable)
def downgrade():
    from alembic import op
    if safe.has_table('chunk_terms'): op.drop_table('chunk_terms')
    safe.drop_column('document_chunks','length')
