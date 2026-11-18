"""Multimodal RAG: picture chunks (description text, stored image, image embedding) next to text chunks."""
import sqlalchemy as sa
from hub import migration_helpers as safe  # repeatable: 0001 already creates the current schema on a new database
revision='0020'
down_revision='0019'
branch_labels=None
depends_on=None
def upgrade():
    safe.add_column('document_chunks',sa.Column('kind',sa.String(),nullable=False,server_default='text'))
    safe.add_column('document_chunks',sa.Column('image_key',sa.String(),nullable=False,server_default=''))
    safe.add_column('document_chunks',sa.Column('mm_embedding',sa.JSON(),nullable=False,server_default='[]'))
def downgrade():
    for column in ('mm_embedding','image_key','kind'):safe.drop_column('document_chunks',column)
