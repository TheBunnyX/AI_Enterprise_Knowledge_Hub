"""Where a paused agent run lives: the hub's own database, so a run survives restarts and follows the same tenant
isolation (row-level security) and backups as everything else.

- AgentRun         one row per run that is waiting for a person: whose it is, what it is waiting for, when it expires
- AgentCheckpoint  LangGraph's saved graph state for that run (the conversation so far, tool results, counters)
- AgentWrite       LangGraph's pending writes of the interrupted step

DbSaver is the LangGraph checkpoint saver over these tables. Rows are removed when the run finishes; a run nobody
answers is removed by hub.cleanup after it expires.
"""
import asyncio, time
from sqlalchemy import JSON, LargeBinary, delete, select
from sqlalchemy.orm import Mapped, mapped_column
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP, get_checkpoint_id, get_checkpoint_metadata
from .database import Base, SessionLocal, scope_to_tenant
from .models import Identity

PAUSE_HOURS = 24  # how long a run waits for the person before it is dropped


class AgentRun(Identity, Base):
    """id = the LangGraph thread id."""
    __tablename__ = 'agent_runs'
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(index=True)
    conversation_id: Mapped[str] = mapped_column(index=True)
    pending: Mapped[dict] = mapped_column(JSON, default=dict)  # what the person is asked: {kind: question|approval, ...}
    input_tokens: Mapped[int] = mapped_column(default=0)  # already metered when the run paused
    output_tokens: Mapped[int] = mapped_column(default=0)
    expires: Mapped[float] = mapped_column(default=0)


class AgentCheckpoint(Base):
    __tablename__ = 'agent_checkpoints'
    thread_id: Mapped[str] = mapped_column(primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(primary_key=True, default='')
    checkpoint_id: Mapped[str] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(index=True)
    parent_id: Mapped[str] = mapped_column(default='')
    kind: Mapped[str]
    data: Mapped[bytes] = mapped_column(LargeBinary)
    metadata_kind: Mapped[str]
    metadata_data: Mapped[bytes] = mapped_column(LargeBinary)


class AgentWrite(Base):
    __tablename__ = 'agent_checkpoint_writes'
    thread_id: Mapped[str] = mapped_column(primary_key=True)
    checkpoint_ns: Mapped[str] = mapped_column(primary_key=True, default='')
    checkpoint_id: Mapped[str] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(primary_key=True)
    idx: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(index=True)
    channel: Mapped[str]
    kind: Mapped[str]
    data: Mapped[bytes] = mapped_column(LargeBinary)
    task_path: Mapped[str] = mapped_column(default='')


def _session(config):
    """A session bound to the run's tenant, so PostgreSQL row-level security applies to checkpoints too."""
    db = SessionLocal(); tenant = config['configurable'].get('tenant_id') or ''
    if tenant: scope_to_tenant(db, tenant)
    return db, tenant


class DbSaver(BaseCheckpointSaver):
    """LangGraph checkpoint saver on the hub database. Each checkpoint is stored whole (state included)."""

    def _tuple(self, db, row):
        writes = db.scalars(select(AgentWrite).where(AgentWrite.thread_id == row.thread_id, AgentWrite.checkpoint_ns == row.checkpoint_ns,
                                                    AgentWrite.checkpoint_id == row.checkpoint_id).order_by(AgentWrite.task_id, AgentWrite.idx)).all()
        where = {'thread_id': row.thread_id, 'checkpoint_ns': row.checkpoint_ns}
        return CheckpointTuple(config={'configurable': {**where, 'checkpoint_id': row.checkpoint_id}},
                               checkpoint=self.serde.loads_typed((row.kind, row.data)), metadata=self.serde.loads_typed((row.metadata_kind, row.metadata_data)),
                               parent_config={'configurable': {**where, 'checkpoint_id': row.parent_id}} if row.parent_id else None,
                               pending_writes=[(w.task_id, w.channel, self.serde.loads_typed((w.kind, w.data))) for w in writes])

    def get_tuple(self, config):
        db, _ = _session(config)
        try:
            c = config['configurable']
            stmt = select(AgentCheckpoint).where(AgentCheckpoint.thread_id == c['thread_id'], AgentCheckpoint.checkpoint_ns == c.get('checkpoint_ns', ''))
            wanted = get_checkpoint_id(config)
            stmt = stmt.where(AgentCheckpoint.checkpoint_id == wanted) if wanted else stmt.order_by(AgentCheckpoint.checkpoint_id.desc()).limit(1)
            row = db.scalar(stmt)
            return self._tuple(db, row) if row else None
        finally: db.close()

    def list(self, config, *, filter=None, before=None, limit=None):
        if config is None: return
        db, _ = _session(config)
        try:
            c = config['configurable']
            stmt = select(AgentCheckpoint).where(AgentCheckpoint.thread_id == c['thread_id'], AgentCheckpoint.checkpoint_ns == c.get('checkpoint_ns', '')).order_by(AgentCheckpoint.checkpoint_id.desc())
            if before and get_checkpoint_id(before): stmt = stmt.where(AgentCheckpoint.checkpoint_id < get_checkpoint_id(before))
            if limit: stmt = stmt.limit(limit)
            found = [self._tuple(db, row) for row in db.scalars(stmt)]
        finally: db.close()
        yield from found

    def put(self, config, checkpoint, metadata, new_versions):
        db, tenant = _session(config)
        try:
            c = config['configurable']; where = {'thread_id': c['thread_id'], 'checkpoint_ns': c.get('checkpoint_ns', '')}
            kind, data = self.serde.dumps_typed(checkpoint); metadata_kind, metadata_data = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))
            db.merge(AgentCheckpoint(**where, checkpoint_id=checkpoint['id'], tenant_id=tenant, parent_id=c.get('checkpoint_id') or '',
                                     kind=kind, data=data, metadata_kind=metadata_kind, metadata_data=metadata_data))
            db.commit()
            return {'configurable': {**where, 'checkpoint_id': checkpoint['id']}}
        finally: db.close()

    def put_writes(self, config, writes, task_id, task_path=''):
        db, tenant = _session(config)
        try:
            c = config['configurable']; where = {'thread_id': c['thread_id'], 'checkpoint_ns': c.get('checkpoint_ns', ''), 'checkpoint_id': c['checkpoint_id'], 'task_id': task_id}
            for position, (channel, value) in enumerate(writes):
                idx = WRITES_IDX_MAP.get(channel, position)
                if idx >= 0 and db.get(AgentWrite, {**where, 'idx': idx}): continue  # a regular write is kept; special ones (errors, interrupts) are replaced
                kind, data = self.serde.dumps_typed(value)
                db.merge(AgentWrite(**where, idx=idx, tenant_id=tenant, channel=channel, kind=kind, data=data, task_path=task_path))
            db.commit()
        finally: db.close()

    def delete_thread(self, thread_id):
        forget(thread_id)

    async def aget_tuple(self, config): return await asyncio.to_thread(self.get_tuple, config)
    async def aput(self, config, checkpoint, metadata, new_versions): return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)
    async def aput_writes(self, config, writes, task_id, task_path=''): return await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)
    async def adelete_thread(self, thread_id): return await asyncio.to_thread(self.delete_thread, thread_id)
    async def alist(self, config, *, filter=None, before=None, limit=None):
        for item in await asyncio.to_thread(lambda: list(self.list(config, filter=filter, before=before, limit=limit))): yield item


def forget(thread_id, db=None):
    """Remove a run and everything saved for it."""
    own = db is None; db = db or SessionLocal()
    try:
        for table in (AgentWrite, AgentCheckpoint): db.execute(delete(table).where(table.thread_id == thread_id))
        db.execute(delete(AgentRun).where(AgentRun.id == thread_id)); db.commit()
    finally:
        if own: db.close()


def remember(thread_id, tenant_id, user_id, conversation_id, pending, input_tokens, output_tokens):
    """Record that a run is waiting for its user. One conversation waits for one thing at a time."""
    with SessionLocal() as db:
        for old in db.scalars(select(AgentRun.id).where(AgentRun.user_id == user_id, AgentRun.conversation_id == conversation_id, AgentRun.id != thread_id)).all(): forget(old, db)
        run = db.get(AgentRun, thread_id) or AgentRun(id=thread_id, tenant_id=tenant_id, user_id=user_id, conversation_id=conversation_id)
        run.pending = pending; run.input_tokens = input_tokens; run.output_tokens = output_tokens; run.expires = time.time() + PAUSE_HOURS * 3600
        db.add(run); db.commit()


def waiting(db, user, conversation_id):
    """The run of this user's conversation that is waiting for them, if any."""
    return db.scalar(select(AgentRun).where(AgentRun.tenant_id == user.tenant_id, AgentRun.user_id == user.id, AgentRun.conversation_id == conversation_id, AgentRun.expires > time.time()))


def purge_expired():
    with SessionLocal() as db:
        ids = list(db.scalars(select(AgentRun.id).where(AgentRun.expires <= time.time())))
        for id in ids: forget(id, db)
    return len(ids)
