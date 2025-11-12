
import sys
import os
import pytest
from sqlmodel import Session, SQLModel, create_engine
# Add the app directory to the sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from llm import chat_query, get_embeddings
from models import Organization, Project, Document, Node
from config import DATABASE_URL


# Create a test database
engine = create_engine(DATABASE_URL, echo=False)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

@pytest.fixture(name="session")
def session_fixture():
    create_db_and_tables()
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


def test_kekzal_side_effects_bug(session: Session):
    """
    This test reproduces the bug where the chatbot fails to answer a question
    about the side effects of Kekzal.
    """
    # 1. Create dummy organization and project
    org = Organization(display_name="Test Org", namespace="test-org")
    session.add(org)
    session.commit()
    session.refresh(org)

    project = Project(display_name="Test Project", organization_id=org.id)
    session.add(project)
    session.commit()
    session.refresh(project)

    # 2. Load the Kekzal document
    doc_path = "app/api/data/training_data/project-kekzal.md"
    with open(doc_path, "r") as f:
        doc_content = f.read()

    doc = Document(
        display_name="project-kekzal.md",
        project_id=project.id,
        organization_id=org.id,
        data=doc_content,
        hash="testhash",
        version=1,
    )
    session.add(doc)
    session.commit()
    session.refresh(doc)

    # 3. Create embeddings for the document
    arr_documents, embeddings = get_embeddings(doc_content)
    for i, (doc_chunk, embedding) in enumerate(zip(arr_documents, embeddings)):
        node = Node(
            document_id=doc.id,
            text=doc_chunk,
            embeddings=embedding,
            node_order=i,
        )
        session.add(node)
    session.commit()


    # 4. Ask the question about side effects
    response = chat_query(
        query_str="What are the side effects of Kekzal?",
        session=session,
        project=project,
        organization=org,
    )

    # 5. Assert that the response is correct
    correct_response = "Some potential side effects of Kekzal may include"
    assert correct_response in response.response
