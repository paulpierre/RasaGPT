from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declared_attr
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from datetime import datetime
from util import snake_case
import uuid as uuid_pkg

from sqlmodel import (
    UniqueConstraint,
    create_engine,
    Relationship,
    SQLModel,
    Session,
    select,
    Field,
)
from typing import (
    Optional,
    Union,
    List,
    Dict,
    Any
)
from config import (
    LLM_DEFAULT_DISTANCE_STRATEGY,
    VECTOR_EMBEDDINGS_COUNT,
    LLM_MAX_OUTPUT_TOKENS,
    DISTANCE_STRATEGIES,
    LLM_MIN_NODE_LIMIT,
    PGVECTOR_ADD_INDEX,
    ENTITY_STATUS,
    CHANNEL_TYPE,
    LLM_MODELS,
    DB_USER,
    SU_DSN,
    logger,
)


# ==========
# Base model
# ==========
class BaseModel(SQLModel):
    @declared_attr
    def __tablename__(cls) -> str:
        return snake_case(cls.__name__)

    @classmethod
    def by_uuid(self, _uuid: uuid_pkg.UUID):
        with Session(get_engine()) as session:
            q = select(self).where(self.uuid == _uuid)
            org = session.exec(q).first()
            return org if org else None

    def update(self, o: Union[SQLModel, dict] = None):
        if not o:
            raise ValueError("Must provide a model or dict to update values")
        o = o if isinstance(o, dict) else o.dict(exclude_unset=True)
        for key, value in o.items():
            setattr(self, key, value)

        # save and commit to database
        with Session(get_engine()) as session:
            session.add(self)
            session.commit()
            session.refresh(self)

    def delete(self):
        with Session(get_engine()) as session:
            self.status = ENTITY_STATUS.DELETED
            self.updated_at = datetime.utcnow()
            session.add(self)
            session.commit()
            session.refresh(self)

    @classmethod
    def create(self, o: Union[SQLModel, dict] = None):
        if not o:
            raise ValueError("Must provide a model or dict to update values")

        with Session(get_engine()) as session:
            obj = self.from_orm(o) if isinstance(o, SQLModel) else self(**o)
            session.add(obj)
            session.commit()
            session.refresh(obj)

        return obj


# ============
# Organization
# ============
class Organization(BaseModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: Optional[uuid_pkg.UUID] = Field(
        unique=True, default_factory=uuid_pkg.uuid4
    )  # UUID for the organization
    display_name: Optional[str] = Field(
        default="Untitled Organization 😊", index=True
    )  # display name of the organization
    namespace: str = Field(
        unique=True, index=True
    )  # unique organization namespace for URLs, etc.
    bot_url: Optional[str] = Field(default=None)  # URL for the bot
    status: Optional[ENTITY_STATUS] = Field(default=ENTITY_STATUS.ACTIVE.value)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

    # -------------
    # Relationships
    # -------------
    projects: Optional[List["Project"]] = Relationship(back_populates="organization")
    documents: Optional[List["Document"]] = Relationship(back_populates="organization")

    @property
    def project_count(self) -> int:
        return len(self.projects)

    @property
    def document_count(self) -> int:
        return len(self.documents)

    def __repr__(self):
        return f"<Organization id={self.id} name={self.display_name} namespace={self.namespace} uuid={self.uuid}>"


class OrganizationCreate(SQLModel):
    display_name: Optional[str]
    namespace: Optional[str]
    bot_url: Optional[str]


class OrganizationRead(SQLModel):
    id: int
    uuid: uuid_pkg.UUID
    display_name: str
    namespace: Optional[str]
    bot_url: Optional[str]
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(SQLModel):
    display_name: Optional[str]
    namespace: Optional[str]
    bot_url: Optional[str]


# ===============
# User (customer)
# ===============
class User(BaseModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    identifier: str = Field(default=None, unique=True, index=True)
    identifier_type: Optional[CHANNEL_TYPE] = Field(default=None)
    uuid: Optional[uuid_pkg.UUID] = Field(unique=True, default_factory=uuid_pkg.uuid4)
    first_name: Optional[str] = Field(default=None)
    last_name: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    dob: Optional[datetime] = Field(default=None)
    device_fingerprint: Optional[str] = Field(default=None)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

    # -------------
    # Relationships
    # -------------
    chat_sessions: Optional[List["ChatSession"]] = Relationship(back_populates="user")

    @property
    def chat_session_count(self) -> int:
        return len(self.chat_sessions)

    __table_args__ = (
        UniqueConstraint("identifier", "identifier_type", name="unq_id_idtype"),
    )

    def __repr__(self):
        return f"<User id={self.id} uuid={self.uuid} project_id={self.project_id} device_fingerprint={self.device_fingerprint}>"


class UserCreate(SQLModel):
    identifier: str
    identifier_type: CHANNEL_TYPE
    device_fingerprint: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    dob: Optional[datetime]


class UserReadList(SQLModel):
    id: int
    identifier: Optional[str]
    identifier_type: Optional[CHANNEL_TYPE]
    uuid: uuid_pkg.UUID
    device_fingerprint: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    dob: Optional[datetime]
    chat_session_count: int
    created_at: datetime
    updated_at: datetime


class UserUpdate(SQLModel):
    device_fingerprint: Optional[str]
    device_fingerprint: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    dob: Optional[datetime]


# =======
# Project
# =======
class Project(BaseModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: Optional[uuid_pkg.UUID] = Field(unique=True, default_factory=uuid_pkg.uuid4)
    organization_id: int = Field(default=None, foreign_key="organization.id")
    display_name: str = Field(default="📝 Untitled Project")
    status: Optional[ENTITY_STATUS] = Field(default=ENTITY_STATUS.ACTIVE.value)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

    # -------------
    # Relationships
    # -------------
    organization: Optional["Organization"] = Relationship(back_populates="projects")
    documents: Optional[List["Document"]] = Relationship(back_populates="project")
    chat_sessions: Optional[List["ChatSession"]] = Relationship(
        back_populates="project"
    )

    @property
    def document_count(self) -> int:
        return len(self.documents)

    def __repr__(self):
        return f"<Project id={self.id} name={self.display_name} uuid={self.uuid} project_id={self.uuid}>"


class ProjectCreate(SQLModel):
    display_name: Optional[str]


class ProjectReadListOrganization(SQLModel):
    uuid: uuid_pkg.UUID
    display_name: str
    namespace: Optional[str]
    document_count: int


class ProjectUpdate(SQLModel):
    display_name: Optional[str]
    status: Optional[ENTITY_STATUS]


# =========
# Documents
# =========
class Document(BaseModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    uuid: Optional[uuid_pkg.UUID] = Field(unique=True, default_factory=uuid_pkg.uuid4)
    organization_id: int = Field(default=None, foreign_key="organization.id")
    project_id: int = Field(default=None, foreign_key="project.id")
    display_name: str = Field(default="Untitled Document 😊")
    url: str = Field(default="")
    data: Optional[bytes] = Field(default=None)
    hash: str = Field(default=None)
    version: Optional[int] = Field(default=1)
    status: Optional[ENTITY_STATUS] = Field(default=ENTITY_STATUS.ACTIVE.value)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

    # -------------
    # Relationships
    # -------------
    nodes: Optional[List["Node"]] = Relationship(back_populates="document")
    organization: Optional["Organization"] = Relationship(back_populates="documents")
    project: Optional["Project"] = Relationship(back_populates="documents")

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    __table_args__ = (UniqueConstraint("uuid", "hash", name="unq_org_document"),)

    def __repr__(self):
        return f"<Document id={self.id} name={self.display_name} uuid={self.uuid}>"


class ProjectRead(SQLModel):
    id: int
    uuid: uuid_pkg.UUID
    organization: Organization
    document_count: int
    documents: Optional[List[Document]] = None
    display_name: str
    created_at: datetime
    updated_at: datetime


class DocumentCreate(SQLModel):
    project: Project
    display_name: Optional[str]
    url: Optional[str]
    version: Optional[str]
    data: Optional[bytes]
    hash: Optional[str]


class DocumentUpdate(SQLModel):
    status: Optional[ENTITY_STATUS]


# ==============
# Document Nodes
# ==============
class Node(BaseModel, table=True):
    class Config:
        arbitrary_types_allowed = True

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: int = Field(default=None, foreign_key="document.id")
    uuid: Optional[uuid_pkg.UUID] = Field(unique=True, default_factory=uuid_pkg.uuid4)
    embeddings: Optional[List[float]] = Field(
        sa_column=Column(Vector(VECTOR_EMBEDDINGS_COUNT))
    )
    meta: Optional[Dict] = Field(default=None, sa_column=Column(JSONB))
    token_count: Optional[int] = Field(default=None)
    text: str = Field(default=None, nullable=False)
    status: Optional[ENTITY_STATUS] = Field(default=ENTITY_STATUS.ACTIVE.value)
    created_at: Optional[datetime] = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(default_factory=datetime.now)

    # -------------
    # Relationships
    # -------------
    document: Optional["Document"] = Relationship(back_populates="nodes")

    def __repr__(self):
        return f"<Node id={self.id} uuid={self.uuid} document={self.document_id}>"


class NodeCreate(SQLModel):
    document: Document
    embeddings: List[float]
    token_count: Optional[int]
    text: str
    status: Optional[ENTITY_STATUS]


class NodeRead(SQLModel):
    id: int
    document: Document
    embeddings: Optional[List[float]]
    token_count: Optional[int]
    text: str
    created_at: datetime


class DocumentReadNodeList(SQLModel):
    id: int
    uuid: uuid_pkg.UUID
    display_name: str
    node_count: int


class NodeReadResult(SQLModel):
    id: int
    token_count: Optional[int]
    text: str
    meta: Optional[Dict]


class ProjectReadListDocumentList(SQLModel):
    uuid: uuid_pkg.UUID
    display_name: str
    node_count: Optional[int]


class ProjectReadList(SQLModel):
    id: int
    # organization: ProjectReadListOrganization
    documents: Optional[List[DocumentReadNodeList]]
    document_count: int
    uuid: uuid_pkg.UUID
    display_name: str
    created_at: datetime
    updated_at: datetime


class NodeReadList(SQLModel):
    id: int
    document: DocumentReadNodeList
    embeddings: Optional[List[float]]
    token_count: Optional[int]
    text: str
    created_at: datetime


class NodeUpdate(SQLModel):
    status: Optional[ENTITY_STATUS] = Field(default=ENTITY_STATUS.ACTIVE.value)


class NodeReadListDocumentRead(SQLModel):
    uuid: uuid_pkg.UUID
    token_count: Optional[int]
    created_at: datetime


class DocumentReadList(SQLModel):
    id: int
    uuid: uuid_pkg.UUID
    display_name: str
    version: int
    nodes: Optional[List[NodeReadListDocumentRead]] = None
    node_count: int
    hash: str
    created_at: datetime
    updated_at: datetime


# ============
# Chat Session
# ============
class ChatSession(BaseModel, table=True):
    class Config:
        arbitrary_types_allowed = True

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: Optional[uuid_pkg.UUID] = Field(
        index=True, default_factory=uuid_pkg.uuid4
    )
    user_id: int = Field(default=None, foreign_key="user.id")
    project_id: int = Field(default=None, foreign_key="project.id")
    channel: CHANNEL_TYPE = Field(default=CHANNEL_TYPE.TELEGRAM)
    user_message: str = Field(default=None)
    token_count: Optional[int] = Field(default=None)
    embeddings: Optional[List[float]] = Field(
        sa_column=Column(Vector(VECTOR_EMBEDDINGS_COUNT))
    )
    response: Optional[str] = Field(default=None)
    meta: Optional[Dict] = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=datetime.now)

    # -------------
    # Relationships
    # -------------
    user: Optional["User"] = Relationship(back_populates="chat_sessions")
    project: Optional["Project"] = Relationship(back_populates="chat_sessions")

    def __repr__(self):
        return f"<ChatSession id={self.id} uuid={self.uuid} project_id={self.project_id} user_id={self.user_id} message={self.user_message}>"


class ChatSessionCreatePost(SQLModel):
    project_id: Optional[str] = ""
    organization_id: Optional[str] = "pepe"
    channel: Optional[CHANNEL_TYPE] = CHANNEL_TYPE.TELEGRAM
    query: Optional[str] = "What is the weather like in London right now?"
    identifier: Optional[str] = "@username"
    distance_strategy: Optional[str] = LLM_DEFAULT_DISTANCE_STRATEGY
    max_output_tokens: Optional[int] = LLM_MAX_OUTPUT_TOKENS
    node_limit: Optional[int] = LLM_MIN_NODE_LIMIT
    model: Optional[str] = LLM_MODELS.GPT_35_TURBO
    session_id: Optional[str] = ""


class ChatSessionCreate(SQLModel):
    channel: CHANNEL_TYPE
    token_count: Optional[int]
    user_message: str
    embeddings: List[float]
    response: Optional[str]


class ChatSessionRead(SQLModel):
    id: int
    user: User
    project: Optional[ProjectReadListDocumentList]
    token_count: Optional[int]
    channel: CHANNEL_TYPE
    user_message: str
    embeddings: List[float]
    response: Optional[str]
    meta: Optional[dict]
    created_at: datetime = Field(default_factory=datetime.now)


class ChatSessionResponse(SQLModel):
    meta: Optional[dict]
    response: Optional[str]
    user_message: Optional[str]


class ProjectReadChatSessionRead(SQLModel):
    id: int
    token_count: Optional[int]
    channel: CHANNEL_TYPE
    created_at: datetime = Field(default_factory=datetime.now)


class ChatSessionReadUserRead(SQLModel):
    id: int
    project: Optional[ProjectReadListDocumentList]
    token_count: Optional[int]
    channel: CHANNEL_TYPE
    user_message: str
    response: Optional[str]
    created_at: datetime = Field(default_factory=datetime.now)


class UserRead(SQLModel):
    id: int
    identifier: Optional[str]
    identifier_type: Optional[CHANNEL_TYPE]
    uuid: uuid_pkg.UUID
    language: Optional[str]
    device_fingerprint: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    dob: Optional[datetime]
    chat_session_count: int
    chat_sessions: Optional[List[ChatSessionReadUserRead]]
    created_at: datetime
    updated_at: datetime


class DocumentReadProjectRead(SQLModel):
    uuid: uuid_pkg.UUID
    display_name: str
    namespace: Optional[str]
    document_count: int


class DocumentRead(SQLModel):
    id: int
    uuid: uuid_pkg.UUID
    project: DocumentReadProjectRead
    organization: OrganizationRead
    display_name: str
    node_count: int
    url: Optional[str]
    version: int
    data: bytes
    hash: str
    created_at: datetime
    updated_at: datetime


class WebhookCreate(SQLModel):
    update_id: str
    message: Dict[str, Any]


class WebhookResponse(SQLModel):
    update_id: str
    message: Dict[str, Any]


# ==================
# Database functions
# ==================
def get_engine(dsn: str = SU_DSN):
    return create_engine(dsn)


def get_session():
    with Session(get_engine()) as session:
        yield session


def create_db():
    logger.info("...Enabling pgvector and creating database tables")
    enable_vector()
    BaseModel.metadata.create_all(get_engine(dsn=SU_DSN))
    create_user_permissions()
    create_vector_index()


def create_user_permissions():
    session = Session(get_engine(dsn=SU_DSN))
    # grant access to entire database and all tables to user DB_USER
    query = f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {DB_USER};"
    session.execute(query)
    session.commit()
    session.close()


def drop_db():
    BaseModel.metadata.drop_all(get_engine(dsn=SU_DSN))


def create_vector_index():
    # -------------------------------------
    # Let's add an index for the embeddings
    # -------------------------------------
    if PGVECTOR_ADD_INDEX is True:
        session = Session(get_engine(dsn=SU_DSN))
        for strategy in DISTANCE_STRATEGIES:
            session.execute(strategy[3])
            session.commit()


def enable_vector():
    session = Session(get_engine(dsn=SU_DSN))
    query = "CREATE EXTENSION IF NOT EXISTS vector;"
    session.execute(query)
    session.commit()
    add_vector_distance_fn(session)
    session.close()


def add_vector_distance_fn(session: Session):
    for strategy in DISTANCE_STRATEGIES:
        strategy_name = strategy[1]
        strategy_distance_str = strategy[2]

        query = f"""create or replace function match_node_{strategy_name} (
    query_embeddings vector({VECTOR_EMBEDDINGS_COUNT}),
    match_threshold float,
    match_count int
) returns table (
    uuid uuid,
    text varchar,
    similarity float
)
language plpgsql
as $$
begin
    return query
    select
        node.uuid,
        node.text,
        1 - (node.embeddings {strategy_distance_str} query_embeddings) as similarity
    from node
        where 1 - (node.embeddings {strategy_distance_str} query_embeddings) > match_threshold
        order by similarity desc
        limit match_count;
end;
$$;"""

        session.execute(query)
        session.commit()
    session.close()


if __name__ == "__main__":
    create_db()
