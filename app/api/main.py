from fastapi import (
    FastAPI,
    File,
    Depends,
    HTTPException,
    UploadFile
)
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from typing import (
    List,
    Optional,
    Union,
    Any
)
from datetime import datetime
import requests
import aiohttp
import time
import json
import os

# -----------
# LLM imports
# -----------
from llm import (
    chat_query
)

# ----------------
# Database imports
# ----------------
from models import (
    # ---------------
    # Database Models
    # ---------------
    Organization,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    User,
    UserCreate,
    UserRead,
    UserReadList,
    UserUpdate,
    DocumentRead,
    DocumentReadList,
    ProjectCreate,
    ProjectRead,
    ProjectReadList,
    ChatSessionResponse,
    ChatSessionCreatePost,
    WebhookCreate,
    # ------------------
    # Database functions
    # ------------------
    get_engine,
    get_session

)
from helpers import (
    # ----------------
    # Helper functions
    # ----------------
    get_org_by_uuid_or_namespace,
    get_project_by_uuid,
    get_user_by_uuid_or_identifier,
    get_users,
    get_documents_by_project_and_org,
    get_document_by_uuid,
    create_org_by_org_or_uuid,
    create_project_by_org
)
from util import (
    save_file,
    get_sha256,
    is_uuid,
    logger
)
# -----------
# LLM imports
# -----------
from config import (
    APP_NAME,
    APP_VERSION,
    APP_DESCRIPTION,
    ENTITY_STATUS,
    CHANNEL_TYPE,
    LLM_MODELS,
    LLM_DISTANCE_THRESHOLD,
    LLM_DEFAULT_DISTANCE_STRATEGY,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_MIN_NODE_LIMIT,
    FILE_UPLOAD_PATH,
    RASA_WEBHOOK_URL
)


# ------------------
# Mount static files
# ------------------


app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------
# Health check endpoint
# ---------------------
@app.get("/health", include_in_schema=False)
def health_check():
    return {'status': 'ok'}


# ======================
# ORGANIZATION ENDPOINTS
# ======================

# ---------------------
# Get all organizations
# ---------------------
@app.get("/org", response_model=List[OrganizationRead])
def read_organizations():
    '''
    ## Get all active organizations

    Returns:
        List[OrganizationRead]: List of organizations

    '''
    with Session(get_engine()) as session:
        orgs = session.exec(select(Organization).where(Organization.status == ENTITY_STATUS.ACTIVE.value)).all()
        return orgs


# ----------------------
# Create an organization
# ----------------------
@app.post("/org", response_model=Union[OrganizationRead, Any])
def create_organization(
    *,
    session: Session = Depends(get_session),
    organization: Optional[OrganizationCreate] = None,
    namespace: Optional[str] = None,
    display_name: Optional[str] = None
):
    '''

    ### Creates a new organization
    ### <u>Args:</u>
    - **namespace**: Unique namespace for the organization (ex. openai)
    - **name**: Name of the organization (ex. OpenAI)
    - **bot_url**: URL of the bot (ex. https://t.me/your_bot)

    ### <u>Returns:</u>
    - OrganizationRead
    ---
    <details><summary>👇 💻 Code examples:</summary>
    ### 🖥️ Curl
    ```bash
    curl -X POST "http://localhost:8888/org" -H "accept: application/json" -H "Content-Type: application/json" -d '{\"namespace\":\"openai\",\"name\":\"OpenAI\",\"bot_url\":\"https://t.me/your_bot\"}'
    ```
    <br/>
    ### 🐍 Python
    ```python
    import requests
    response = requests.post("http://localhost:8888/org", json={"namespace":"openai","name":"OpenAI","bot_url":"https://t.me/your_bot"})
    print(response.json())
    ```
    </details>
    '''
    # Create organization
    return create_org_by_org_or_uuid(
        organization=organization,
        namespace=namespace,
        display_name=display_name, session=session
    )


# ---------------------------
# Get an organization by UUID
# ---------------------------
@app.get("/org/{organization_id}", response_model=Union[OrganizationRead, Any])
def read_organization(
    *,
    session: Session = Depends(get_session),
    organization_id: str
):

    organization = get_org_by_uuid_or_namespace(organization_id, session=session)

    return organization


# ------------------------------
# Update an organization by UUID
# ------------------------------
@app.put("/org/{organization_id}", response_model=Union[OrganizationRead, Any])
def update_organization(
    *,
    session: Session = Depends(get_session),
    organization_id: str,
    organization: OrganizationUpdate
):

    org = get_org_by_uuid_or_namespace(organization_id, session=session)

    org.update(organization.dict(exclude_unset=True))
    return org


# =================
# Project endpoints
# =================

# -----------------------
# Get all projects by org
# -----------------------
@app.get("/project", response_model=List[ProjectReadList])
def read_projects(
    *,
    session: Session = Depends(get_session),
    organization_id: str
):

    organization = get_org_by_uuid_or_namespace(organization_id, session=session)

    if not organization.projects:
        raise HTTPException(status_code=404, detail='No projects found for organization')

    return organization.projects


# -----------------------
# Create a project by org
# -----------------------
@app.post("/project", response_model=Union[ProjectRead, Any])
def create_project(
    *,
    session: Session = Depends(get_session),
    organization_id: str,
    project: ProjectCreate
):
    return create_project_by_org(
        organization_id=organization_id,
        project=project,
        session=session
    )


# -----------------------------
# Get a project by UUID and org
# -----------------------------
@app.get("/project/{project_id}", response_model=Union[ProjectRead, Any])
def read_project(
    *,
    session: Session = Depends(get_session),
    organization_id: str,
    project_id: str
):

    return get_project_by_uuid(uuid=project_id, organization_id=organization_id, session=session)


# ==================
# DOCUMENT ENDPOINTS
# ==================

# ---------------
# Upload document
# ---------------
@app.post("/document", response_model=Union[DocumentReadList, Any])
async def upload_document(
    *,
    session: Session = Depends(get_session),
    organization_id: str,
    project_id: str,
    url: Optional[str] = None,
    file: Optional[UploadFile] = File(...),
    overwrite: Optional[bool] = True
):
    organization = get_org_by_uuid_or_namespace(organization_id, session=session)
    project = get_project_by_uuid(uuid=project_id, organization_id=organization_id, session=session)
    file_root_path = os.path.join(FILE_UPLOAD_PATH, str(organization.uuid), str(project.uuid))

    file_version = 1

    # ------------------------
    # Enforce XOR for url/file
    # ------------------------
    if url and file:
        raise HTTPException(status_code=400, detail='You can only upload a file OR provide a URL, not both')

    # --------------------
    # Upload file from URL
    # --------------------
    if url:
        file_name = url.split('/')[-1]
        file_upload_path = os.path.join(file_root_path, file_name)
        file_exists = os.path.isfile(file_upload_path)

        if file_exists:
            file_name = f'{file_name}_{int(time.time())}'
            file_upload_path = os.path.join(file_root_path, file_name)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=400, detail=f'Could not download file from {url}')

                with open(file_upload_path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(1024)
                        if not chunk:
                            break
                        f.write(chunk)

        file_contents = open(file_upload_path, 'rb').read()
        file_hash = get_sha256(contents=file_contents)

    # -----------------------
    # Upload file from device
    # -----------------------
    else:
        file_name = file.filename
        file_upload_path = os.path.join(file_root_path, file_name)
        file_exists = os.path.isfile(file_upload_path)

        if file_exists:
            file_name = f'{file_name}_{int(time.time())}'
            file_upload_path = os.path.join(file_root_path, file_name)

        file_contents = await file.read()
        file_hash = get_sha256(contents=file_contents)
        await save_file(file, file_upload_path)

    document_obj = create_document_by_file_path(
        organization=organization,
        project=project,
        file_path=file_upload_path,
        file_hash=file_hash,
        file_version=file_version,
        url=url,
        overwrite=overwrite,
        session=session
    )
    return document_obj


# --------------------------------
# List all documents for a project
# --------------------------------
@app.get("/document", response_model=List[DocumentReadList])
def read_documents(
    *,
    session: Session = Depends(get_session),
    organization_id: str,
    project_id: str
):
    return get_documents_by_project_and_org(project_id=project_id, organization_id=organization_id, session=session)

# ----------------------
# Get a document by UUID
# ----------------------
@app.get("/document/{document_id}", response_model=DocumentRead)
def read_document(
    *,
    session: Session = Depends(get_session),
    organization_id: str,
    project_id: str,
    document_id: str
):
    return get_document_by_uuid(uuid=document_id, project_id=project_id, organization_id=organization_id, session=session)


# ==============
# USER ENDPOINTS
# ==============

# -------------
# Get all users
# -------------
@app.get("/user", response_model=List[UserReadList])
def read_users(
    *,
    session: Session = Depends(get_session),
):
    return get_users(session=session)


# -------------
# Create a user
# -------------
@app.post("/user", response_model=UserRead)
def create_user(
    *,
    session: Session = Depends(get_session),
    user: UserCreate
):

    return create_user(
        user=user,
        session=session
    )


# ------------------
# Get a user by UUID
# ------------------
@app.get("/user/{user_uuid}", response_model=UserRead)
def read_user(
    *,
    session: Session = Depends(get_session),
    user_id: str
):

    return get_user_by_uuid_or_identifier(id=user_id, session=session)


# ---------------------
# Update a user by UUID
# ---------------------
@app.put("/user/{user_uuid}", response_model=UserRead)
def update_user(*, user_uuid: str, user: UserUpdate):

    # Get user by UUID
    user = User.get(uuid=user_uuid)

    # If user exists, update it
    if user:
        user.update(**user.dict())
        return user

    # If user doesn't exist, return 404
    else:
        raise HTTPException(status_code=404, detail=f'User {user_uuid} not found!')


# =============
# LLM ENDPOINTS
# =============


def process_webhook_telegram(webhook_data: dict):
    """
    Telegram example response:
    {
        "update_id": 248146407,
        "message": {
            "message_id": 299,
            "from": {
                "id": 123456789,
                "is_bot": false,
                "first_name": "Elon",
                "username": "elonmusk",
                "language_code": "en"
            },
            "chat": {
                "id": 123456789,
                "first_name": "Elon",
                "username": "elonmusk",
                "type": "private"
            },
            "date": 1683115867,
            "text": "Tell me about the company?"
        }
    }
    """
    message = webhook_data.get('message', None)
    chat = message.get('chat', None)
    message_from = message.get('from', None)
    return {
        'update_id': webhook_data.get('update_id', None),
        'message_id': message.get('message_id', None),
        'user_id': message_from.get('id', None),
        'username': message_from.get('username', None),
        'user_language': message_from.get('language_code', None),
        'user_firstname': chat.get('first_name', None),
        'user_message': message.get('text', None),
        'message_ts': datetime.fromtimestamp(message.get('date', None)) if message.get('date', None) else None,
        'message_type': chat.get('type', None)
    }


@app.post("/webhooks/{channel}/webhook")
def get_webhook(
    *,
    session: Session = Depends(get_session),
    channel: str,
    webhook: WebhookCreate
):
    webhook_data = webhook.dict()

    # --------------------
    # Get webhook metadata
    # --------------------
    if channel == 'telegram':
        rasa_webhook_url = f'{RASA_WEBHOOK_URL}/webhooks/{channel}/webhook'
        data = process_webhook_telegram(webhook_data)
        channel = CHANNEL_TYPE.TELEGRAM.value
        user_data = {
            'identifier': data['user_id'],
            'identifier_type': channel,
            'first_name': data['user_firstname'],
            'language': data['user_language']
        }
        session_metadata = {
            'update_id': data['update_id'],
            'username': data['username'],
            'message_id': data['user_message'],
            'msg_ts': data['message_ts'],
            'msg_type': data['message_type'],
        }
        user_message = data['user_message']
    else:
        # Not a valid channel, return 404
        raise HTTPException(status_code=404, detail=f'Channel {channel} not a valid webhook channel!')

    chat_session = chat_query(
        user_message,
        session=session,
        channel=channel,
        identifier=user_data['identifier'],
        user_data=user_data,
        meta=session_metadata
    )

    meta = chat_session.meta

    # -----------------------------------------
    # Lets add the LLM response to the metadata
    # -----------------------------------------
    webhook_data['message']['meta'] = {
        'response': chat_session.response if chat_session.response else None,
        'tags': meta['tags'] if 'tags' in meta else None,
        'is_escalate': meta['is_escalate'] if 'is_escalate' in meta else False,
        'session_id': meta['session_id'] if 'session_id' in meta else None

    }

    # -----------------------------------
    # Forward the webhook to Rasa webhook
    # -----------------------------------
    res = requests.post(rasa_webhook_url, data=json.dumps(webhook_data))
    logger.debug(f'[🤖 RasaGPT API webhook]\nPosting data: {json.dumps(webhook_data)}\n\n[🤖 RasaGPT API webhook]\nRasa webhook response: {res.text}')

    return {'status': 'ok'}


# ------------------
# Customize API docs
# ------------------
_schema = get_openapi(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    routes=app.routes,
)
_schema['info']['x-logo'] = {
    'url': '/static/img/rasagpt-logo-1.png'
}
app.openapi_schema = _schema