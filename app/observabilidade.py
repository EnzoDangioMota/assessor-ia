"""Coleta métricas em memória por turno, sem armazenar prompts ou respostas."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

_FUSO = ZoneInfo("America/Sao_Paulo")

# USD por milhão de tokens: (entrada, saída).
PRECO_POR_MILHAO: dict[str, tuple[float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50),
    "openai/gpt-oss-120b": (0.15, 0.60),
}

_NOS_ESPECIALISTA = {"financeiro", "agenda"}
_MODELO_ESPECIALISTA = "gemini-2.5-flash"

LIMITE_TURNOS = 50
LIMITE_P95_MS = 8_000
LIMITE_TAXA_ERRO = 0.05

_lock = threading.Lock()
_turno_por_thread = threading.local()
_inicio_processo = time.time()
_em_andamento = 0
_turnos: list[dict[str, Any]] = []
_chamadas: list[dict[str, Any]] = []
_abertos: dict[str, float] = {}
_runs: dict[str, dict[str, Any]] = {}


def _turno_da_thread() -> str | None:
    return getattr(_turno_por_thread, "turno_id", None)


def _nome_modelo(
    serialized: dict[str, Any] | None,
    invocation_params: dict[str, Any] | None,
    resposta_meta: dict[str, Any] | None,
) -> str:
    fontes = (
        resposta_meta or {},
        invocation_params or {},
        (serialized or {}).get("kwargs") or {},
    )
    for fonte in fontes:
        for chave in ("model_name", "model"):
            nome = fonte.get(chave)
            if nome:
                nome = str(nome)
                return nome.split("/", 1)[1] if nome.startswith("models/") else nome
    return "desconhecido"


def _no_do_grafo(metadata: dict[str, Any] | None) -> str:
    metadata = metadata or {}
    namespace = str(metadata.get("langgraph_checkpoint_ns") or "")
    candidatos = [
        parte.split(":", 1)[0]
        for parte in namespace.split("|")
        if parte
    ]
    no = metadata.get("langgraph_node")
    if no:
        candidatos.append(str(no))
    for nome in reversed(candidatos):
        if nome in _NOS_ESPECIALISTA:
            return nome
    return candidatos[-1] if candidatos else "desconhecido"


def _tokens(message: Any) -> tuple[int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        usage = {
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
        }
    entrada = int(usage.get("input_tokens") or 0)
    saida = int(usage.get("output_tokens") or 0)
    if entrada or saida:
        return entrada, saida

    metadata = getattr(message, "response_metadata", None) or {}
    bruto = metadata.get("token_usage") or metadata.get("usage") or {}
    return (
        int(bruto.get("prompt_tokens") or bruto.get("input_tokens") or 0),
        int(bruto.get("completion_tokens") or bruto.get("output_tokens") or 0),
    )


def custo_usd(modelo: str, entrada: int, saida: int) -> float | None:
    precos = PRECO_POR_MILHAO.get(modelo)
    if precos is None:
        precos = next(
            (valor for chave, valor in PRECO_POR_MILHAO.items() if chave in modelo),
            None,
        )
    if precos is None:
        return None
    preco_entrada, preco_saida = precos
    return (entrada * preco_entrada + saida * preco_saida) / 1_000_000


class ColetorChamadas(BaseCallbackHandler):
    """Registra modelo, tokens e latência sem reter conteúdo de mensagens."""

    raise_error = False

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: Any,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        invocation = kwargs.get("invocation_params") or {}
        with _lock:
            _runs[str(run_id)] = {
                "inicio": time.perf_counter(),
                "modelo": _nome_modelo(serialized, invocation, None),
                "no": _no_do_grafo(metadata),
                "turno_id": (metadata or {}).get("turno_id") or _turno_da_thread(),
            }

    def on_llm_end(
        self, response: LLMResult, *, run_id: Any, **kwargs: Any
    ) -> None:
        with _lock:
            abertura = _runs.pop(str(run_id), None)
        if abertura is None or not abertura["turno_id"]:
            return

        try:
            message = response.generations[0][0].message
        except (IndexError, AttributeError):
            message = None

        entrada, saida = _tokens(message) if message is not None else (0, 0)
        metadata = getattr(message, "response_metadata", None) or {}
        modelo = _nome_modelo(None, None, metadata)
        if modelo == "desconhecido":
            modelo = abertura["modelo"]

        registro = {
            "turno_id": abertura["turno_id"],
            "modelo": modelo,
            "no": abertura["no"],
            "tokens_entrada": entrada,
            "tokens_saida": saida,
            "custo_usd": custo_usd(modelo, entrada, saida),
            "latencia_ms": int((time.perf_counter() - abertura["inicio"]) * 1000),
            "fallback": (
                abertura["no"] in _NOS_ESPECIALISTA
                and _MODELO_ESPECIALISTA not in modelo
            ),
        }
        with _lock:
            _chamadas.append(registro)

    def on_llm_error(
        self, error: BaseException, *, run_id: Any, **kwargs: Any
    ) -> None:
        with _lock:
            _runs.pop(str(run_id), None)


coletor = ColetorChamadas()


def abrir_turno() -> str:
    """Começa a medir um turno e associa as chamadas desta thread a ele."""
    global _em_andamento
    turno_id = uuid.uuid4().hex
    _turno_por_thread.turno_id = turno_id
    with _lock:
        _em_andamento += 1
        _abertos[turno_id] = time.perf_counter()
    return turno_id


def fechar_turno(turno_id: str, session_id: str, rota: str, status: str) -> None:
    """Fecha um turno mesmo quando a execução do grafo termina com exceção."""
    global _em_andamento
    _turno_por_thread.turno_id = None
    with _lock:
        inicio = _abertos.pop(turno_id, None)
        if inicio is None:
            return

        _em_andamento = max(0, _em_andamento - 1)
        chamadas = [c for c in _chamadas if c["turno_id"] == turno_id]
        custos_conhecidos = [
            chamada["custo_usd"]
            for chamada in chamadas
            if chamada["custo_usd"] is not None
        ]
        _turnos.append(
            {
                "id": turno_id,
                "hora": datetime.now(_FUSO).strftime("%H:%M:%S"),
                "session_id": session_id,
                "latencia_ms": int((time.perf_counter() - inicio) * 1000),
                "rota": rota or "—",
                "status": status,
                "tokens_total": sum(
                    c["tokens_entrada"] + c["tokens_saida"] for c in chamadas
                ),
                "custo_usd": sum(custos_conhecidos),
                "custo_completo": len(custos_conhecidos) == len(chamadas),
            }
        )
        while len(_turnos) > LIMITE_TURNOS:
            antigo = _turnos.pop(0)
            _chamadas[:] = [
                chamada
                for chamada in _chamadas
                if chamada["turno_id"] != antigo["id"]
            ]


def status_do_estado(estado: dict[str, Any]) -> str:
    """Bloqueios do guardrail são esperados; falhas excepcionais são erros."""
    for agente in estado.get("agentes_chamados") or []:
        if (
            isinstance(agente, str)
            and agente.startswith("guardrail_entrada:")
            and agente != "guardrail_entrada:aprovado"
        ):
            return "bloqueado"
    return "ok"


def listar_turnos() -> list[dict[str, Any]]:
    with _lock:
        return [
            {chave: valor for chave, valor in turno.items() if chave != "id"}
            for turno in _turnos
        ]


def listar_chamadas() -> list[dict[str, Any]]:
    with _lock:
        concluidos = {turno["id"] for turno in _turnos}
        return [
            {chave: valor for chave, valor in chamada.items() if chave != "turno_id"}
            for chamada in _chamadas
            if chamada["turno_id"] in concluidos
        ]


def situacao() -> dict[str, int]:
    with _lock:
        return {
            "em_andamento": _em_andamento,
            "no_ar_segundos": int(time.time() - _inicio_processo),
        }
