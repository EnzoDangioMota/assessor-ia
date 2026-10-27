import psycopg2
from typing import List, Optional
from langchain.tools import tool
from pydantic import BaseModel, Field

from app.config import DATABASE_URL


def get_conn():
    return psycopg2.connect(DATABASE_URL)


# ==============================================================================
# ARGS SCHEMAS
# ==============================================================================
class AddEventArgs(BaseModel):
    title: str = Field(..., description="Título/nome do compromisso ou evento.")
    start_time: str = Field(
        ...,
        description="Timestamp ISO 8601 de início do evento (ex.: '2026-09-25T14:00:00').",
    )
    end_time: Optional[str] = Field(
        default=None,
        description="Timestamp ISO 8601 de término do evento (opcional).",
    )
    location: Optional[str] = Field(default=None, description="Local do evento (opcional).")
    notes: Optional[str] = Field(default=None, description="Observações/anotações sobre o evento (opcional).")
    source_text: str = Field(..., description="Texto original do usuário.")


class QueryEventsArgs(BaseModel):
    source_text: Optional[str] = Field(default=None, description="Texto original do usuário para busca livre.")
    title: Optional[str] = Field(default=None, description="Filtra por título (busca parcial).")
    initial_date: Optional[str] = Field(
        default=None, description="Primeira data (YYYY-MM-DD) do intervalo de busca."
    )
    final_date: Optional[str] = Field(
        default=None, description="Data final (YYYY-MM-DD) do intervalo de busca."
    )


class UpdateEventArgs(BaseModel):
    id: Optional[int] = Field(
        default=None,
        description="ID do evento a atualizar. Se ausente, será feita uma busca por (match_text + date_local).",
    )
    match_text: Optional[str] = Field(
        default=None,
        description="Texto para localizar o evento quando id não for informado (busca em title/notes/source_text).",
    )
    date_local: Optional[str] = Field(
        default=None,
        description="Data local (YYYY-MM-DD) em America/Sao_Paulo; usado com match_text quando id ausente.",
    )
    title: Optional[str] = Field(default=None, description="Novo título.")
    start_time: Optional[str] = Field(default=None, description="Novo timestamp ISO 8601 de início.")
    end_time: Optional[str] = Field(default=None, description="Novo timestamp ISO 8601 de término.")
    location: Optional[str] = Field(default=None, description="Novo local.")
    notes: Optional[str] = Field(default=None, description="Novas observações.")


class DeleteEventArgs(BaseModel):
    id: Optional[int] = Field(
        default=None,
        description="ID do evento a remover. Se ausente, será feita uma busca por (match_text + date_local).",
    )
    match_text: Optional[str] = Field(
        default=None,
        description="Texto para localizar o evento quando id não for informado (busca em title/notes/source_text).",
    )
    date_local: Optional[str] = Field(
        default=None,
        description="Data local (YYYY-MM-DD) em America/Sao_Paulo; usado com match_text quando id ausente.",
    )


class CheckConflictsArgs(BaseModel):
    start_time: str = Field(..., description="Timestamp ISO 8601 de início da janela a checar.")
    end_time: Optional[str] = Field(
        default=None,
        description="Timestamp ISO 8601 de término da janela a checar. Se ausente, usa o próprio start_time.",
    )
    exclude_id: Optional[int] = Field(
        default=None, description="ID de evento a ignorar na checagem (útil ao editar um evento existente)."
    )


def _local_date_filter_sql(coluna: str) -> str:
    """Filtra uma coluna timestamptz pela data local (America/Sao_Paulo)."""
    return f"({coluna} AT TIME ZONE 'America/Sao_Paulo')::date = %s::date"


# ==============================================================================
# TOOL: add_event
# ==============================================================================
@tool("add_event", args_schema=AddEventArgs)
def add_event(
    title: str,
    start_time: str,
    source_text: str,
    end_time: Optional[str] = None,
    location: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """Insere um compromisso/evento no banco de dados Postgres (tabela events)."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO events
                (title, start_time, end_time, location, notes, source_text, recorded_at)
            VALUES
                (%s, %s::timestamptz, %s::timestamptz, %s, %s, %s, NOW())
            RETURNING id, start_time, end_time;
            """,
            (title, start_time, end_time, location, notes, source_text),
        )
        new_id, started, ended = cur.fetchone()
        conn.commit()
        return {
            "status": "ok",
            "id": new_id,
            "start_time": str(started),
            "end_time": str(ended) if ended else None,
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ==============================================================================
# TOOL: query_events
# ==============================================================================
@tool("query_events", args_schema=QueryEventsArgs)
def query_events(
    source_text: Optional[str] = None,
    title: Optional[str] = None,
    initial_date: Optional[str] = None,
    final_date: Optional[str] = None,
) -> dict:
    """Lista compromissos/eventos, opcionalmente filtrando por texto, título ou período."""
    conn = get_conn()
    cur = conn.cursor()
    query = "SELECT id, title, start_time, end_time, location, notes, source_text FROM events WHERE 1=1"
    params: List[object] = []

    try:
        if source_text:
            query += " AND (source_text ILIKE %s OR notes ILIKE %s)"
            params.extend([f"%{source_text}%", f"%{source_text}%"])

        if title:
            query += " AND title ILIKE %s"
            params.append(f"%{title}%")

        if initial_date and final_date:
            query += """ AND start_time >= %s::timestamp
                         AND start_time < %s::timestamp + INTERVAL '1 day'"""
            params.extend([initial_date, final_date])
        elif initial_date:
            query += f" AND {_local_date_filter_sql('start_time')}"
            params.append(initial_date)

        query += " ORDER BY start_time ASC"

        cur.execute(query, params)
        rows = cur.fetchall()

        return {
            "status": "ok",
            "events": [
                {
                    "id": r[0],
                    "title": r[1],
                    "start_time": str(r[2]),
                    "end_time": str(r[3]) if r[3] else None,
                    "location": r[4],
                    "notes": r[5],
                    "source_text": r[6],
                }
                for r in rows
            ],
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()


# ==============================================================================
# TOOL: check_conflicts
# ==============================================================================
@tool("check_conflicts", args_schema=CheckConflictsArgs)
def check_conflicts(
    start_time: str,
    end_time: Optional[str] = None,
    exclude_id: Optional[int] = None,
) -> dict:
    """Verifica se já existe algum evento que se sobreponha à janela de horário informada."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        end_value = end_time or start_time
        query = """
            SELECT id, title, start_time, end_time, location
            FROM events
            WHERE start_time < %s::timestamptz
              AND COALESCE(end_time, start_time) > %s::timestamptz
        """
        params: List[object] = [end_value, start_time]

        if exclude_id:
            query += " AND id != %s"
            params.append(exclude_id)

        query += " ORDER BY start_time ASC"

        cur.execute(query, params)
        rows = cur.fetchall()

        return {
            "status": "ok",
            "tem_conflito": len(rows) > 0,
            "eventos_conflitantes": [
                {
                    "id": r[0],
                    "title": r[1],
                    "start_time": str(r[2]),
                    "end_time": str(r[3]) if r[3] else None,
                    "location": r[4],
                }
                for r in rows
            ],
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()


def _resolve_target_id(cur, id: Optional[int], match_text: Optional[str], date_local: Optional[str]):
    if id is not None:
        return id, None

    if not match_text or not date_local:
        return None, "Sem 'id': informe match_text E date_local para localizar o evento."

    cur.execute(
        f"""
        SELECT e.id
        FROM events e
        WHERE (e.title ILIKE %s OR e.notes ILIKE %s OR e.source_text ILIKE %s)
          AND {_local_date_filter_sql("e.start_time")}
        ORDER BY e.start_time DESC
        LIMIT 1;
        """,
        (f"%{match_text}%", f"%{match_text}%", f"%{match_text}%", date_local),
    )
    row = cur.fetchone()
    if not row:
        return None, "Nenhum evento encontrado para os filtros fornecidos."
    return row[0], None


# ==============================================================================
# TOOL: update_event
# ==============================================================================
@tool("update_event", args_schema=UpdateEventArgs)
def update_event(
    id: Optional[int] = None,
    match_text: Optional[str] = None,
    date_local: Optional[str] = None,
    title: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    location: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Atualiza um compromisso/evento existente.
    Estratégias:
      - Se 'id' for informado: atualiza diretamente por ID.
      - Caso contrário: localiza o evento mais recente que combine (match_text em
        title/notes/source_text) E (date_local em America/Sao_Paulo), então atualiza.
    """
    if not any([title, start_time, end_time, location, notes]):
        return {"status": "error", "message": "Nada para atualizar: forneça pelo menos um campo."}

    conn = get_conn()
    cur = conn.cursor()
    try:
        target_id, erro = _resolve_target_id(cur, id, match_text, date_local)
        if erro:
            return {"status": "error", "message": erro}

        sets = []
        params: List[object] = []
        if title is not None:
            sets.append("title = %s")
            params.append(title)
        if start_time is not None:
            sets.append("start_time = %s::timestamptz")
            params.append(start_time)
        if end_time is not None:
            sets.append("end_time = %s::timestamptz")
            params.append(end_time)
        if location is not None:
            sets.append("location = %s")
            params.append(location)
        if notes is not None:
            sets.append("notes = %s")
            params.append(notes)

        params.append(target_id)

        cur.execute(f"UPDATE events SET {', '.join(sets)} WHERE id = %s;", params)
        rows_affected = cur.rowcount
        conn.commit()

        cur.execute(
            "SELECT id, title, start_time, end_time, location, notes, source_text FROM events WHERE id = %s;",
            (target_id,),
        )
        r = cur.fetchone()
        updated = None
        if r:
            updated = {
                "id": r[0],
                "title": r[1],
                "start_time": str(r[2]),
                "end_time": str(r[3]) if r[3] else None,
                "location": r[4],
                "notes": r[5],
                "source_text": r[6],
            }

        return {"status": "ok", "rows_affected": rows_affected, "id": target_id, "updated": updated}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# ==============================================================================
# TOOL: delete_event
# ==============================================================================
@tool("delete_event", args_schema=DeleteEventArgs)
def delete_event(
    id: Optional[int] = None,
    match_text: Optional[str] = None,
    date_local: Optional[str] = None,
) -> dict:
    """
    Remove um compromisso/evento do banco de dados.
    Estratégias:
      - Se 'id' for informado: remove diretamente por ID.
      - Caso contrário: localiza o evento mais recente que combine (match_text em
        title/notes/source_text) E (date_local em America/Sao_Paulo), então remove.
    Sempre confirme com o usuário antes de chamar esta tool.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        target_id, erro = _resolve_target_id(cur, id, match_text, date_local)
        if erro:
            return {"status": "error", "message": erro}

        cur.execute("SELECT id, title, start_time FROM events WHERE id = %s;", (target_id,))
        removido = cur.fetchone()

        cur.execute("DELETE FROM events WHERE id = %s;", (target_id,))
        rows_affected = cur.rowcount
        conn.commit()

        return {
            "status": "ok",
            "rows_affected": rows_affected,
            "id": target_id,
            "removido": {"id": removido[0], "title": removido[1], "start_time": str(removido[2])}
            if removido
            else None,
        }
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


# Exporta a lista de tools
TOOLS_AGENDA = [add_event, query_events, check_conflicts, update_event, delete_event]
