"""Add policies, media jobs, preferences and document history; preserve existing records."""
from alembic import op
from hub.database import Base
from hub import feature_models
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None
TABLES=['knowledge_base_policies','document_states','document_versions','generation_jobs','settings','user_preferences','tenant_model_policies','message_feedback']
def upgrade():
    for name in TABLES:Base.metadata.tables[name].create(op.get_bind(),checkfirst=True)
def downgrade():
    for name in reversed(TABLES):Base.metadata.tables[name].drop(op.get_bind(),checkfirst=True)
