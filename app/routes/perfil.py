"""Rota de escrita do perfil financeiro do usuário.

Só existe POST. Não há leitura, listagem nem exclusão — fora de escopo
por definição do enunciado. A resposta do POST é o próprio perfil
gravado: é assim que a tela confirma que o salvamento funcionou.
"""

from fastapi import APIRouter, HTTPException

from app.perfil import salvar_perfil
from app.schemas import PerfilRequest, PerfilResponse

router = APIRouter(tags=["perfil"])


@router.post("/perfil", response_model=PerfilResponse)
def gravar_perfil(requisicao: PerfilRequest) -> PerfilResponse:
    """
    Grava se o user_id não existir, caso contrário atualiza o perfil financeiro do
    usuário nos dois bancos, o MongoDB para o dado estruturado e Qdrant
    para as preferências em texto livre, a partir desse único ponto de
    entrada. Dado inválido nunca chega aqui porque é recusado antes, na
    validação do PerfilRequest (422), porque dái  não vira erro interno.
    """
    try:
        documento = salvar_perfil(
            user_id=requisicao.user_id,
            renda_mensal=requisicao.renda_mensal,
            objetivo=requisicao.objetivo,
            tolerancia_risco=requisicao.tolerancia_risco,
            preferencias=requisicao.preferencias,
        )
    except Exception as erro:
        # Falha de infraestrutura (Mongo/Qdrant fora do ar), não dado
        # inválido — isso já foi recusado pelo Pydantic antes de chegar
        # aqui. Reportamos como indisponibilidade, não como 500 opaco.
        raise HTTPException(
            status_code=503,
            detail=f"Não foi possível gravar o perfil agora: {erro}",
        )

    return PerfilResponse(
        user_id=documento["user_id"],
        renda_mensal=documento["renda_mensal"],
        objetivo=documento["objetivo"],
        tolerancia_risco=documento["tolerancia_risco"],
        preferencias=documento["preferencias"],
        atualizado_em=documento["atualizado_em"],
    )
