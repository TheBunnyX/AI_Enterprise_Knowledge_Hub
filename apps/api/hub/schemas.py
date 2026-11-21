from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated, Literal

class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1,max_length=200)
class KBCreate(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    name_en: str = Field(default='',max_length=100)  # optional English name
    description: str = Field(default='',max_length=500)
    department_id: str = Field(default='',max_length=36)  # '' = the creator's own department (a Super Admin may leave it unset)
    multimodal: bool = False  # describe and embed the pictures in this library's documents (sent to Google AI)
class ChatInput(BaseModel):
    question: str = Field(min_length=1,max_length=6000)
    conversation_id: str | None = None
    knowledge_base_id: str | None = None
    document_ids: list[str] = Field(default_factory=list,max_length=30)
    model_id: str | None = None
    spoken: bool = False
    attachment_ids: list[Annotated[str,StringConstraints(pattern=r'^[0-9a-f]{32}$')]] = Field(default_factory=list,max_length=5)  # temporary files from /chat/attachments
    web_search: bool = False  # let the model search the web (OpenRouter models only)
    effort: Literal['','minimal','low','medium','high'] = ''  # reasoning effort chosen in chat; '' = the model's own setting
    skill_id: str | None = Field(default=None,max_length=36)  # a saved skill whose instructions steer this answer
    use_documents: bool = True  # False = plain LLM chat: no retrieval, no citations
    agent: bool = False  # Agent mode: the model plans and calls read-only tools (documents, web) in a loop
    agent_decision: Literal['approve','deny'] | None = None  # the user's answer when a paused agent run asked for approval
class OrgInput(BaseModel):
    name: str = Field(min_length=1,max_length=200)
    status: Literal['active','suspended','pending'] = 'active'
    quota: int = Field(default=10000,ge=0,le=100000000)
class UserInput(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    name_en: str = Field('',max_length=100)
    email: str = Field(pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$',max_length=254)
    tenant_id: str = ''
    role: Literal['SUPER_ADMIN','DEPARTMENT_ADMIN','USER'] = 'USER'
    password: str = Field(min_length=12,max_length=200)
    department_id: str | None = None
class ModelInput(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    provider: Literal['LiteLLM','OpenRouter','Google AI','Local LLM'] = 'LiteLLM'
    api_id: str = Field(min_length=1,max_length=200)
    category: Literal['LLM','Embedding','Reranker','STT','TTS','Live','Image','Video','Search API'] = 'LLM'
    enabled: bool = False
    rpm: int = Field(default=0,ge=0,le=10000000)
    tpm: int = Field(default=0,ge=0,le=2000000000)
    rpd: int = Field(default=0,ge=0,le=100000000)
    input_price: float = Field(default=0,ge=0)
    output_price: float = Field(default=0,ge=0)
    effort: Literal['','minimal','low','medium','high'] = ''
    media_limits: dict[Literal['resolutions','aspect_ratios','durations'],list[Annotated[str,StringConstraints(max_length=12)]]] = Field(default_factory=dict)


class DocumentNames(BaseModel):
    """Both names of a document: the file name (Thai or any language; its extension must not change) and an optional English name."""
    name: str | None = Field(None, min_length=1, max_length=200)
    name_en: str | None = Field(None, max_length=200)
