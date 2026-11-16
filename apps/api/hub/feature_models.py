"""Durable policies and jobs added without destructive changes to existing tables."""
from sqlalchemy import ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .models import Identity

class KBPolicy(Identity, Base):
    __tablename__='knowledge_base_policies'
    tenant_id: Mapped[str]=mapped_column(index=True)
    knowledge_base_id: Mapped[str]=mapped_column(ForeignKey('knowledge_bases.id'),unique=True)
    visibility: Mapped[str]=mapped_column(default='organization')
    readers: Mapped[list]=mapped_column(JSON,default=list)
    writers: Mapped[list]=mapped_column(JSON,default=list)

class DocumentState(Identity, Base):
    __tablename__='document_states'
    tenant_id: Mapped[str]=mapped_column(index=True)
    document_id: Mapped[str]=mapped_column(ForeignKey('documents.id'),unique=True)
    deleted_at: Mapped[str]=mapped_column(default='')

class DocumentVersion(Identity, Base):
    __tablename__='document_versions'
    tenant_id: Mapped[str]=mapped_column(index=True)
    document_id: Mapped[str]=mapped_column(ForeignKey('documents.id'),index=True)
    version: Mapped[int]
    name: Mapped[str]
    storage_key: Mapped[str]
    size: Mapped[int]
    sha256: Mapped[str]

class GenerationJob(Identity, Base):
    __tablename__='generation_jobs'
    tenant_id: Mapped[str]=mapped_column(index=True)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    model_id: Mapped[str]=mapped_column(ForeignKey('ai_models.id'))
    kind: Mapped[str]
    prompt: Mapped[str]=mapped_column(Text,default='')
    options: Mapped[dict]=mapped_column(JSON,default=dict)
    status: Mapped[str]=mapped_column(default='queued',index=True)
    progress: Mapped[int]=mapped_column(default=0)
    error: Mapped[str]=mapped_column(default='')
    input_key: Mapped[str]=mapped_column(default='')
    input_name: Mapped[str]=mapped_column(default='')
    output_key: Mapped[str]=mapped_column(default='')
    output_type: Mapped[str]=mapped_column(default='')
    output_text: Mapped[str]=mapped_column(Text,default='')
    provider_job_id: Mapped[str]=mapped_column(default='')
    cost: Mapped[float]=mapped_column(default=0)
    cost_known: Mapped[bool]=mapped_column(default=False)
    updated_at: Mapped[str]=mapped_column(default='')

class Setting(Identity, Base):
    __tablename__='settings'
    key: Mapped[str]=mapped_column(unique=True)
    value: Mapped[dict]=mapped_column(JSON,default=dict)

class UserPreference(Identity, Base):
    __tablename__='user_preferences'
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'),unique=True)
    value: Mapped[dict]=mapped_column(JSON,default=dict)

class ModelPolicy(Identity, Base):
    __tablename__='tenant_model_policies'
    tenant_id: Mapped[str]=mapped_column(ForeignKey('organizations.id'),unique=True)
    allowed_models: Mapped[list]=mapped_column(JSON,default=list)
    default_model: Mapped[str]=mapped_column(default='')
    monthly_budget: Mapped[float]=mapped_column(default=0)

class MessageFeedback(Identity, Base):
    __tablename__='message_feedback'
    tenant_id: Mapped[str]=mapped_column(index=True)
    message_id: Mapped[str]=mapped_column(ForeignKey('messages.id'),unique=True)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
    value: Mapped[str]
