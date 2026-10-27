"""
Cliente Qdrant e função de embedding — centralizados aqui.

Dois consumidores:
  - memory.py   → salva/busca resumos na collection "memoria_resumos"
  - tools/faq.py → busca chunks do PDF na collection "faq_chunks"

O modelo de embedding é o mesmo para ambos (gemini-embedding-2-preview, 768d),
então instanciamos uma vez só.
"""

from qdrant_client import QdrantClient, models
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from app.config import (
    GEMINI_API_KEY,
    QDRANT_API_KEY,
    QDRANT_URL,
)

qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

COLLECTION_MEMORIA = "memoria_resumos"
COLLECTION_FAQ     = "faq_chunks"
COLLECTION_PERFIL  = "perfil_preferencias"
COLLECTION_DOCUMENTOS = "documentos_usuario"
EMBEDDING_DIM      = 768

_embeddings = GoogleGenerativeAIEmbeddings(
    model="gemini-embedding-2-preview",
    google_api_key=GEMINI_API_KEY,
)


def gerar_embedding(texto: str) -> list[float]:
    """Gera um vetor de 768 dimensões para o texto informado."""
    return _embeddings.embed_query(texto, output_dimensionality=EMBEDDING_DIM)


def gerar_embeddings_batch(textos: list[str]) -> list[list[float]]:
    """Gera embeddings para uma lista de textos de uma vez (mais eficiente)."""
    return _embeddings.embed_documents(textos, output_dimensionality=EMBEDDING_DIM)


def garantir_collection(nome: str) -> None:
    """Cria a collection no Qdrant se ela ainda não existir. Idempotente:
    não recria nem apaga nada se ela já estiver lá."""
    if not qdrant.collection_exists(nome):
        qdrant.create_collection(
            collection_name=nome,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIM, distance=models.Distance.COSINE
            ),
        )