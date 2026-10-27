from fastapi import APIRouter

from app.graph import executar_fluxo_assessor
from app.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def conversar(requisicao: ChatRequest) -> ChatResponse:
    
    """Recebe uma mensagem do usuário e devolve a resposta do assessor."""
    resposta = executar_fluxo_assessor(
        requisicao.pergunta, requisicao.session_id, requisicao.user_id
    )
    return ChatResponse(resposta=resposta)