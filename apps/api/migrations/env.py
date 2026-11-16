from alembic import context
from hub.database import Base, owner_engine
engine = owner_engine()
from hub import models, feature_models, ops_models, savings_models, agent_store, sync_models
with engine.connect() as connection:
    context.configure(connection=connection,target_metadata=Base.metadata,compare_type=True)
    with context.begin_transaction(): context.run_migrations()
