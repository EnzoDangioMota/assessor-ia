import os
from pathlib import Path

from dotenv import load_dotenv

# BASE_DIR aponta para migracao_fastAPI/. Montado a partir da localização
# do próprio arquivo: não depende da pasta de onde você rodou o uvicorn.
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"

load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return default

    value = value.strip().strip('"').strip("'")
    if not value or value.startswith("******") or value.lower() in {"none", "null"}:
        return default
    return value


FAQ_FILE_NAME = _env("FAQ_FILE_NAME", "FAQ_assessor_v1.1.pdf")
FAQ_PDF_PATH = DATA_DIR / FAQ_FILE_NAME

GEMINI_API_KEY = _env("GEMINI_API_KEY")
GROQ_API_KEY = _env("GROQ_API_KEY")
TYPESAFE_API_KEY = _env("TYPESAFE_API_KEY")
DATABASE_URL = _env("DATABASE_URL")
MONGODB_URI = _env("MONGODB_URI", "mongodb://localhost:27017")

# QDRANT CONFIG
QDRANT_API_KEY = _env("QDRANT_API_KEY")
QDRANT_URL = _env("QDRANT_URL")

GEMINI_MODEL = _env("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = _env("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
GROQ_MODEL = _env("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_MODEL_FAST = _env("GROQ_MODEL_FAST", GROQ_MODEL or "openai/gpt-oss-20b")
MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024

OBRIGATORIAS = {
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "GROQ_API_KEY":   GROQ_API_KEY,
    "DATABASE_URL":   DATABASE_URL,
    "MONGODB_URI":    MONGODB_URI,
}


def validar_config() -> list[str]:
    """Devolve a lista de problemas de configuração (vazia = tudo certo)."""
    problemas = []
    for nome, valor in OBRIGATORIAS.items():
        if not valor:
            problemas.append(f"Variável ausente no .env: {nome}")
    if not FAQ_PDF_PATH.exists():
        problemas.append(f"PDF do FAQ não encontrado em: {FAQ_PDF_PATH}")
    return problemas