from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, ForeignKey, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .clientip import ip_default

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc).isoformat()

class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[str] = mapped_column(default=now)

class Organization(Identity, Base):
    __tablename__ = 'organizations'
    name: Mapped[str]
    plan: Mapped[str] = mapped_column(default='Business')
    status: Mapped[str] = mapped_column(default='active')
    quota: Mapped[int] = mapped_column(default=10000)

class User(Identity, Base):
    __tablename__ = 'users'
    tenant_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    name_en: Mapped[str] = mapped_column(default='', server_default='')  # optional English name beside the Thai one
    password_hash: Mapped[str]
    role: Mapped[str] = mapped_column(default='USER')
    active: Mapped[bool] = mapped_column(default=True)
    monthly_budget: Mapped[float] = mapped_column(default=0, server_default='0')  # the user's budget in USD for one budget_period (name kept from when it was monthly only)
    budget_period: Mapped[str] = mapped_column(default='month', server_default='month')  # 'day' | 'week' | 'month', counted in UTC
    last_seen: Mapped[float] = mapped_column(default=0, server_default='0')  # epoch seconds of the last authenticated request
    last_ip: Mapped[str] = mapped_column(default='', server_default='')  # address of the most recent sign-in

class LoginSession(Identity, Base):
    __tablename__ = 'sessions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    expires: Mapped[float]
    token_hash: Mapped[str] = mapped_column(unique=True)
    ip: Mapped[str] = mapped_column(default=ip_default, server_default='')

class OIDCState(Identity, Base):
    __tablename__ = 'oidc_states'
    state_hash: Mapped[str] = mapped_column(unique=True)
    verifier: Mapped[str]
    nonce: Mapped[str]
    expires: Mapped[float]

class KnowledgeBase(Identity, Base):
    __tablename__ = 'knowledge_bases'
    tenant_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str]
    name_en: Mapped[str] = mapped_column(default='', server_default='')  # optional English name beside the Thai one
    description: Mapped[str] = mapped_column(default='')
    multimodal: Mapped[bool] = mapped_column(default=False, server_default='false')  # Multimodal RAG for this library: pictures in its documents are described and embedded (sent to Google AI)
    department_id: Mapped[str] = mapped_column(default='', server_default='', index=True)  # the department (access group of kind 'department') that owns and manages it; '' = the organisation

class Document(Identity, Base):
    __tablename__ = 'documents'
    __table_args__ = (UniqueConstraint('tenant_id', 'sha256'),)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey('knowledge_bases.id'), index=True)
    name: Mapped[str]
    sha256: Mapped[str]
    size: Mapped[int]
    storage_key: Mapped[str]
    status: Mapped[str] = mapped_column(default='processing')
    error: Mapped[str] = mapped_column(default='')
    version: Mapped[int] = mapped_column(default=1)
    name_en: Mapped[str] = mapped_column(default='', server_default='')  # optional English display name; `name` stays the real file name (its extension decides how it is read)

class Chunk(Identity, Base):
    __tablename__ = 'document_chunks'
    tenant_id: Mapped[str] = mapped_column(index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id'), index=True)
    page: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    embedding_version: Mapped[str] = mapped_column(default='hash-ngram-v1-256')
    kind: Mapped[str] = mapped_column(default='text', server_default='text')  # 'text', or 'image': a picture whose text is a vision-model description
    image_key: Mapped[str] = mapped_column(default='', server_default='')  # object-storage key of the picture (kind='image')
    mm_embedding: Mapped[list] = mapped_column(JSON, default=list, server_default='[]')  # multimodal vector of the picture itself
    length: Mapped[int] = mapped_column(default=-1, server_default='-1')  # number of lexical tokens (text + document name) for BM25; -1 = term index not built yet

class ChunkTerm(Base):
    """Inverted index for BM25: how often a lexical token occurs in a chunk. Rows go away with their chunk."""
    __tablename__ = 'chunk_terms'
    chunk_id: Mapped[str] = mapped_column(ForeignKey('document_chunks.id', ondelete='CASCADE'), primary_key=True)
    term: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(index=True)
    document_id: Mapped[str] = mapped_column(index=True)
    tf: Mapped[int]
    __table_args__ = (Index('ix_chunk_terms_tenant_term', 'tenant_id', 'term'),)

class Conversation(Identity, Base):
    __tablename__ = 'conversations'
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    title: Mapped[str]

class Message(Identity, Base):
    __tablename__ = 'messages'
    tenant_id: Mapped[str] = mapped_column(index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)

class AIModel(Identity, Base):
    __tablename__ = 'ai_models'
    name: Mapped[str]
    provider: Mapped[str]
    api_id: Mapped[str]
    category: Mapped[str] = mapped_column(default='LLM')
    enabled: Mapped[bool] = mapped_column(default=False)
    input_price: Mapped[float] = mapped_column(default=0)
    output_price: Mapped[float] = mapped_column(default=0)
    rpm: Mapped[int] = mapped_column(default=0)  # provider limits shown to admins and users; 0 = unknown/unlimited
    tpm: Mapped[int] = mapped_column(default=0)
    rpd: Mapped[int] = mapped_column(default=0)
    effort: Mapped[str] = mapped_column(default='', server_default='')  # reasoning effort sent to the provider; '' = provider default
    media_limits: Mapped[dict] = mapped_column(JSON, default=dict, server_default='{}')  # Image/Video: the options users may pick, {'resolutions':[..],'aspect_ratios':[..],'durations':[..]}; a missing or empty list = everything the model offers

class Usage(Identity, Base):
    __tablename__ = 'usage_events'
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(index=True)
    model: Mapped[str]
    provider: Mapped[str] = mapped_column(default='', server_default='')  # which provider answered, for per-provider rate-limit counters
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost: Mapped[float] = mapped_column(default=0)
    estimated: Mapped[bool] = mapped_column(default=True)

class Audit(Identity, Base):
    __tablename__ = 'audit_logs'
    tenant_id: Mapped[str] = mapped_column(index=True)
    user_id: Mapped[str] = mapped_column(default='', server_default='', index=True)  # who did it; rows are shown to their owner by this id, never by the display name
    actor: Mapped[str]
    action: Mapped[str]
    detail: Mapped[str] = mapped_column(default='')
    ip: Mapped[str] = mapped_column(default=ip_default, server_default='')
