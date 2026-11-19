from sqlalchemy import ForeignKey, JSON, Text, UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .database import Base
from .models import Identity

class Group(Identity,Base):
    __tablename__='access_groups'
    __table_args__=(UniqueConstraint('tenant_id','name'),)
    tenant_id:Mapped[str]=mapped_column(index=True)
    name:Mapped[str]
    kind:Mapped[str]=mapped_column(default='group')
    name_en:Mapped[str]=mapped_column(default='',server_default='')  # optional English name of a department

class GroupMember(Identity,Base):
    __tablename__='group_members'
    __table_args__=(UniqueConstraint('group_id','user_id'),)
    tenant_id:Mapped[str]=mapped_column(index=True)
    group_id:Mapped[str]=mapped_column(ForeignKey('access_groups.id'),index=True)
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)

class ResourcePolicy(Identity,Base):
    __tablename__='resource_policies'
    __table_args__=(UniqueConstraint('resource_type','resource_id'),)
    tenant_id:Mapped[str]=mapped_column(index=True)
    resource_type:Mapped[str]
    resource_id:Mapped[str]=mapped_column(index=True)
    visibility:Mapped[str]=mapped_column(default='inherit')
    readers:Mapped[list]=mapped_column(JSON,default=list)
    writers:Mapped[list]=mapped_column(JSON,default=list)
    reader_groups:Mapped[list]=mapped_column(JSON,default=list)
    writer_groups:Mapped[list]=mapped_column(JSON,default=list)

class ConversationShare(Identity,Base):
    __tablename__='conversation_shares'
    conversation_id:Mapped[str]=mapped_column(ForeignKey('conversations.id'),unique=True)
    tenant_id:Mapped[str]=mapped_column(index=True)
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id'))
    users:Mapped[list]=mapped_column(JSON,default=list)
    groups:Mapped[list]=mapped_column(JSON,default=list)
    expires_at:Mapped[float]

class TaskRun(Identity,Base):
    __tablename__='task_runs'
    task_key:Mapped[str]=mapped_column(unique=True)
    kind:Mapped[str]
    target_id:Mapped[str]=mapped_column(index=True)
    tenant_id:Mapped[str]=mapped_column(index=True)
    status:Mapped[str]=mapped_column(default='queued',index=True)
    attempts:Mapped[int]=mapped_column(default=0)
    lease_token:Mapped[str]=mapped_column(default='')
    lease_until:Mapped[float]=mapped_column(default=0)
    next_attempt:Mapped[float]=mapped_column(default=0)
    error:Mapped[str]=mapped_column(default='')
    updated_at:Mapped[str]=mapped_column(default='')

class SystemAlert(Identity,Base):
    __tablename__='system_alerts'
    alert_key:Mapped[str]=mapped_column(unique=True)
    tenant_id:Mapped[str]=mapped_column(default='',index=True)
    user_id:Mapped[str]=mapped_column(default='',index=True)
    severity:Mapped[str]=mapped_column(default='warning')
    title:Mapped[str]
    detail:Mapped[str]=mapped_column(Text,default='')
    resource_id:Mapped[str]=mapped_column(default='')
    status:Mapped[str]=mapped_column(default='active',index=True)
    updated_at:Mapped[str]=mapped_column(default='')

class AlertRead(Identity,Base):
    __tablename__='alert_reads'
    __table_args__=(UniqueConstraint('alert_id','user_id'),)
    alert_id:Mapped[str]=mapped_column(ForeignKey('system_alerts.id'))
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id'))

class Backup(Identity,Base):
    __tablename__='backups'
    status:Mapped[str]=mapped_column(default='queued')
    filename:Mapped[str]=mapped_column(default='')
    size:Mapped[int]=mapped_column(default=0)
    file_count:Mapped[int]=mapped_column(default=0)
    sha256:Mapped[str]=mapped_column(default='')
    error:Mapped[str]=mapped_column(default='')
    completed_at:Mapped[str]=mapped_column(default='')
    automatic:Mapped[bool]=mapped_column(default=False)
