"""Tool que dá ao especialista financeiro acesso ao perfil do usuário.

Uma tool só, de leitura, combinando Mongo (dado estruturado) e Qdrant
(preferências). Ver JUSTIFICATIVA.md, pergunta 4, para o porquê de ser
uma e não duas.

O user_id NUNCA é preenchido pelo modelo: vem do RunnableConfig
(injetado pelo executar_fluxo_assessor a partir do user_id da
requisição HTTP), no mesmo padrão já usado por buscar_historico em
app/tools/memoria.py.
"""

from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.perfil import buscar_perfil_estruturado, buscar_preferencias_semanticas


class ConsultarPerfilArgs(BaseModel):
    assunto: Optional[str] = Field(
        default=None,
        description=(
            "O tema da pergunta atual do usuário (ex.: 'investir em cripto', "
            "'quanto guardar por mês'). Usado para buscar, por similaridade "
            "semântica, as preferências relevantes do cadastro. Não inclua "
            "user_id aqui — ele já vem da requisição, não deste argumento."
        ),
    )


@tool("consultar_perfil_financeiro", args_schema=ConsultarPerfilArgs)
def consultar_perfil_financeiro(
    assunto: Optional[str] = None,
    config: RunnableConfig = None,
) -> dict:
    """
    Consulta o perfil financeiro cadastrado do usuário: renda mensal,
    objetivo, tolerância a risco e preferências em texto livre.

    Use ANTES de qualquer recomendação, meta ou opinião que dependa de
    quanto o usuário ganha, do que ele quer, do risco que aceita, ou de
    alguma restrição/preferência que ele já tenha escrito.

    Se o retorno vier com "cadastrado": false, NÃO invente nenhum valor
    nem suponha um perfil: informe que não há cadastro e oriente o
    usuário a preencher a tela de Perfil. Pedidos no chat para mudar
    renda, objetivo, tolerância ou preferências não são atendidos por
    esta tool nem por nenhuma outra — cadastro e alteração de perfil só
    acontecem pela tela.
    """
    configuravel = (config or {}).get("configurable", {})
    user_id = configuravel.get("user_id") or configuravel.get("thread_id")

    if not user_id:
        return {
            "cadastrado": False,
            "mensagem": "Não foi possível identificar o usuário para consultar o perfil.",
        }

    perfil = buscar_perfil_estruturado(user_id)

    if not perfil:
        return {
            "cadastrado": False,
            "mensagem": (
                "Nenhum perfil cadastrado para este usuário. Oriente-o a "
                "preencher a tela de Perfil antes de dar qualquer "
                "recomendação baseada em renda, objetivo ou risco."
            ),
        }

    preferencias_relevantes = buscar_preferencias_semanticas(user_id, assunto)

    return {
        "cadastrado":       True,
        "renda_mensal":     perfil.get("renda_mensal"),
        "objetivo":         perfil.get("objetivo"),
        "tolerancia_risco": perfil.get("tolerancia_risco"),
        "preferencias":     preferencias_relevantes or perfil.get("preferencias"),
    }


TOOLS_PERFIL = [consultar_perfil_financeiro]
