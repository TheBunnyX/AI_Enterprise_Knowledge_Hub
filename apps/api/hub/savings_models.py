"""Tables behind the cost controls: answer cache, embedding cache and savings events."""
from sqlalchemy import JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .models import Identity

class AnswerCache(Identity, Base):
    __tablename__ = 'answer_cache'
    tenant_id: Mapped[str] = mapped_column(index=True)
    cache_key: Mapped[str] = mapped_column(unique=True)
    question: Mapped[str] = mapped_column(Text, default='')
    answer: Mapped[str] = mapped_column(Text, default='')
    citations: Mapped[list] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(default='')
    cost: Mapped[float] = mapped_column(default=0)
    hits: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[str] = mapped_column(default='')

class EmbeddingCache(Identity, Base):
    __tablename__ = 'embedding_cache'
    cache_key: Mapped[str] = mapped_column(unique=True)
    vector: Mapped[list] = mapped_column(JSON, default=list)

class SavingsEvent(Identity, Base):
    __tablename__ = 'savings_events'
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(default='')
    kind: Mapped[str] = mapped_column(index=True)  # cache_hit | embedding_hit | route
    saved: Mapped[float] = mapped_column(default=0)
    detail: Mapped[str] = mapped_column(default='')
