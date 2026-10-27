import sys
from pathlib import Path
from typing import Annotated, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from app.config import DATABASE_URL
from app.tools.financeiro import (
    add_transaction as _add_transaction,
    daily_balance as _daily_balance,
    query_transactions as _query_transactions,
    total_balance as _total_balance,
    update_transaction as _update_transaction,
)
from app.tools.agenda import (
    add_event as _add_event,
    check_conflicts as _check_conflicts,
    delete_event as _delete_event,
    query_events as _query_events,
    update_event as _update_event,
)

mcp = MCPServer(
    name="assessor-financeiro",
    version="1.0.0",
    instructions="Ferramentas financeiras do Assessor.AI...",
)

LEITURA = ToolAnnotations(readOnlyHint=True)
ESCRITA = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
DELETAR = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


@mcp.tool(
    name="query_transactions",
    title="Consultar transações",
    description="Lista transações filtrando por texto, tipo e intervalo de datas.",
    annotations=LEITURA,
)
def query_transactions(
    source_text: Annotated[
        Optional[str], Field(description="Texto para buscar na origem ou descrição.")
    ] = None,
    type_id: Annotated[
        Optional[int], Field(description="ID do tipo: 1=INCOME, 2=EXPENSES, 3=TRANSFER.")
    ] = None,
    initial_date: Annotated[
        Optional[str], Field(description="Data inicial no formato YYYY-MM-DD.")
    ] = None,
    final_date: Annotated[
        Optional[str], Field(description="Data final no formato YYYY-MM-DD.")
    ] = None,
    limit: Annotated[
        Optional[int],
        Field(description="Quantidade máxima de transações (1 a 100).", ge=1, le=100),
    ] = None,
) -> dict[str, Any]:
    resultado = _query_transactions.invoke(
        {
            "source_text": source_text,
            "type_id": type_id,
            "initial_date": initial_date,
            "final_date": final_date,
        }
    )
    if limit is not None and resultado.get("status") == "ok":
        transacoes = resultado.get("transactions")
        if isinstance(transacoes, list):
            resultado = {**resultado, "transactions": transacoes[:limit]}
    return resultado


@mcp.tool(
    name="total_balance",
    title="Saldo total",
    description="Calcula o saldo de todo o histórico: receitas menos despesas.",
    annotations=LEITURA,
)
def total_balance() -> dict[str, Any]:
    return _total_balance.invoke({})


@mcp.tool(
    name="daily_balance",
    title="Saldo diário",
    description="Calcula o saldo das transações do dia atual.",
    annotations=LEITURA,
)
def daily_balance() -> dict[str, Any]:
    return _daily_balance.invoke({})


@mcp.tool(
    name="add_transaction",
    title="Registrar transação",
    description="Registra uma transação financeira na tabela transactions.",
    annotations=ESCRITA,
)
def add_transaction(
    amount: Annotated[float, Field(description="Valor da transação, sempre positivo.")],
    source_text: Annotated[str, Field(description="Texto original informado pelo usuário.")],
    occurred_at: Annotated[
        Optional[str], Field(description="Timestamp ISO 8601; se omitido, usa o horário atual.")
    ] = None,
    type_name: Annotated[
        Optional[str], Field(description="Tipo: INCOME, EXPENSES ou TRANSFER.")
    ] = None,
    category_name: Annotated[
        Optional[str], Field(description="Nome da categoria em português.")
    ] = None,
    description: Annotated[
        Optional[str], Field(description="Descrição opcional da transação.")
    ] = None,
    payment_method: Annotated[
        Optional[str], Field(description="Forma de pagamento opcional.")
    ] = None,
) -> dict[str, Any]:
    return _add_transaction.invoke(
        {
            "amount": amount,
            "source_text": source_text,
            "occurred_at": occurred_at,
            "type_name": type_name,
            "category_name": category_name,
            "description": description,
            "payment_method": payment_method,
        }
    )


@mcp.tool(
    name="update_transaction",
    title="Atualizar transação",
    description="Atualiza uma transação por ID ou por texto e data.",
    annotations=ESCRITA,
)
def update_transaction(
    id: Annotated[Optional[int], Field(description="ID da transação.")] = None,
    match_text: Annotated[
        Optional[str], Field(description="Texto para localizar a transação quando não houver ID.")
    ] = None,
    date_local: Annotated[
        Optional[str], Field(description="Data local YYYY-MM-DD usada com match_text.")
    ] = None,
    amount: Annotated[Optional[float], Field(description="Novo valor.")] = None,
    type_name: Annotated[
        Optional[str], Field(description="Novo tipo: INCOME, EXPENSES ou TRANSFER.")
    ] = None,
    category_name: Annotated[
        Optional[str], Field(description="Nova categoria em português.")
    ] = None,
    description: Annotated[Optional[str], Field(description="Nova descrição.")] = None,
    payment_method: Annotated[
        Optional[str], Field(description="Novo meio de pagamento.")
    ] = None,
    occurred_at: Annotated[
        Optional[str], Field(description="Novo timestamp ISO 8601.")
    ] = None,
) -> dict[str, Any]:
    return _update_transaction.invoke(
        {
            "id": id,
            "match_text": match_text,
            "date_local": date_local,
            "amount": amount,
            "type_name": type_name,
            "category_name": category_name,
            "description": description,
            "payment_method": payment_method,
            "occurred_at": occurred_at,
        }
    )


@mcp.tool(
    name="add_event",
    title="Registrar evento",
    description="Registra um compromisso na tabela events do PostgreSQL.",
    annotations=ESCRITA,
)
def add_event(
    title: Annotated[str, Field(description="Título do evento.")],
    start_time: Annotated[str, Field(description="Início em ISO 8601.")],
    source_text: Annotated[str, Field(description="Texto original do usuário.")],
    end_time: Annotated[Optional[str], Field(description="Fim em ISO 8601.")] = None,
    location: Annotated[Optional[str], Field(description="Local do evento.")] = None,
    notes: Annotated[Optional[str], Field(description="Observações do evento.")] = None,
) -> dict[str, Any]:
    return _add_event.invoke(
        {
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "location": location,
            "notes": notes,
            "source_text": source_text,
        }
    )


@mcp.tool(
    name="query_events",
    title="Consultar eventos",
    description="Lista eventos por texto, título ou intervalo de datas.",
    annotations=LEITURA,
)
def query_events(
    source_text: Annotated[Optional[str], Field(description="Texto livre para busca.")] = None,
    title: Annotated[Optional[str], Field(description="Filtro parcial pelo título.")] = None,
    initial_date: Annotated[Optional[str], Field(description="Data inicial YYYY-MM-DD.")] = None,
    final_date: Annotated[Optional[str], Field(description="Data final YYYY-MM-DD.")] = None,
) -> dict[str, Any]:
    return _query_events.invoke(
        {
            "source_text": source_text,
            "title": title,
            "initial_date": initial_date,
            "final_date": final_date,
        }
    )


@mcp.tool(
    name="check_conflicts",
    title="Verificar conflitos",
    description="Verifica eventos que se sobrepõem a uma janela de horário.",
    annotations=LEITURA,
)
def check_conflicts(
    start_time: Annotated[str, Field(description="Início da janela em ISO 8601.")],
    end_time: Annotated[Optional[str], Field(description="Fim da janela em ISO 8601.")] = None,
    exclude_id: Annotated[Optional[int], Field(description="ID a ignorar.")] = None,
) -> dict[str, Any]:
    return _check_conflicts.invoke(
        {"start_time": start_time, "end_time": end_time, "exclude_id": exclude_id}
    )


@mcp.tool(
    name="update_event",
    title="Atualizar evento",
    description="Atualiza um evento por ID ou por texto e data.",
    annotations=ESCRITA,
)
def update_event(
    id: Annotated[Optional[int], Field(description="ID do evento.")] = None,
    match_text: Annotated[Optional[str], Field(description="Texto para localizar o evento.")] = None,
    date_local: Annotated[Optional[str], Field(description="Data local YYYY-MM-DD.")] = None,
    title: Annotated[Optional[str], Field(description="Novo título.")] = None,
    start_time: Annotated[Optional[str], Field(description="Novo início ISO 8601.")] = None,
    end_time: Annotated[Optional[str], Field(description="Novo fim ISO 8601.")] = None,
    location: Annotated[Optional[str], Field(description="Novo local.")] = None,
    notes: Annotated[Optional[str], Field(description="Novas observações.")] = None,
) -> dict[str, Any]:
    return _update_event.invoke(
        {
            "id": id,
            "match_text": match_text,
            "date_local": date_local,
            "title": title,
            "start_time": start_time,
            "end_time": end_time,
            "location": location,
            "notes": notes,
        }
    )


@mcp.tool(
    name="delete_event",
    title="Excluir evento",
    description="Exclui um evento por ID ou por texto e data.",
    annotations=DELETAR,
)
def delete_event(
    id: Annotated[Optional[int], Field(description="ID do evento.")] = None,
    match_text: Annotated[Optional[str], Field(description="Texto para localizar o evento.")] = None,
    date_local: Annotated[Optional[str], Field(description="Data local YYYY-MM-DD.")] = None,
) -> dict[str, Any]:
    return _delete_event.invoke(
        {"id": id, "match_text": match_text, "date_local": date_local}
    )


if __name__ == "__main__":
    if not DATABASE_URL:
        print(
            "[assessor-financeiro] DATABASE_URL ausente no .env",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")
