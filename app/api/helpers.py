from fastapi import HTTPException
from uuid import UUID
import os

from typing import (
    Optional,
    Union
)
from config import (
    FILE_UPLOAD_PATH,
    ENTITY_STATUS,
    logger
)

from util import (
    is_uuid,
    get_file_hash
)
from sqlmodel import (
    Session,
    select
)
from datetime import datetime
from models import (
    Organization,
    OrganizationCreate,
    User,
    UserCreate,
    get_engine,
    Project,
    ProjectCreate,
    Document,
    Node,
    ChatSession
)

# ================
# Helper functions
# ================


# ----------------------
# Organization functions
# ----------------------
def get_org_by_uuid_or_namespace(
    id: Union[UUID, str], session: Optional[Session] = None, should_except: bool = True
):
    if session:
        org = (
            Organization.by_uuid(str(id))
            if is_uuid(id)
            else session.exec(
                select(Organization).where(Organization.namespace == str(id))
            ).first()
        )

    else:
        with Session(get_engine()) as session:
            org = (
                Organization.by_uuid(str(id))
                if is_uuid(id)
                else session.exec(
                    select(Organization).where(Organization.namespace == str(id))
                ).first()
            )

    if not org and should_except is True:
        raise HTTPException(
            status_code=404, detail=f"Organization identifer {id} not found"
        )

    return org


def create_org_by_org_or_uuid(
    namespace: str = None,
    display_name: str = None,
    organization: Union[Organization, OrganizationCreate, str] = None,
    session: Optional[Session] = None,
):
    namespace = namespace or organization.namespace

    if not namespace:
        raise HTTPException(
            status_code=400, detail="Organization namespace is required"
        )

    o = (
        get_org_by_uuid_or_namespace(namespace, session=session, should_except=False)
        if not isinstance(organization, Organization)
        else organization
    )

    if o:
        raise HTTPException(status_code=404, detail="Organization already exists")

    if isinstance(organization, OrganizationCreate) or isinstance(organization, str):
        organization = organization or OrganizationCreate(
            namespace=namespace, display_name=display_name
        )

        db_org = Organization.from_orm(organization)

        if session:
            session.add(db_org)
            session.commit()
            session.refresh(db_org)
        else:
            with Session(get_engine()) as session:
                session.add(db_org)
                session.commit()
                session.refresh(db_org)
    elif isinstance(organization, Organization):
        db_org = organization
        db_org.update(
            {
                "namespace": namespace if namespace else organization.namespace,
                "display_name": display_name
                if display_name
                else organization.display_name,
            }
        )
    else:
        db_org = Organization.create(
            {"namespace": namespace, "display_name": display_name}
        )

    # Create folder for organization_uuid in uploads
    os.mkdir(os.path.join(FILE_UPLOAD_PATH, str(db_org.uuid)))

    return db_org


# --------------
# User functions
# --------------
def create_user(
    user: Union[UserCreate, User] = None,
    identifier: str = None,
    identifier_type: str = None,
    device_fingerprint: str = None,
    first_name: str = None,
    last_name: str = None,
    email: str = None,
    phone: str = None,
    dob: str = None,
    session: Optional[Session] = None,
):
    # Check if user already exists
    user = (
        get_user_by_uuid_or_identifier(user.id or identifier, session=session)
        if not isinstance(user, User)
        else user
    )

    if isinstance(user, UserCreate):
        db_user = User.from_orm(user)

        if session:
            session.add(db_user)
            session.commit()
            session.refresh(db_user)
        else:
            with Session(get_engine()) as session:
                session.add(db_user)
                session.commit()
                session.refresh(db_user)
    elif isinstance(user, User):
        db_user = user
        db_user.update(
            {
                "identifier": identifier if identifier else user.identifier,
                "identifier_type": identifier_type
                if identifier_type
                else user.identifier_type,
                "device_fingerprint": device_fingerprint
                if device_fingerprint
                else user.device_fingerprint,
                "first_name": first_name if first_name else user.first_name,
                "last_name": last_name if last_name else user.last_name,
                "email": email if email else user.email,
                "phone": phone if phone else user.phone,
                "dob": dob if dob else user.dob,
            }
        )
    else:
        db_user = User.create(
            {
                "identifier": identifier,
                "identifier_type": identifier_type,
                "device_fingerprint": device_fingerprint,
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "phone": phone,
                "dob": dob,
            }
        )

    return db_user


def get_users(session: Optional[Session] = None):
    if session:
        users = session.exec(select(User)).all()
    else:
        with Session(get_engine()) as session:
            users = session.exec(select(User)).all()

    return users


def get_user_by_uuid_or_identifier(
    id: Union[UUID, str], session: Optional[Session] = None, should_except: bool = True
):
    if session:
        user = (
            User.by_uuid(str(id))
            if is_uuid(str(id))
            else session.exec(select(User).where(User.identifier == str(id))).first()
        )

    else:
        with Session(get_engine()) as session:
            user = (
                User.by_uuid(str(id))
                if is_uuid(str(id))
                else session.exec(
                    select(User).where(User.identifier == str(id))
                ).first()
            )

    if not user and should_except is True:
        raise HTTPException(status_code=404, detail=f"User identifer {id} not found")

    return user


# ------------------
# Document functions
# ------------------
def create_document_by_file_path(
    organization: Organization = None,
    project: Project = None,
    file_path: str = None,
    url: Optional[str] = None,
    file_version: Optional[int] = 1,
    file_hash: Optional[str] = None,
    overwrite: Optional[bool] = True,
    session: Optional[Session] = None,
):
    if not organization or not project:
        raise HTTPException(
            status_code=400, detail="Organization and project are required"
        )

    organization_id = organization.uuid
    project_id = project.uuid

    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail="A valid file path is required")

    if not file_hash:
        file_hash = get_file_hash(file_path)

    file_name = os.path.basename(file_path)

    file_contents = open(file_path, "rb").read()

    # ------------------------
    # Handle duplicate content
    # ------------------------
    if get_document_by_hash(file_hash, session=session):
        raise HTTPException(
            status_code=409,
            detail=f'Document "{file_name}" already uploaded! \n\nsha256:{file_hash}!',
        )

    # ----------------------------------
    # Handle file versioning by filename
    # ----------------------------------

    # If we are overwriting, deprecate the current version and increment the version number of new file
    document = get_document_by_name(
        file_name,
        project_id=project_id,
        organization_id=organization_id,
        session=session,
    )

    if document and overwrite:
        file_version = document.version + 1
        document.updated_at = datetime.utcnow()
        document.status = ENTITY_STATUS.DEPRECATED.value
        document.save()
    else:
        # ---------------------
        # Create a new document
        # ---------------------
        document = Document(
            display_name=file_name,
            project_id=project.id,
            organization_id=organization.id,
            data=file_contents,
            version=file_version,
            hash=file_hash,
            url=url if url else None,
        )
        if session:
            session.add(document)
            session.commit()
            session.refresh(document)

            # ---------------------
            # Create the embeddings
            # ---------------------
            create_document_nodes(
                document=document,
                project=project,
                organization=organization,
                session=session,
            )

        else:
            with Session(get_engine()) as session:
                session.add(document)
                session.commit()
                session.refresh(document)

                # ---------------------
                # Create the embeddings
                # ---------------------
                create_document_nodes(
                    document=document,
                    project=project,
                    organization=organization,
                    session=session,
                )

    if not document:
        raise HTTPException(status_code=400, detail="Could not create document")


# --------------------------
# Create document embeddings
# --------------------------
def create_document_nodes(
    document: Document,
    project: Project,
    organization: Organization,
    session: Optional[Session] = None,
):
    # Avoid circular imports
    from llm import get_embeddings, get_token_count

    project_uuid = str(project.uuid)
    document_uuid = str(document.uuid)
    document_id = document.id
    organization_uuid = str(organization.uuid)

    if not document or not project:
        raise Exception("Missing required parameters document, project")

    metadata = {
        "project_uuid": project_uuid,
        "document_uuid": document_uuid,
        "organization_uuid": organization_uuid,
        "document_id": document_id,
        "version": document.version,
        "name": document.display_name,
    }

    # convert document data bytes to string
    document_data = (
        document.data.decode("utf-8")
        if isinstance(document.data, bytes)
        else document.data
    )

    # lets get the embeddings
    arr_documents, embeddings = get_embeddings(document_data)

    # -------------------------------------------
    # Process the embeddings and save to database
    # -------------------------------------------

    for doc, vec in zip(arr_documents, embeddings):
        node = Node(
            document_id=document.id,
            embeddings=vec,
            text=doc,
            token_count=get_token_count(doc),
            meta=metadata
        )
        if session:
            session.add(node)
            session.commit()
            session.refresh(node)

        else:
            with Session(get_engine()) as session:
                session.add(node)
                session.commit()
                session.refresh(node)

        # Node.create(
        #     {
        #         "document_id": document.id,
        #         "embeddings": vec,
        #         "text": doc,
        #         "token_count": get_token_count(doc),
        #         "meta": metadata,
        #     }
        # )


def get_documents_by_project_and_org(
    project_id: Union[UUID, str],
    organization_id: Union[UUID, str],
    session: Optional[Session] = None,
):
    if session:
        org = get_org_by_uuid_or_namespace(organization_id, session=session)
        project = get_project_by_uuid(project_id, org.uuid, session=session)
        documents = session.exec(
            select(Document).where(Document.project_id == project.id)
        ).all()
    else:
        with Session(get_engine()) as session:
            org = get_org_by_uuid_or_namespace(organization_id, session=session)
            project = get_project_by_uuid(project_id, org.uuid, session=session)
            documents = session.exec(
                select(Document).where(Document.project_id == project.id)
            ).all()

    return documents


def get_document_by_uuid(
    uuid: Union[UUID, str],
    organization_id: Union[UUID, str] = None,
    project_id: Union[UUID, str] = None,
    session: Optional[Session] = None,
    should_except: bool = True,
):
    if not is_uuid(uuid):
        raise HTTPException(
            status_code=422, detail=f"Invalid document identifier {uuid}"
        )

    org = get_org_by_uuid_or_namespace(organization_id, session=session)
    project = get_project_by_uuid(project_id, organization_id=org.uuid, session=session)

    if session:
        document = session.exec(
            select(Document).where(
                Document.project == project, Document.uuid == str(uuid)
            )
        ).first()

    else:
        with Session(get_engine()) as session:
            document = session.exec(
                select(Document).where(
                    Document.project == project, Document.uuid == str(uuid)
                )
            ).first()

    if not document and should_except is True:
        raise HTTPException(
            status_code=404, detail=f"Document identifier {uuid} not found"
        )

    return document


def get_document_by_hash(hash: str, session: Optional[Session] = None):
    if session:
        document = session.exec(select(Document).where(Document.hash == hash)).first()
    else:
        with Session(get_engine()) as session:
            document = session.exec(
                select(Document).where(Document.hash == hash)
            ).first()

    return document


def get_document_by_name(
    file_name: str,
    project_id: Union[UUID, str],
    organization_id: Union[UUID, str],
    session: Optional[Session] = None,
):
    org = (
        get_org_by_uuid_or_namespace(organization_id, session=session)
        if not isinstance(organization_id, Organization)
        else organization_id
    )
    project = get_project_by_uuid(
        project_id, organization_id=str(org.uuid), session=session
    )

    if session:
        return session.exec(
            select(Document).where(
                Document.project == project,
                Document.display_name == file_name,
                Document.status == ENTITY_STATUS.ACTIVE.value,
            )
        ).first()
    else:
        with Session(get_engine()) as session:
            return session.exec(
                select(Document).where(
                    Document.project == project,
                    Document.display_name == file_name,
                    Document.status == ENTITY_STATUS.ACTIVE.value,
                )
            ).first()


# ---------------------
# ChatSession functions
# ---------------------
def get_chat_session_by_uuid(
    id: Union[UUID, str], session: Optional[Session] = None, should_except: bool = False
):
    if session:
        chat_session = (
            ChatSession.by_uuid(str(id))
            if is_uuid(id)
            else session.exec(
                select(ChatSession).where(ChatSession.session_id == str(id))
            ).first()
        )

    else:
        with Session(get_engine()) as session:
            chat_session = (
                ChatSession.by_uuid(str(id))
                if is_uuid(id)
                else session.exec(
                    select(ChatSession).where(ChatSession.session_id == str(id))
                ).first()
            )

    if not chat_session and should_except is True:
        raise HTTPException(
            status_code=404, detail=f"ChatSession identifer {id} not found"
        )

    return chat_session


# -----------------
# Project functions
# -----------------


def create_project_by_org(
    project: Union[Project, ProjectCreate] = None,
    organization_id: Union[Organization, str] = None,
    display_name: str = None,
    session: Optional[Session] = None,
):
    organization = (
        get_org_by_uuid_or_namespace(organization_id, session=session)
        if not isinstance(organization_id, Organization)
        else organization_id
    )

    if isinstance(project, ProjectCreate):
        db_project = Project.from_orm(project) if not project else project
        db_project.organization_id = organization.id

        # Lets give a default name if not set
        db_project.display_name = (
            f"📁 Untitled Project #{len(organization.projects) + 1}"
            if not display_name and not project
            else display_name
        )

        if session:
            session.add(db_project)
            session.commit()
            session.refresh(db_project)
        else:
            with Session(get_engine()) as session:
                session.add(db_project)
                session.commit()
                session.refresh(db_project)
    elif isinstance(project, Project):
        db_project = project
        db_project.update(
            {
                "organization_id": organization.id,
                "display_name": f"📁 Untitled Project #{len(organization.projects) + 1}"
                if not display_name and not project
                else display_name,
            }
        )
    else:
        db_project = Project.create(
            {
                "organization_id": organization.id,
                "display_name": f"📁 Untitled Project #{len(organization.projects) + 1}"
                if not display_name and not project
                else display_name,
            }
        )

    # -------------------------------
    # Create project upload directory
    # -------------------------------
    project_dir = os.path.join(
        FILE_UPLOAD_PATH, str(organization.uuid), str(db_project.uuid)
    )
    os.makedirs(project_dir, exist_ok=True)

    # Create project
    return db_project


def get_project_by_uuid(
    uuid: Union[UUID, str] = None,
    organization_id: Union[UUID, str] = None,
    session: Optional[Session] = None,
    should_except: bool = True,
):
    if not is_uuid(uuid):
        raise HTTPException(
            status_code=422, detail=f"Invalid project identifier {uuid}"
        )

    org = get_org_by_uuid_or_namespace(organization_id, session=session)

    if session:
        project = session.exec(
            select(Project).where(
                Project.organization == org, Project.uuid == str(uuid)
            )
        ).first()

    else:
        with Session(get_engine()) as session:
            project = session.exec(
                select(Project).where(
                    Project.organization == org, Project.uuid == str(uuid)
                )
            ).first()

    if not project and should_except is True:
        raise HTTPException(
            status_code=404, detail=f"Project identifier {uuid} not found"
        )

    return project