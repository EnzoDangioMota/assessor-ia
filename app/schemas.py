from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """O que o navegador envia no POST /chat."""

    session_id: str = Field(
        ...,
        description="Identifica a conversa (UUID gerado pelo front a cada sessão).",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    user_id: str = Field(
        default="usuario_teste",
        description="Identifica o usuário de forma estável entre sessões. "
                    "É o que permite a memória de longo prazo funcionar.",
        examples=["usuario_teste"],
    )
    pergunta: str = Field(
        ...,
        min_length=1,
        description="A mensagem do usuário — o que antes vinha do input().",
        examples=["gastei 50 reais no mercado hoje"],
    )


class ChatResponse(BaseModel):
    """O que a API devolve no POST /chat."""
    resposta:         str
    agentes_chamados: list[str] = Field(default_factory=list)


class SessionResponse(BaseModel):
    """Ainda não é usado — é do Passo 6 da Etapa 3."""
    session_id: str
    resumo:     str | None = None


class PerfilRequest(BaseModel):
    """Contrato exato que a tela Perfil envia. Não renomear campos nem
    afrouxar tipos: é a tela que se ajusta a este contrato, e não o
    contrário — então ele é reproduzido aqui como veio no enunciado."""

    user_id: str = Field(
        ...,
        min_length=1,
        description="Identificador estável do usuário — o mesmo que o chat usa.",
        examples=["usuario_teste"],
    )
    renda_mensal: float = Field(
        ...,
        gt=0,
        description="Renda mensal em reais. Precisa ser maior que zero.",
        examples=[4200],
    )
    objetivo: str = Field(
        ...,
        min_length=1,
        description="Objetivo financeiro, em uma frase curta.",
        examples=["juntar para viagem em dezembro"],
    )
    tolerancia_risco: Literal["baixa", "media", "alta"] = Field(
        ...,
        description='Somente "baixa", "media" ou "alta".',
    )
    preferencias: str = Field(
        ...,
        min_length=1,
        description="Texto livre com planos, restrições e preferências do usuário.",
        examples=[
            "quero juntar para uma viagem a João Pessoa em dezembro; "
            "não quero investimento agressivo."
        ],
    )


class PerfilResponse(PerfilRequest):
    """O que o POST /perfil devolve: o próprio perfil gravado — é assim
    que a tela confirma que o salvamento funcionou."""
    atualizado_em: datetime