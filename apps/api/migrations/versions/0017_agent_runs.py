"""Paused agent runs: what a run waits for from its user, and LangGraph's saved state for it (see hub.agent_store)."""
from alembic import op
from hub.database import Base
from hub import agent_store
revision='0017'
down_revision='0016'
branch_labels=None
depends_on=None
TABLES=['agent_runs','agent_checkpoints','agent_checkpoint_writes']
def upgrade():
    for name in TABLES:Base.metadata.tables[name].create(op.get_bind(),checkfirst=True)
def downgrade():
    for name in reversed(TABLES):Base.metadata.tables[name].drop(op.get_bind(),checkfirst=True)
