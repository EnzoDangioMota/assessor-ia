import json
import unittest
from unittest.mock import patch

from app.juiz import FRASE_SEGURA, _coleta, no_juiz


def _resposta_jev(choice="apoiada", noul=0.9):
    corpo = json.dumps({
        "answers": {
            "veredito": {"choice": choice},
            "apoiada": {"noul": noul},
        }
    }).encode()
    resposta = unittest.mock.MagicMock()
    resposta.__enter__.return_value.read.return_value = corpo
    return resposta


class JuizTests(unittest.TestCase):
    def setUp(self):
        self.estado = {
            "messages": [
                {"role": "human", "content": "Quanto gastei?"},
                {
                    "role": "assistant",
                    "content": "Você gastou R$ 120.",
                    "tool_calls": [{"name": "query_transactions", "args": {"ano": 2026}}],
                },
                {"role": "tool", "name": "query_transactions", "content": '[{"amount":120}]'},
            ]
        }

    def test_coleta_restringe_evidencias_ao_turno_atual(self):
        self.estado["messages"].insert(0, {"role": "human", "content": "Turno anterior"})
        pergunta, resposta, evidencia = _coleta(self.estado)

        self.assertEqual(pergunta, "Quanto gastei?")
        self.assertEqual(resposta, "Você gastou R$ 120.")
        self.assertIn("[query_transactions]", evidencia)
        self.assertNotIn("Turno anterior", evidencia)

    @patch("app.juiz.TYPESAFE_API_KEY", None)
    def test_sem_chave_reprova_com_frase_fixa(self):
        resultado = no_juiz(self.estado)

        self.assertEqual(resultado["messages"][0]["content"], FRASE_SEGURA)
        self.assertEqual(resultado["agentes_chamados"], ["juiz:sem_chave"])

    @patch("app.juiz.TYPESAFE_API_KEY", "teste")
    @patch("app.juiz.urllib.request.urlopen")
    def test_aprovacao_preserva_resposta_original(self, urlopen):
        urlopen.return_value = _resposta_jev("apoiada", 0.7)

        resultado = no_juiz(self.estado)

        self.assertNotIn("messages", resultado)
        self.assertEqual(resultado["agentes_chamados"], ["juiz:apoiada noul=0.70"])

    @patch("app.juiz.TYPESAFE_API_KEY", "teste")
    @patch("app.juiz.urllib.request.urlopen")
    def test_veredito_sem_apoio_substitui_resposta(self, urlopen):
        urlopen.return_value = _resposta_jev("sem_apoio", 0.95)

        resultado = no_juiz(self.estado)

        self.assertEqual(resultado["messages"][0]["content"], FRASE_SEGURA)
        self.assertEqual(resultado["agentes_chamados"], ["juiz:sem_apoio noul=0.95"])

    @patch("app.juiz.TYPESAFE_API_KEY", "teste")
    @patch("app.juiz.urllib.request.urlopen")
    def test_probabilidade_abaixo_do_limiar_reprova(self, urlopen):
        urlopen.return_value = _resposta_jev("apoiada", 0.69)

        resultado = no_juiz(self.estado)

        self.assertEqual(resultado["messages"][0]["content"], FRASE_SEGURA)
        self.assertEqual(
            resultado["agentes_chamados"],
            ["juiz:apoiada:abaixo_do_limiar noul=0.69"],
        )

    @patch("app.juiz.TYPESAFE_API_KEY", "teste")
    @patch("app.juiz.urllib.request.urlopen")
    def test_erro_de_rede_reprova_com_frase_fixa(self, urlopen):
        urlopen.side_effect = TimeoutError("timeout")

        resultado = no_juiz(self.estado)

        self.assertEqual(resultado["messages"][0]["content"], FRASE_SEGURA)
        self.assertEqual(resultado["agentes_chamados"], ["juiz:erro de rede"])


if __name__ == "__main__":
    unittest.main()
