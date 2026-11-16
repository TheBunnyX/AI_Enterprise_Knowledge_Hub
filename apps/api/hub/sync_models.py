"""Where a department's knowledge base keeps itself up to date from."""
from sqlalchemy import Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
from .models import Identity


class KBSource(Identity, Base):
    """A file on the web that a knowledge base mirrors: re-fetched on a schedule, a new version when its content changed."""
    __tablename__ = 'kb_sources'
    tenant_id: Mapped[str] = mapped_column(index=True)
    knowledge_base_id: Mapped[str] = mapped_column(ForeignKey('knowledge_bases.id'), index=True)
    url: Mapped[str]
    interval_minutes: Mapped[int] = mapped_column(default=1440)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    document_id: Mapped[str] = mapped_column(default='')  # the document this source feeds, once it exists
    content_sha: Mapped[str] = mapped_column(default='')
    last_checked: Mapped[str] = mapped_column(default='')  # ISO time of the last attempt
    last_status: Mapped[str] = mapped_column(default='')  # updated | unchanged | error
    last_error: Mapped[str] = mapped_column(default='')
