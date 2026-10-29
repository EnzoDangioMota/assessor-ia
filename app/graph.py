from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from datetime import datetime

import json
import operator
from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, END, MessagesState

from app.tools.financeiro import TOOLS
from app.tools.faq import faq_retriever
from app.tools.perfil import TOOLS_PERFIL
from app.tools.agenda import TOOLS_AGENDA
from app.tools.documents import consultar_arquivos_usuario

from app.llms import llm, llmRapido, llmGroq, llmGemini

import os

from app.prompts import (
    ROUTER_PROMPT_COMPLETO, 
    FINANCEIRO_PROMPT_COMPLETO, 
    AGENDA_PROMPT_COMPLETO, 
    ORQUESTRADOR_PROMPT_COMPLETO, 
    FAQ_PROMPT_COMPLETO
)

from dotenv import load_dotenv

from app.guardrail import guardrail_entrada, guardrail_saida, anonimizar_entrada, desanonimizar_saida
from app.juiz import no_juiz

from langchain_core.messages import RemoveMessage
from langchain_core.runnables import RunnableConfig

from app.memory import iniciar_sessao, salvar_mensagem, encerrar_sessao
from app.observabilidade import abrir_turno, coletor, fechar_turno, status_do_estado
from app.tools.turno_tx import iniciar_turno, encerrar_turno

data_atual = datetime.now()

load_dotenv()

router_memory = MemorySaver()

# AGENTE DO ROTEADOR
router_agent = create_agent(
    model = llmRapido, 
    system_prompt = ROUTER_PROMPT_COMPLETO, 
    checkpointer = router_memory
)

# AGENTE RESPONSÁVEL PELAS FINANÇAS
financeiro_agent = create_agent(
    model = llm, 
    system_prompt = FINANCEIRO_PROMPT_COMPLETO, 
    tools = TOOLS + TOOLS_PERFIL + [consultar_arquivos_usuario],
    checkpointer = router_memory
)

# AGENTE RESPONSÁVEL PELA AGENDA
agenda_agent = create_agent(
    model = llm, 
    system_prompt = AGENDA_PROMPT_COMPLETO,
    tools = TOOLS_AGENDA + [consultar_arquivos_usuario],
    checkpointer = router_memory,
)

# AGENTE DO ORQUESTRADOR - NÃO RECEBE CHECKPOINTER PORQUE ELE NÃO PRECISA DO HISTÓRICO
orquestrador_agent = create_agent(
    model = llmRapido, 
    system_prompt = ORQUESTRADOR_PROMPT_COMPLETO
)

# AGENTE DO FAQ - RESPONDE COISAS SOBRE O SISTEMA
faq_agent = create_agent(
    model = llmRapido,
    system_prompt = FAQ_PROMPT_COMPLETO,
    tools = [faq_retriever],
)

# FUNÇÃO PARA DEFINIRMOS QUAL AGENTE SERÁ USADO
# ==============================================================================
# ESTADO
# ==============================================================================
class Estado(MessagesState):
    agentes_chamados:   Annotated[list[str], operator.add]  # acumula entre nós
    rota:               str
    mapa_pii: dict


def _tipo_msg(msg):
    if isinstance(msg, dict):
        return msg.get("role")
    return getattr(msg, "type", None)


def _conteudo_msg(msg):
    if isinstance(msg, dict):
        return msg.get("content", "")
    return getattr(msg, "content", "")


def _formatar_protocolo_especialista(texto: str) -> str:
    """Converte um JSON de especialista que escapou para a resposta final."""
    bruto = texto.strip()
    if not bruto.startswith("{"):
        return texto

    try:
        protocolo = json.loads(bruto)
    except json.JSONDecodeError:
        return texto

    if not isinstance(protocolo, dict) or not protocolo.get("dominio") or not protocolo.get("resposta"):
        return texto

    linhas = [f"- {protocolo['resposta']}"]
    recomendacao = protocolo.get("recomendacao")
    if recomendacao:
        linhas.extend(["- *Recomendação*:", str(recomendacao)])

    acompanhamento = protocolo.get("esclarecer") or protocolo.get("acompanhamento")
    if acompanhamento:
        linhas.extend(["- *Acompanhamento*:", str(acompanhamento)])

    evento = protocolo.get("evento")
    if isinstance(evento, dict) and protocolo.get("intencao") in {"criar", "atualizar"}:
        detalhes = []
        if evento.get("titulo"):
            detalhes.append(str(evento["titulo"]))
        if evento.get("data"):
            detalhes.append(str(evento["data"]))
        if evento.get("inicio"):
            horario = str(evento["inicio"])
            if evento.get("fim"):
                horario += f"-{evento['fim']}"
            detalhes.append(horario)
        if detalhes:
            linhas.append(f"- *Evento*: {' | '.join(detalhes)}")

    return "\n".join(linhas)


# ==============================================================================
# NÓS
# ==============================================================================
def no_roteador(estado: Estado, config: RunnableConfig) -> dict:
    saida = router_agent.invoke(
        {"messages": list(estado["messages"])},
        config=config,
    )
    texto = saida["messages"][-1].text

    # Resposta direta (saudação, fora de escopo): já escreve no campo final
    if not texto.strip().startswith("ROUTE="):
        return {
            "agentes_chamados": ["roteador"],
            "rota":             "fim",
            "messages":         [{"role": "assistant", "content": texto}], # saida["messages"][-1] ---> O código comentado ao lado representa uma forma mais fácil de fazer a mesma coisa. O que está sendo usado é para melhor compreensão.
        }
        
    rota = "fim"
    
    for linha in texto.splitlines():
        if linha.startswith("ROUTE="):
            rota = linha.split("=", 1)[1].strip()
            break            

    # Encaminhamento: sobrescreve input com o protocolo para o especialista
    return {
        "agentes_chamados": ["roteador"],
        "rota":             rota
    }
    

def no_orquestrador(estado: Estado, config: RunnableConfig) -> dict:
    ultimo_especialista = ""
    for mensagem in reversed(estado["messages"]):
        tipo = _tipo_msg(mensagem)
        conteudo = _conteudo_msg(mensagem)
        if tipo in {"ai", "assistant"} and conteudo:
            ultimo_especialista = conteudo
            break

    saida = orquestrador_agent.invoke(
        {"messages": list(estado["messages"])},
        config=config,
    )
    ultima = saida["messages"][-1]
    texto = getattr(ultima, "text", None) or _conteudo_msg(ultima)
    texto = _formatar_protocolo_especialista(texto)

    return {
        "agentes_chamados": ["orquestrador", estado["rota"]],
        "messages": [{"role": "assistant", "content": texto}],
    }
    
def no_guardrail_entrada(estado: Estado, config: RunnableConfig) -> dict:
    ultimo_humano = ""
    id_mou = ""
    for msg in reversed(estado["messages"]):
        if getattr(msg, "type", None) == "human" and getattr(msg, "content", None):
            id_mou = getattr(msg, "id", None)
            ultimo_humano = msg.content
            break

    if not ultimo_humano:
        return {
            "messages": [{"role": "assistant", "content": "Não consegui ler sua mensagem."}],
            "rota": "fim",
            "mapa_pii": {},
            "agentes_chamados": ["guardrail_entrada:sem_mensagem"],
        }

    mensagem_anonimizada, mapa = anonimizar_entrada(ultimo_humano)
    resultado = guardrail_entrada(mensagem_anonimizada, config=config)

    if resultado["bloqueado"]:
        return {
            "messages": [{"role": "assistant", "content": resultado["mensagem"]}],
            "rota": "fim",
            "mapa_pii": {},
            "agentes_chamados": [f"guardrail_entrada:{resultado['motivo']}"] ,
        }

    mensagens = []
    if id_mou:
        mensagens.append(RemoveMessage(id=id_mou))
    mensagens.append({"role": "human", "content": mensagem_anonimizada})

    return {
        "messages": mensagens,
        "mapa_pii": mapa,
        "agentes_chamados": ["guardrail_entrada:aprovado"],
        "rota": "roteador",
    }


def no_decidir_pos_entrada(estado: Estado) -> str:
    return "fim" if estado.get("rota") == "fim" else "roteador"


def no_guardrail_saida(estado: Estado, config: RunnableConfig) -> dict:
    ultima = ""
    for msg in reversed(estado["messages"]):
        tipo = _tipo_msg(msg)
        conteudo = _conteudo_msg(msg)
        if tipo == "ai" and conteudo:
            ultima = conteudo
            break

    resultado = guardrail_saida(
        ultima,
        estado.get("mapa_pii", {}),
        config=config,
    )
    return {
        "messages": [{"role": "assistant", "content": resultado["conteudo"]}],
        "agentes_chamados": ["guardrail_saida"],
    }


def no_decidir_pos_orquestrador(
    estado: Estado, config: RunnableConfig
) -> dict:
    ultima = ""
    for msg in reversed(estado["messages"]):
        tipo = _tipo_msg(msg)
        conteudo = _conteudo_msg(msg)
        if tipo == "ai" and conteudo:
            ultima = conteudo
            break

    resultado = guardrail_saida(
        ultima,
        estado.get("mapa_pii", {}),
        config=config,
    )

    return {
        "messages": [{"role": "assistant", "content": resultado["conteudo"]}],
        "agentes_chamados": ["guardrail_saida"],
    }

# ==============================================================================
# FUNÇÃO DE DECISÃO
# ==============================================================================
def decidir_especialista(estado: Estado) -> str:
    """Lê o protocolo do roteador e devolve o nome do próximo nó."""
    return estado["rota"] if estado["rota"] in ("financeiro", "agenda", "faq") else "fim"


# ==============================================================================
# CONSTRUÇÃO DO GRAFO
# ==============================================================================
grafo = StateGraph(Estado)

grafo.add_node("roteador", no_roteador)
grafo.add_node("financeiro", financeiro_agent)
grafo.add_node("agenda", agenda_agent)
grafo.add_node("faq", faq_agent)
grafo.add_node("orquestrador", no_orquestrador)
grafo.add_node("guardrail_entrada", no_guardrail_entrada)
grafo.add_node("guardrail_saida", no_guardrail_saida)
grafo.add_node("juiz", no_juiz)

grafo.set_entry_point("guardrail_entrada")

grafo.add_conditional_edges(
    "guardrail_entrada",
    no_decidir_pos_entrada,
    {
        "roteador": "roteador",
        "fim":        END,       # resposta direta: sem especialista nem orquestrador
    },
)

grafo.add_conditional_edges(
    "roteador",
    decidir_especialista,
    {
        "financeiro": "financeiro",
        "agenda":     "agenda",
        "faq":        "faq",
        "fim":        "juiz",    # resposta direta: sem especialista nem orquestrador
    },
)

grafo.add_edge("financeiro",   "orquestrador")
grafo.add_edge("agenda",       "orquestrador")
grafo.add_edge("orquestrador", "guardrail_saida")
grafo.add_edge("guardrail_saida", "juiz")
grafo.add_edge("faq",          "juiz")   # FAQ bypassa o orquestrador
grafo.add_edge("juiz",         END)

# Memória centralizada no grafo — persiste o Estado inteiro entre turns
memory = MemorySaver()
fluxo_agentes = grafo.compile(checkpointer=memory)


# ==============================================================================
# FLUXO PRINCIPAL
# ==============================================================================
def executar_fluxo_assessor(
    pergunta_usuario: str, session_id: str, user_id: str = "usuario_teste"
) -> str:
    pergunta_usuario_anonimizado, _ = anonimizar_entrada(pergunta_usuario)
    estado_inicial = {
        "messages":         [{"role": "human", "content": pergunta_usuario}],
        "agentes_chamados": [],
        "rota":             "",
        "mapa_pii":         {},
        "session_id":       session_id,
    }

    turno_id = abrir_turno()
    iniciar_turno()  # unidade de trabalho do turno: o juiz decide o commit (app/juiz.py)
    status = "erro"
    rota = ""
    try:
        estado_final = fluxo_agentes.invoke(
            estado_inicial,
            config={
                "configurable": {"thread_id": session_id, "user_id": user_id},
                "metadata": {"turno_id": turno_id},
                "callbacks": [coletor],
            },
        )

        resposta = estado_final["messages"][-1].text

        salvar_mensagem(
            session_id, "human", pergunta_usuario_anonimizado, user_id=user_id
        )
        salvar_mensagem(session_id, "assistant", resposta, user_id=user_id)

        status = status_do_estado(estado_final)
        rota = estado_final.get("rota") or ""
        return resposta
    finally:
        encerrar_turno()  # rede de segurança: desfaz o que o juiz não confirmou (exceção, bloqueio)
        fechar_turno(turno_id, session_id=session_id, rota=rota, status=status)

# while True: 
#     user_input = input("> ")
#     if user_input.lower() in ('sair', 'end', 'fim', 'tchau', 'bye', 'flw', 'falou'):
#         print("Encerrando a conversa.")
#         break
    
#     try: 
#         resposta = executar_fluxo_assessor(
#             pergunta_usuario = user_input, 
#             session_id = "id_do_usuario_mas_nao_precisa_agora"
#         )
#         print("Assessor: " + resposta)
#     except Exception as e:
#         print(f"Erro ao consumir a API: {e}", e)