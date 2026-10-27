"""
=================
Perfil financeiro do usuário
-----------------------------
Guarda dois tipos de dado, em dois bancos diferentes, escritos a partir
do MESMO ponto de entrada: salvar_perfil(), chamada pela rota POST /perfil.

  - Estruturado (renda_mensal, objetivo, tolerancia_risco)
    → MongoDB, collection "perfis".
    O _id do documento É o user_id: salvar de novo com o mesmo user_id
    substitui o documento inteiro (upsert por replace_one), nunca cria
    um segundo registro.

  - Texto livre (preferencias)
    → Qdrant, collection "perfil_preferencias".
    Um ponto por usuário. O id do ponto é derivado deterministicamente
    do user_id (uuid5): o mesmo usuário sempre cai no mesmo ponto, então
    salvar de novo SUBSTITUI o vetor e o payload antigos — o texto de
    preferências anterior não sobrevive ao lado do novo.

Este módulo só GRAVA e CONSULTA por user_id. Não existe listagem nem
exclusão — não é pedido, e não tem rota que exponha isso.

Quem lê esses dados para aconselhar é a tool do especialista financeiro,
em app/tools/perfil.py — não há endpoint de leitura HTTP.
"""

import uuid
from datetime import datetime, timezone

from pymongo import MongoClient
from qdrant_client import models

from app.config import MONGODB_URI
from app.vectorstore import (
    COLLECTION_PERFIL,
    gerar_embedding,
    garantir_collection,
    qdrant,
)

COLLECTION_MONGO_PERFIS = "perfis"

# ==============================================================================
# CONEXÃO MONGO
# ==============================================================================
_col_perfis = None


def _get_col_perfis():
    global _col_perfis
    if _col_perfis is None:
        try:
            _mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
            _mongo.admin.command("ping")
            db = _mongo["assessor"]
            _col_perfis = db[COLLECTION_MONGO_PERFIS]
        except Exception:
            _col_perfis = None
    return _col_perfis


# Garante que a collection do Qdrant já existe assim que o módulo é
# carregado — ou seja, na subida da API — e não só quando alguém
# consultar pela primeira vez. Também garante o índice de payload em
# "user_id": sem ele, o Qdrant recusa (400) qualquer query_filter que
# tente filtrar por esse campo — e é exatamente esse filtro que impede
# o perfil de um usuário aparecer para outro (pergunta 5 da
# JUSTIFICATIVA.md). Não fatal: se o Qdrant estiver temporariamente
# fora do ar na subida, a API ainda sobe; a escrita via POST /perfil
# tentará de novo e vai falhar de forma visível (503), não em silêncio.
try:
    garantir_collection(COLLECTION_PERFIL)
    qdrant.create_payload_index(
        collection_name=COLLECTION_PERFIL,
        field_name="user_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
except Exception as _erro:
    print(f"[perfil] ATENÇÃO: não foi possível garantir a collection/índice do Qdrant: {_erro}")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _ponto_id(user_id: str) -> str:
    """UUID determinístico a partir do user_id: o mesmo usuário sempre
    gera o mesmo id de ponto, então um novo upsert SUBSTITUI o ponto
    anterior em vez de duplicar."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"perfil:{user_id}"))


# ==============================================================================
# ESCRITA — chamada pela rota POST /perfil (único ponto de entrada)
# ==============================================================================
def salvar_perfil(
    user_id: str,
    renda_mensal: float,
    objetivo: str,
    tolerancia_risco: str,
    preferencias: str,
) -> dict:
    """
    Grava o perfil nos dois bancos a partir do mesmo ponto de entrada.
    Upsert nos dois: mesmo user_id atualiza, nunca duplica, e o dado
    antigo não sobrevive ao lado do novo.
    """
    agora = _agora()

    documento = {
        "_id":              user_id,
        "user_id":          user_id,
        "renda_mensal":     renda_mensal,
        "objetivo":         objetivo,
        "tolerancia_risco": tolerancia_risco,
        "preferencias":     preferencias,
        "atualizado_em":    agora,
    }

    # --- MongoDB: dado estruturado. replace_one troca o documento
    # inteiro (não faz merge de campos), então nada do cadastro antigo
    # sobra junto do novo. ---
    collection = _get_col_perfis()
    if collection is None:
        raise RuntimeError("MongoDB indisponível: não foi possível gravar o perfil.")
    collection.replace_one({"_id": user_id}, documento, upsert=True)

    # --- Qdrant: texto livre. upsert com id determinístico substitui o
    # ponto (vetor + payload) do usuário por completo. ---
    vetor = gerar_embedding(preferencias)
    qdrant.upsert(
        collection_name=COLLECTION_PERFIL,
        points=[
            models.PointStruct(
                id=_ponto_id(user_id),
                vector=vetor,
                payload={
                    "user_id":       user_id,
                    "preferencias":  preferencias,
                    "atualizado_em": agora.isoformat(),
                },
            )
        ],
    )

    return documento


# ==============================================================================
# LEITURA — chamada apenas pela tool do especialista financeiro
# ==============================================================================
def buscar_perfil_estruturado(user_id: str) -> dict | None:
    """Consulta direta por usuário no Mongo. None se não houver cadastro
    (ou se o Mongo estiver indisponível — o chamador trata os dois casos
    da mesma forma: 'não invente, oriente a usar a tela')."""
    collection = _get_col_perfis()
    if collection is None:
        return None
    return collection.find_one({"_id": user_id})


def buscar_preferencias_semanticas(user_id: str, assunto: str | None) -> str | None:
    """
    Busca semântica das preferências do usuário no Qdrant, sempre
    filtrada por user_id — isso é o que impede o perfil de um usuário
    de aparecer para outro. Se `assunto` vier vazio, usa uma consulta
    genérica só para recuperar o texto cadastrado.
    """
    texto_busca = (
        assunto.strip()
        if assunto and assunto.strip()
        else "preferências, planos e restrições financeiras do usuário"
    )
    vetor = gerar_embedding(texto_busca)

    resultados = qdrant.query_points(
        collection_name=COLLECTION_PERFIL,
        query=vetor,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                )
            ]
        ),
        limit=1,
    )

    if not resultados.points:
        return None

    return resultados.points[0].payload.get("preferencias")