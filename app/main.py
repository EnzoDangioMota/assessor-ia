from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import FRONTEND_DIR, validar_config
from app.routes.chat import router
from app.routes.documents import router as documents_router
from app.routes.monitor import router as monitor_router
from app.routes.perfil import router as perfil_router
from app.routes.sessions import router as sessions_router

for _problema in validar_config():
    print(f"[config] ATENÇÃO: {_problema}")

app = FastAPI(
    title="Assessor IA",
    description="Assessor financeiro e de agenda com LangChain e LangGraph.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(documents_router)
app.include_router(perfil_router)
app.include_router(sessions_router)
app.include_router(monitor_router)

@app.get("/health", tags=["infra"])
def health() -> dict:
    problemas = validar_config()
    return {
        "status": "ok" if not problemas else "atencao",
        "problemas_de_configuracao": problemas,
    }


# O mount em "/" captura qualquer rota nao registrada antes dele; por isso
# fica por ultimo, depois de /health e dos routers.
if (FRONTEND_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    @app.get("/", tags=["infra"])
    def raiz() -> dict:
        return {"mensagem": "API do acessor no ar. O frontend ainda não foi criado."}
