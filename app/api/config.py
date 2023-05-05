from enum import Enum, IntEnum
from dotenv import load_dotenv
from pathlib import Path
import logging
import sys
import os

# -------
# Logging
# -------

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.getLogger().addHandler(logging.StreamHandler(stream=sys.stdout))
logger = logging.getLogger(__name__)

# ----------------
# Environment vars
# ----------------
env = os.getenv("ENV", None)

if not env:
    # Check up to 2 levels up for .env-{env} file
    env_file = Path(__file__).parent.parent.parent / '.env'
    logger.debug(f"Loading env file: {env_file}")
    if os.path.exists(env_file):
        load_dotenv(dotenv_path=env_file)
    else:
        raise Exception(f"Env file {env})file not found")

# -----------------------
# Configuration constants
# -----------------------
readme_file = Path(__file__).parent / "API.md"

readme_str = (
    f"""
<details>
    <summary>📕 API.MD</summary>
{readme_file.read_text()}

</details>

"""
    if readme_file.exists()
    else ""
)
APP_NAME = "API Documentation"
APP_VERSION = "0.0.1"
APP_DESCRIPTION = f"""
![img](/static/img/rasagpt-logo-1.png)

---
## About
💬 RasaGPT is the first headless LLM chatbot platform built on top of Rasa and Langchain

- 📚 Resources: [https://rasagpt.dev](https://rasagpt.dev)
- 🧑‍💻 Github: [https://github.com/paulpierre/RasaGPT](https://github.com/paulpierre/RasaGPT)
- 🧙 Author: [@paulpierre](https://twitter.com/paulpierre)

{readme_str}
"""
APP_ICON = "/public/img/rasagpt-icon-200x200.png"
APP_LOGO = "/public/img/rasagpt-logo-1.png"

FILE_UPLOAD_PATH = os.getenv("FILE_UPLOAD_PATH", "/tmp")

# Database configurations
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", 5432)
DB_USER = os.getenv("DB_USER")
DB_NAME = os.getenv("DB_NAME")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DSN = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
SU_DSN = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

RASA_WEBHOOK_HOST = os.getenv("RASA_WEBHOOK_HOST", "rasa-core")
RASA_WEBHOOK_PORT = os.getenv("RASA_WEBHOOK_PORT", 5005)
RASA_WEBHOOK_URL = f"http://{RASA_WEBHOOK_HOST}:{RASA_WEBHOOK_PORT}"

# LLM configurations
MODEL_NAME = os.getenv("MODEL_NAME")
LLM_DEFAULT_TEMPERATURE = float(os.getenv("LLM_DEFAULT_TEMPERATURE", 0.0))
LLM_CHUNK_SIZE = int(os.getenv("LLM_CHUNK_SIZE", 512))
LLM_CHUNK_OVERLAP = int(os.getenv("LLM_CHUNK_OVERLAP", 20))
LLM_DISTANCE_THRESHOLD = float(os.getenv("LLM_DISTANCE_THRESHOLD", 0.5))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", 256))
LLM_MIN_NODE_LIMIT = int(os.getenv("LLM_MIN_NODE_LIMIT", 3))


class DISTANCE_STRATEGY(Enum):
    COSINE = "cosine"
    EUCLIDEAN = "euclidean"
    MAX_INNER_PRODUCT = "max_inner_product"

    def __new__(cls, strategy_name: str):
        obj = object.__new__(cls)
        obj._value_ = strategy_name
        return obj

    @property
    def strategy_name(self) -> str:
        return self.value


DISTANCE_STRATEGIES = [
    (
        DISTANCE_STRATEGY.EUCLIDEAN,
        "euclidean",
        "<->",
        "CREATE INDEX ON node USING ivfflat (embeddings vector_l2_ops) WITH (lists = 100);",
    ),
    (
        DISTANCE_STRATEGY.COSINE,
        "cosine",
        "<=>",
        "CREATE INDEX ON node USING ivfflat (embeddings vector_cosine_ops) WITH (lists = 100);",
    ),
    (
        DISTANCE_STRATEGY.MAX_INNER_PRODUCT,
        "max_inner_product",
        "<#>",
        "CREATE INDEX ON node USING ivfflat (embeddings vector_ip_ops) WITH (lists = 100);",
    ),
]
LLM_DEFAULT_DISTANCE_STRATEGY = DISTANCE_STRATEGY[
    os.getenv("LLM_DEFAULT_DISTANCE_STRATEGY", "COSINE")
]
VECTOR_EMBEDDINGS_COUNT = 1536
PGVECTOR_ADD_INDEX = True if os.getenv("PGVECTOR_ADD_INDEX", False) else False
# Model constants

DOCUMENT_TYPE = IntEnum("DOCUMENT_TYPE", ["PLAINTEXT", "MARKDOWN", "HTML", "PDF"])

ENTITY_STATUS = IntEnum(
    "ENTITY_STATUS",
    ["UNVERIFIED", "ACTIVE", "INACTIVE", "DELETED", "BANNED" "DEPRECATED"],
)
CHANNEL_TYPE = IntEnum(
    "CHANNEL_TYPE", ["SMS", "TELEGRAM", "WHATSAPP", "EMAIL", "WEBSITE"]
)

AGENT_NAMES = [
    "Aisha",
    "Lilly",
    "Hanna",
    "Julia",
    "Emily",
    "Sophia",
    "Alex",
    "Isabella",
]


class LLM_MODELS(Enum):
    TEXT_DAVINCI_003 = "text-davinci-003", 4097
    GPT_35_TURBO = "gpt-3.5-turbo", 4096
    TEXT_DAVINCI_002 = "text-davinci-002", 4097
    CODE_DAVINCI_002 = "code-davinci-002", 8001
    GPT_4 = "gpt-4", 8192
    GPT_4_32K = "gpt-4-32k", 32768

    def __init__(self, model_name, token_limit):
        self._model_name = model_name
        self._token_limit = token_limit

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def token_limit(self) -> int:
        return self._token_limit
