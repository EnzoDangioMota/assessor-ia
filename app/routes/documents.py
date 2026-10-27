from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.config import MAX_DOCUMENT_SIZE_BYTES
from app.documents import excluir_documento, listar_documentos, salvar_documento

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    document_id: str
    file_name: str
    chunks: int
    uploaded_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]


@router.post("", response_model=DocumentResponse)
def enviar_documento(
    user_id: str = Query(default="usuario_teste", min_length=1),
    arquivo: UploadFile = File(...),
) -> DocumentResponse:
    conteudo = arquivo.file.read(MAX_DOCUMENT_SIZE_BYTES + 1)
    arquivo.file.close()
    if len(conteudo) > MAX_DOCUMENT_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="O arquivo excede o limite de 10 MB.")
    try:
        resultado = salvar_documento(user_id, arquivo.filename or "", conteudo)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from erro
    return DocumentResponse(**resultado)


@router.get("", response_model=DocumentListResponse)
def obter_documentos(
    user_id: str = Query(default="usuario_teste", min_length=1),
) -> DocumentListResponse:
    return DocumentListResponse(
        documents=[DocumentResponse(**item) for item in listar_documentos(user_id)]
    )


@router.delete("/{document_id}")
def remover_documento(
    document_id: str,
    user_id: str = Query(default="usuario_teste", min_length=1),
) -> dict:
    removido = excluir_documento(user_id, document_id)
    if not removido:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return {"document_id": document_id, "removido": True}
