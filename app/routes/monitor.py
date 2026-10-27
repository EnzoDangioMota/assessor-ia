"""Agrega os sinais de observabilidade para a tela de operação."""

import math
from typing import Any

from fastapi import APIRouter

from app.observabilidade import (
    LIMITE_P95_MS,
    LIMITE_TAXA_ERRO,
    listar_chamadas,
    listar_turnos,
    situacao,
)

router = APIRouter(tags=["monitor"])


def _percentil_95(valores: list[int]) -> int:
    """Percentil nearest-rank: menor valor que cobre 95% das amostras."""
    if not valores:
        return 0
    ordenados = sorted(valores)
    indice = math.ceil(0.95 * len(ordenados)) - 1
    return ordenados[indice]


def _media(valores: list[float]) -> float:
    return sum(valores) / len(valores) if valores else 0.0


def _agrupar(itens: list[dict[str, Any]], chave: str) -> dict[str, list[dict[str, Any]]]:
    grupos: dict[str, list[dict[str, Any]]] = {}
    for item in itens:
        grupos.setdefault(item[chave], []).append(item)
    return grupos


def montar_painel() -> dict[str, Any]:
    turnos = listar_turnos()
    chamadas = listar_chamadas()
    estado = situacao()
    latencias = [turno["latencia_ms"] for turno in turnos]
    erros = sum(turno["status"] == "erro" for turno in turnos)
    bloqueios = sum(turno["status"] == "bloqueado" for turno in turnos)
    taxa_erro = erros / len(turnos) if turnos else 0.0
    latencia_p95 = _percentil_95(latencias)

    tokens_entrada = sum(chamada["tokens_entrada"] for chamada in chamadas)
    tokens_saida = sum(chamada["tokens_saida"] for chamada in chamadas)
    custos_conhecidos = [
        chamada["custo_usd"]
        for chamada in chamadas
        if chamada["custo_usd"] is not None
    ]
    custo = sum(custos_conhecidos)
    modelos_sem_preco = sorted(
        {
            chamada["modelo"]
            for chamada in chamadas
            if chamada["custo_usd"] is None
        }
    )

    grupos_modelo = _agrupar(chamadas, "modelo")
    modelo_mais_usado = "—"
    if grupos_modelo:
        modelo_mais_usado = max(
            grupos_modelo,
            key=lambda modelo: (
                len(grupos_modelo[modelo]),
                sum(
                    chamada["tokens_entrada"] + chamada["tokens_saida"]
                    for chamada in grupos_modelo[modelo]
                ),
            ),
        )

    por_modelo = [
        {
            "modelo": modelo,
            "chamadas": len(itens),
            "tokens_entrada": sum(item["tokens_entrada"] for item in itens),
            "tokens_saida": sum(item["tokens_saida"] for item in itens),
            "custo_usd": (
                round(sum(item["custo_usd"] for item in itens), 6)
                if all(item["custo_usd"] is not None for item in itens)
                else None
            ),
            "latencia_media_ms": round(
                _media([item["latencia_ms"] for item in itens])
            ),
        }
        for modelo, itens in grupos_modelo.items()
    ]
    por_modelo.sort(
        key=lambda linha: (
            linha["custo_usd"] if linha["custo_usd"] is not None else -1
        ),
        reverse=True,
    )

    grupos_rota = _agrupar(turnos, "rota")
    por_rota = [
        {
            "rota": rota,
            "turnos": len(itens),
            "erros": sum(item["status"] == "erro" for item in itens),
            "latencia_media_ms": round(
                _media([item["latencia_ms"] for item in itens])
            ),
            "custo_usd": round(sum(item["custo_usd"] for item in itens), 6),
            "custo_completo": all(item.get("custo_completo", True) for item in itens),
        }
        for rota, itens in grupos_rota.items()
    ]
    por_rota.sort(key=lambda linha: linha["turnos"], reverse=True)

    custo_acumulado = 0.0
    serie_custo = []
    for turno in turnos:
        custo_acumulado += turno["custo_usd"]
        serie_custo.append(
            {
                "hora": turno["hora"],
                "custo_acumulado_usd": round(custo_acumulado, 6),
            }
        )

    return {
        "slo": {
            "latencia_p95_limite_ms": LIMITE_P95_MS,
            "taxa_erro_limite": LIMITE_TAXA_ERRO,
        },
        "resumo": {
            "turnos": len(turnos),
            "em_andamento": estado["em_andamento"],
            "no_ar_segundos": estado["no_ar_segundos"],
            "taxa_erro": round(taxa_erro, 4),
            "bloqueios": bloqueios,
            "latencia_media_ms": round(_media(latencias)),
            "latencia_p95_ms": latencia_p95,
            "slo_ok": (
                latencia_p95 <= LIMITE_P95_MS
                and taxa_erro <= LIMITE_TAXA_ERRO
            ),
            "tokens_entrada": tokens_entrada,
            "tokens_saida": tokens_saida,
            "tokens_total": tokens_entrada + tokens_saida,
            "custo_usd": round(custo, 6),
            "custo_completo": not modelos_sem_preco,
            "modelos_sem_preco": modelos_sem_preco,
            "modelo_mais_usado": modelo_mais_usado,
            "fallbacks": sum(chamada["fallback"] for chamada in chamadas),
        },
        "serie_latencia": [
            {"hora": turno["hora"], "latencia_ms": turno["latencia_ms"]}
            for turno in turnos
        ],
        "serie_custo": serie_custo,
        "por_modelo": por_modelo,
        "por_rota": por_rota,
        "turnos": [
            {**turno, "custo_usd": round(turno["custo_usd"], 6)}
            for turno in turnos
        ],
    }


@router.get("/monitor")
def painel() -> dict[str, Any]:
    """Retorna métricas deste processo; reiniciar a API reinicia o registro."""
    return montar_painel()
