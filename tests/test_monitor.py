import unittest
import uuid
from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.observabilidade import (
    abrir_turno,
    coletor,
    fechar_turno,
    listar_chamadas,
    listar_turnos,
)
from app.routes.monitor import _percentil_95, montar_painel


class Percentil95Tests(unittest.TestCase):
    def test_uses_nearest_rank(self):
        self.assertEqual(_percentil_95([10, 30, 20, 40]), 40)

    def test_empty_sample_is_zero(self):
        self.assertEqual(_percentil_95([]), 0)

    def test_unknown_model_price_is_not_reported_as_zero(self):
        from app.observabilidade import custo_usd

        self.assertIsNone(custo_usd("modelo-sem-preco", 100, 50))


class MonitorPanelTests(unittest.TestCase):
    @patch("app.routes.monitor.situacao")
    @patch("app.routes.monitor.listar_chamadas")
    @patch("app.routes.monitor.listar_turnos")
    def test_aggregates_turns_and_model_usage(
        self, listar_turnos, listar_chamadas, situacao
    ):
        listar_turnos.return_value = [
            {
                "hora": "10:00:00",
                "session_id": "sessao-teste",
                "latencia_ms": 1000,
                "rota": "financeiro",
                "status": "ok",
                "tokens_total": 15,
                "custo_usd": 0.001,
            },
            {
                "hora": "10:01:00",
                "session_id": "sessao-teste",
                "latencia_ms": 9000,
                "rota": "fim",
                "status": "bloqueado",
                "tokens_total": 0,
                "custo_usd": 0.0,
            },
        ]
        listar_chamadas.return_value = [
            {
                "modelo": "gemini-2.5-flash",
                "no": "financeiro",
                "tokens_entrada": 10,
                "tokens_saida": 5,
                "custo_usd": 0.001,
                "latencia_ms": 300,
                "fallback": False,
            }
        ]
        situacao.return_value = {"em_andamento": 0, "no_ar_segundos": 90}

        painel = montar_painel()

        self.assertEqual(painel["resumo"]["turnos"], 2)
        self.assertEqual(painel["resumo"]["bloqueios"], 1)
        self.assertEqual(painel["resumo"]["taxa_erro"], 0)
        self.assertEqual(painel["resumo"]["latencia_p95_ms"], 9000)
        self.assertFalse(painel["resumo"]["slo_ok"])
        self.assertEqual(painel["resumo"]["tokens_total"], 15)
        self.assertTrue(painel["resumo"]["custo_completo"])
        self.assertEqual(painel["por_modelo"][0]["modelo"], "gemini-2.5-flash")

    @patch("app.routes.monitor.situacao")
    @patch("app.routes.monitor.listar_chamadas")
    @patch("app.routes.monitor.listar_turnos")
    def test_marks_cost_as_partial_for_unpriced_models(
        self, listar_turnos, listar_chamadas, situacao
    ):
        listar_turnos.return_value = [
            {
                "hora": "10:00:00",
                "session_id": "sessao-teste",
                "latencia_ms": 500,
                "rota": "financeiro",
                "status": "ok",
                "tokens_total": 10,
                "custo_usd": 0,
                "custo_completo": False,
            }
        ]
        listar_chamadas.return_value = [
            {
                "modelo": "modelo-sem-preco",
                "no": "financeiro",
                "tokens_entrada": 5,
                "tokens_saida": 5,
                "custo_usd": None,
                "latencia_ms": 200,
                "fallback": True,
            }
        ]
        situacao.return_value = {"em_andamento": 0, "no_ar_segundos": 10}

        painel = montar_painel()

        self.assertFalse(painel["resumo"]["custo_completo"])
        self.assertEqual(painel["resumo"]["modelos_sem_preco"], ["modelo-sem-preco"])
        self.assertIsNone(painel["por_modelo"][0]["custo_usd"])


class CallbackCollectionTests(unittest.TestCase):
    def test_collects_tokens_without_storing_message_content(self):
        turno_id = abrir_turno()
        run_id = uuid.uuid4()
        try:
            coletor.on_chat_model_start(
                {"kwargs": {"model": "gemini-2.5-flash"}},
                [],
                run_id=run_id,
                metadata={"turno_id": turno_id, "langgraph_node": "financeiro"},
            )
            resposta = AIMessage(
                content="texto que nao deve ser registrado",
                usage_metadata={
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "total_tokens": 125,
                },
            )
            coletor.on_llm_end(
                LLMResult(generations=[[ChatGeneration(message=resposta)]]),
                run_id=run_id,
            )
        finally:
            fechar_turno(turno_id, "sessao-teste", "financeiro", "ok")

        chamada = listar_chamadas()[-1]
        turno = listar_turnos()[-1]
        self.assertEqual(chamada["tokens_entrada"], 100)
        self.assertEqual(chamada["tokens_saida"], 25)
        self.assertEqual(chamada["no"], "financeiro")
        self.assertNotIn("texto que nao deve ser registrado", str(chamada))
        self.assertEqual(turno["tokens_total"], 125)


if __name__ == "__main__":
    unittest.main()
