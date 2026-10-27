from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.documents import buscar_documentos


class ConsultarArquivosArgs(BaseModel):
    pergunta: str = Field(
        description="Pergunta específica a ser respondida com os arquivos enviados."
    )


@tool("consultar_arquivos_usuario", args_schema=ConsultarArquivosArgs)
def consultar_arquivos_usuario(
    pergunta: str, config: RunnableConfig = None
) -> list[dict]:
    """Busca trechos relevantes nos arquivos enviados pelo próprio usuário."""
    configuravel = (config or {}).get("configurable", {})
    user_id = configuravel.get("user_id")
    if not user_id:
        return [{"erro": "Não foi possível identificar o usuário da consulta."}]
    return buscar_documentos(user_id, pergunta)
