import random
import openai
import json

from langchain.docstore.document import Document as LangChainDocument
from langchain.embeddings.openai import OpenAIEmbeddings
from fastapi import HTTPException
from uuid import UUID, uuid4
from langchain.text_splitter import (
    CharacterTextSplitter,
    MarkdownTextSplitter
)
from sqlmodel import (
    Session,
    text
)
from util import (
    sanitize_input,
    sanitize_output
)
from langchain import OpenAI
from typing import (
    List,
    Union,
    Optional,
    Dict,
    Tuple,
    Any
)
from helpers import (
    get_user_by_uuid_or_identifier,
    get_chat_session_by_uuid
)
from models import (
    User,
    Organization,
    Project,
    Node,
    ChatSession,
    ChatSessionResponse,
    get_engine
)
from config import (
    CHANNEL_TYPE,
    DOCUMENT_TYPE,
    LLM_MODELS,
    LLM_DISTANCE_THRESHOLD,
    LLM_DEFAULT_TEMPERATURE,
    LLM_MAX_OUTPUT_TOKENS,
    LLM_CHUNK_SIZE,
    LLM_CHUNK_OVERLAP,
    LLM_MIN_NODE_LIMIT,
    LLM_DEFAULT_DISTANCE_STRATEGY,
    VECTOR_EMBEDDINGS_COUNT,
    DISTANCE_STRATEGY,
    AGENT_NAMES,
    logger
)


# -------------
# Query the LLM
# -------------
def chat_query(
    query_str: str,
    session_id: Optional[Union[str, UUID]] = None,
    meta: Optional[Dict[str, Any]] = {},
    channel: Optional[CHANNEL_TYPE] = None,
    identifier: Optional[str] = None,
    project: Optional[Project] = None,
    organization: Optional[Organization] = None,
    session: Optional[Session] = None,
    user_data: Optional[Dict[str, Any]] = None,
    distance_strategy: Optional[DISTANCE_STRATEGY] = DISTANCE_STRATEGY.EUCLIDEAN,
    distance_threshold: Optional[float] = LLM_DISTANCE_THRESHOLD,
    node_limit: Optional[int] = LLM_MIN_NODE_LIMIT,
    model: Optional[LLM_MODELS] = LLM_MODELS.GPT_35_TURBO,
    max_output_tokens: Optional[int] = LLM_MAX_OUTPUT_TOKENS,
) -> ChatSessionResponse:
    """
    Steps:
        1. ✅ Clean user input
        2. ✅ Create input embeddings
        3. ✅ Search for similar nodes
        4. ✅ Create prompt template w/ similar nodes
        5. ✅ Submit prompt template to LLM
        6. ✅ Get response from LLM
        7. Create ChatSession
            - Store embeddings
            - Store tags
            - Store is_escalate
        8. Return response
    """
    meta = {}
    agent_name = None
    embeddings = []
    tags = []
    is_escalate = False
    response_message = None
    prompt = None
    context_str = None
    MODEL_TOKEN_LIMIT = (
        model.token_limit if isinstance(model, OpenAI) else LLM_MAX_OUTPUT_TOKENS
    )

    # ---------------------------------------------
    # Generate a new session ID if none is provided
    # ---------------------------------------------
    prev_chat_session = (
        get_chat_session_by_uuid(session_id=session_id, session=session)
        if session_id
        else None
    )

    # If we were given an invalid session_id
    if session_id and not prev_chat_session:
        return HTTPException(
            status_code=404, detail=f"Chat session with ID {session_id} not found."
        )
    # If we were given a valid session_id
    elif session_id and prev_chat_session and prev_chat_session.meta.get("agent"):
        agent_name = prev_chat_session.meta["agent"]
    # If this is a new session, generate a new ID
    else:
        session_id = str(uuid4())

    meta["agent"] = agent_name if agent_name else random.choice(AGENT_NAMES)

    # ----------------
    # Clean user input
    # ----------------
    query_str = sanitize_input(query_str)
    logger.debug(f"💬 Query received: {query_str}")

    # ----------------
    # Get token counts
    # ----------------
    query_token_count = get_token_count(query_str)
    prompt_token_count = 0

    # -----------------------
    # Create input embeddings
    # -----------------------
    arr_query, embeddings = get_embeddings(query_str)

    query_embeddings = embeddings[0]

    # ------------------------
    # Search for similar nodes
    # ------------------------
    nodes = get_nodes_by_embedding(
        query_embeddings,
        node_limit,
        distance_strategy=distance_strategy
        if isinstance(distance_strategy, DISTANCE_STRATEGY)
        else LLM_DEFAULT_DISTANCE_STRATEGY,
        distance_threshold=distance_threshold,
        session=session,
    )

    if len(nodes) > 0:
        if (not project or not organization) and session:
            # get document from Node via session object:
            document = session.get(Node, nodes[0].id).document
            project = document.project
            organization = project.organization

        # ----------------------
        # Create prompt template
        # ----------------------

        # concatenate all nodes into a single string
        context_str = "\n\n".join([node.text for node in nodes])

        # -------------------------------------------
        # Let's make sure we don't exceed token limit
        # -------------------------------------------
        context_token_count = get_token_count(context_str)

        # ----------------------------------------------
        # if token count exceeds limit, truncate context
        # ----------------------------------------------
        if (
            context_token_count + query_token_count + prompt_token_count
        ) > MODEL_TOKEN_LIMIT:
            logger.debug("🚧 Exceeded token limit, truncating context")
            token_delta = MODEL_TOKEN_LIMIT - (query_token_count + prompt_token_count)
            context_str = context_str[:token_delta]

        # create prompt template
        system_prompt, user_prompt = get_prompt_template(
            user_query=query_str,
            context_str=context_str,
            project=project,
            organization=organization,
            agent=agent_name,
        )

        prompt_token_count = get_token_count(prompt)
        token_count = context_token_count + query_token_count + prompt_token_count

        # ---------------------------
        # Get response from LLM model
        # ---------------------------
        # It should return a JSON dict
        llm_response = json.loads(
            retrieve_llm_response(
                user_prompt,
                model=model,
                max_output_tokens=max_output_tokens,
                prefix_messages=system_prompt,
            )
        )
        tags = llm_response.get("tags", [])
        is_escalate = llm_response.get("is_escalate", False)
        response_message = llm_response.get("message", None)
    else:
        logger.info("🚫📝 No similar nodes found, returning default response")

    # ----------------
    # Get user details
    # ----------------
    user = get_user_by_uuid_or_identifier(
        identifier, session=session, should_except=False
    )

    if not user:
        logger.debug("🚫👤 User not found, creating new user")
        user_params = {
            "identifier": identifier,
            "identifier_type": channel.value
            if isinstance(channel, CHANNEL_TYPE)
            else channel,
        }
        if user_data:
            user_params = {**user_params, **user_data}

        user = User.create(user_params)
    else:
        logger.debug(f"👤 User found: {user}")

    # -----------------------------------
    # Calculate input and response tokens
    # -----------------------------------
    token_count = get_token_count(prompt) + get_token_count(response_message)

    # ---------------
    # Add to meta tag
    # ---------------
    if tags:
        meta["tags"] = tags

    meta["is_escalate"] = is_escalate

    if session_id:
        meta["session_id"] = session_id

    chat_session = ChatSession(
        user_id=user.id,
        session_id=session_id,
        project_id=project.id if project else None,
        channel=channel.value if isinstance(channel, CHANNEL_TYPE) else channel,
        user_message=query_str,
        embeddings=query_embeddings,
        token_count=token_count if token_count > 0 else None,
        response=response_message,
        meta=meta,
    )

    if session:
        session.add(chat_session)
        session.commit()
        session.refresh(chat_session)

    else:
        with Session(get_engine()) as session:
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)

    return chat_session


# ------------------------------
# Retrieve a random agent's name
# ------------------------------
def get_random_agent():
    return random.choice(AGENT_NAMES)


# ------------------------
# Retrieve prompt template
# ------------------------
def get_prompt_template(
    user_query: str = None,
    context_str: str = None,
    project: Optional[Project] = None,
    organization: Optional[Organization] = None,
    agent: str = None,
) -> str:
    agent = f"{agent}, " if agent else ""
    user_query = user_query if user_query else ""
    context_str = context_str if context_str else ""
    organization = (
        project.organization.display_name
        if project
        else organization.display_name
        if organization
        else None
    )

    if not context_str or not user_query:
        raise ValueError(
            "Missing required arguments context_str, user_query, organization, agent"
        )

    system_prompt = [
        {
            "role": "system",
            "content": f"""[AGENT]:
I am {agent} a very kind and enthusiastic customer support agent who loves to help customers. I am working on the behalf of "{organization}"

Given the following document from "{organization}", I will answer the [USER] questions using only the [DOCUMENT] and following the [RULES].

[DOCUMENT]:
{context_str}

[RULES]:
I will answer the user's questions using only the [DOCUMENT] provided. I will abide by the following rules:
- I am a kind and helpful human, the best customer support agent in existence
- I never lie or invent answers not explicitly provided in [DOCUMENT]
- If I am unsure of the answer response or the answer is not explicitly contained in [DOCUMENT], I will say: "I apologize, I'm not sure how to help with that".
- I always keep my answers short, relevant and concise.
- I will always respond in JSON format with the following keys: "message" my response to the user, "tags" an array of short labels categorizing user input, "is_escalate" a boolean, returning false if I am unsure and true if I do have a relevant answer
""",
        }
    ]

    return (system_prompt, f"[USER]:\n{user_query}")


# ----------------------------
# Get the count of tokens used
# ----------------------------
# https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def get_token_count(text: str):
    if not text:
        return 0

    return OpenAI().get_num_tokens(text=text)


# --------------------------------------------
# Query embedding search for similar documents
# --------------------------------------------
def get_nodes_by_embedding(
    embeddings: List[float],
    k: int = LLM_MIN_NODE_LIMIT,
    distance_strategy: Optional[DISTANCE_STRATEGY] = LLM_DEFAULT_DISTANCE_STRATEGY,
    distance_threshold: Optional[float] = LLM_DISTANCE_THRESHOLD,
    session: Optional[Session] = None,
) -> List[Node]:
    # Convert embeddings array into sql string
    embeddings_str = str(embeddings)

    if distance_strategy == DISTANCE_STRATEGY.EUCLIDEAN:
        distance_fn = "match_node_euclidean"
    elif distance_strategy == DISTANCE_STRATEGY.COSINE:
        distance_fn = "match_node_cosine"
    elif distance_strategy == DISTANCE_STRATEGY.MAX_INNER_PRODUCT:
        distance_fn = "match_node_max_inner_product"
    else:
        raise Exception(f"Invalid distance strategy {distance_strategy}")

    # ---------------------------
    # Lets do a similarity search
    # ---------------------------
    sql = f"""SELECT * FROM {distance_fn}(
    '{embeddings_str}'::vector({VECTOR_EMBEDDINGS_COUNT}),
    {float(distance_threshold)}::double precision,
    {int(k)});"""

    # logger.debug(f'🔍 Query: {sql}')

    # Execute query, convert results to Node objects
    if not session:
        with Session(get_engine()) as session:
            nodes = session.exec(text(sql)).all()
    else:
        nodes = session.exec(text(sql)).all()

    return [Node.by_uuid(str(node[0])) for node in nodes] if nodes else []


# --------------
# Queries OpenAI
# --------------
def retrieve_llm_response(
    query_str: str,
    model: Optional[LLM_MODELS] = LLM_MODELS.GPT_35_TURBO,
    temperature: Optional[float] = LLM_DEFAULT_TEMPERATURE,
    max_output_tokens: Optional[int] = LLM_MAX_OUTPUT_TOKENS,
    prefix_messages: Optional[List[dict]] = None,
):
    llm = OpenAI(
        temperature=temperature,
        model_name=model.model_name
        if isinstance(model, LLM_MODELS)
        else LLM_MODELS.GPT_35_TURBO.model_name,
        max_tokens=max_output_tokens,
        prefix_messages=prefix_messages,
    )
    try:
        result = llm(prompt=query_str)
    except openai.error.InvalidRequestError as e:
        logger.error(f"🚨 LLM error: {e}")
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")
    logger.debug(f"💬 LLM result: {str(result)}")
    return sanitize_output(result)


# --------------------------
# Create document embeddings
# --------------------------
def get_embeddings(
    document_data: str,
    document_type: DOCUMENT_TYPE = DOCUMENT_TYPE.PLAINTEXT,
) -> Tuple[List[str], List[float]]:
    documents = [LangChainDocument(page_content=document_data)]

    logger.debug(documents)
    if document_type == DOCUMENT_TYPE.MARKDOWN:
        doc_splitter = MarkdownTextSplitter(
            chunk_size=LLM_CHUNK_SIZE, chunk_overlap=LLM_CHUNK_OVERLAP
        )
    else:
        doc_splitter = CharacterTextSplitter(
            chunk_size=LLM_CHUNK_SIZE, chunk_overlap=LLM_CHUNK_OVERLAP
        )

    # Returns an array of Documents
    split_documents = doc_splitter.split_documents(documents)

    # Lets convert them into an array of strings for OpenAI
    arr_documents = [doc.page_content for doc in split_documents]

    # https://github.com/hwchase17/langchain/blob/d18b0caf0e00414e066c9903c8df72bb5bcf9998/langchain/embeddings/openai.py#L219
    embed_func = OpenAIEmbeddings()

    embeddings = embed_func.embed_documents(
        texts=arr_documents, chunk_size=LLM_CHUNK_SIZE
    )

    return arr_documents, embeddings