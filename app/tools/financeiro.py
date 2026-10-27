import os
from dotenv import load_dotenv
import psycopg2
from typing import Optional
from langchain.tools import tool
from pydantic import BaseModel, Field

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  

def get_conn():
    return psycopg2.connect(DATABASE_URL)

# Essa classe garante que o objeto de Python passe todos esses campos
class AddTransactionArgs(BaseModel):
    amount: float = Field(..., description="Valor da transação (use positivo).")
    source_text: str = Field(..., description="Texto original do usuário.")
    occurred_at: Optional[str] = Field(
        default=None,
        description="Timestamp ISO 8601; se ausente, usa NOW() no banco."
    )
    type_id: Optional[int] = Field(default=None, description="ID em transaction_types (1=INCOME, 2=EXPENSES, 3=TRANSFER).")
    type_name: Optional[str] = Field(default=None, description="Nome do tipo: INCOME | EXPENSES | TRANSFER.")
    category_id: Optional[int] = Field(default=None, description="FK de categories (opcional).")
    category_name: Optional[str] = Field(default=None, description="Procure na tabela categories: (1=comida, 2=besteira, 3=estudo, 4=férias, 5=transporte, 6=moradia, 7=saúde, 8=lazer, 9=contas, 10=investimento, 11=presente, 12=outros).")
    description: Optional[str] = Field(default=None, description="Descrição (opcional).")
    payment_method: Optional[str] = Field(default=None, description="Forma de pagamento (opcional).")
    
# Essa classe garante que o objeto de Python passe todos esses campos
class QueryTransactionsArgs(BaseModel):
    source_text: Optional[str] = Field(default=None, description="Texto original do usuário.")
    type_id: Optional[int] = Field(default=None, description="ID em transaction_types (1=INCOME, 2=EXPENSES, 3=TRANSFER).")
    initial_date: Optional[str] = Field(default=None, description="Primeira data no formato YYYY-MM-DD do intervalo que será usada para buscar transações no banco.")
    final_date: Optional[str] = Field(default=None, description="Data final no formato YYYY-MM-DD do interavalo de transações que serão buscadas.")
    
class UpdateTransactionArgs(BaseModel):
    id: Optional[int] = Field(
        default=None,
        description="ID da transação a atualizar. Se ausente, será feita uma busca por (match_text + date_local)."
    )
    match_text: Optional[str] = Field(
        default=None,
        description="Texto para localizar transação quando id não for informado (busca em source_text/description)."
    )
    date_local: Optional[str] = Field(
        default=None,
        description="Data local (YYYY-MM-DD) em America/Sao_Paulo; usado em conjunto com match_text quando id ausente."
    )
    amount: Optional[float] = Field(default=None, description="Novo valor.")
    type_id: Optional[int] = Field(default=None, description="Novo type_id (1/2/3).")
    type_name: Optional[str] = Field(default=None, description="Novo type_name: INCOME | EXPENSES | TRANSFER.")
    category_id: Optional[int] = Field(default=None, description="Nova categoria (id).")
    category_name: Optional[str] = Field(default=None, description="Nova categoria (nome).")
    description: Optional[str] = Field(default=None, description="Nova descrição.")
    payment_method: Optional[str] = Field(default=None, description="Novo meio de pagamento.")
    occurred_at: Optional[str] = Field(default=None, description="Novo timestamp ISO 8601.")
    
    
TYPE_ALIASES = {
    "INCOME": "INCOME", "ENTARDA": "INCOME", "RECEITA": "INCOME", "SALÁRIO": "INCOME",
    "EXPENSE": "EXPENSES", "EXPENSES": "EXPENSES", "DESPESA": "EXPENSES", "GASTO": "EXPENSES",
    "TRANSFER": "TRANSFER", "TRANSFERÊNCIA": "TRANSFER", "TRANSFERENCIA": "TRANSFER"
}

CATEGORY_ALIASES = {
    # COMIDA
    "COMIDA": "comida", "ALIMENTO": "comida", "ALIMENTOS": "comida",
    "RESTAURANTE": "comida", "LANCHONETE": "comida", "FAST FOOD": "comida",
    "MC DONALDS": "comida", "MCDONALD'S": "comida", "BURGER KING": "comida",
    "PIZZA": "comida", "HAMBURGUER": "comida", "LANCHE": "comida",
    "ALMOÇO": "comida", "JANTAR": "comida", "CAFÉ": "comida",
    "ARROZ": "comida", "FEIJÃO": "comida", "COMPRAS MERCADO": "comida",
    "SUPERMERCADO": "comida", "IFOOD": "comida",

    # BESTEIRA
    "BESTEIRA": "besteira", "DOCE": "besteira", "DOCES": "besteira",
    "CHOCOLATE": "besteira", "BALAS": "besteira", "BALA": "besteira",
    "SORVETE": "besteira", "SNACK": "besteira", "SALGADINHO": "besteira",
    "REFRIGERANTE": "besteira", "COCA": "besteira",

    # ESTUDO
    "ESTUDO": "estudo", "ESCOLA": "estudo", "FACULDADE": "estudo",
    "CURSO": "estudo", "CURSOS": "estudo", "LIVRO": "estudo",
    "LIVROS": "estudo", "MATERIAL": "estudo", "CADERNO": "estudo",
    "CANETA": "estudo", "APOSTILA": "estudo", "EDUCAÇÃO": "estudo",

    # FÉRIAS
    "FERIAS": "férias", "FÉRIAS": "férias", "VIAGEM": "férias",
    "HOTEL": "férias", "PASSAGEM": "férias", "AVIÃO": "férias",
    "AEROPORTO": "férias", "RESORT": "férias", "TURISMO": "férias",

    # TRANSPORTE
    "TRANSPORTE": "transporte", "UBER": "transporte", "99": "transporte",
    "TAXI": "transporte", "ÔNIBUS": "transporte", "METRO": "transporte",
    "GASOLINA": "transporte", "COMBUSTIVEL": "transporte",
    "PEDAGIO": "transporte", "ESTACIONAMENTO": "transporte",

    # MORADIA
    "MORADIA": "moradia", "ALUGUEL": "moradia", "CONDOMINIO": "moradia",
    "CASA": "moradia", "APARTAMENTO": "moradia", "REFORMA": "moradia",
    "MÓVEIS": "moradia", "MOVEIS": "moradia",

    # SAÚDE
    "SAUDE": "saúde", "SAÚDE": "saúde", "MEDICO": "saúde",
    "CONSULTA": "saúde", "HOSPITAL": "saúde", "REMEDIO": "saúde",
    "REMÉDIO": "saúde", "FARMACIA": "saúde", "PLANO DE SAUDE": "saúde",
    "DENTISTA": "saúde",

    # LAZER
    "LAZER": "lazer", "CINEMA": "lazer", "FILME": "lazer",
    "NETFLIX": "lazer", "SPOTIFY": "lazer", "JOGO": "lazer",
    "GAMES": "lazer", "SHOW": "lazer", "FESTA": "lazer",
    "BALADA": "lazer",

    # CONTAS
    "CONTAS": "contas", "BOLETO": "contas", "LUZ": "contas",
    "ÁGUA": "contas", "AGUA": "contas", "INTERNET": "contas",
    "WIFI": "contas", "ENERGIA": "contas", "TELEFONE": "contas",

    # INVESTIMENTO
    "INVESTIMENTO": "investimento", "INVESTIR": "investimento",
    "AÇÃO": "investimento", "ACOES": "investimento", "AÇÕES": "investimento",
    "CRIPTO": "investimento", "BITCOIN": "investimento",
    "RENDA FIXA": "investimento", "TESOURO DIRETO": "investimento",

    # PRESENTE
    "PRESENTE": "presente", "PRESENTEAR": "presente",
    "ANIVERSARIO": "presente", "ANIVERSÁRIO": "presente",
    "NATAL": "presente", "SURPRESA": "presente", "AMIGO SECRETO": "presente",

    # OUTROS
    "OUTROS": "outros", "DIVERSOS": "outros", "VARIOS": "outros"
}

#Garante que o campo type da tabela transactions receba um id válido (1=INCOME, 2=EXPENSES, 3=TRANSFER
def _resolve_type_id(cur, type_id: Optional[int], type_name: Optional[str]) -> Optional[int]:
    if type_name:
        t = type_name.strip().upper()
        if t in TYPE_ALIASES:
            t = TYPE_ALIASES[t]
        cur.execute("SELECT id FROM transaction_types WHERE UPPER(type)=%s LIMIT 1;", (t,))
        row = cur.fetchone()
        return row[0] if row else None
    if type_id:
        return int(type_id)
    return 2

#Garante que o campo category_id da tabela transactions seja preenchido com um id válido (1=comida, 2=besteira, 3=estudo, 4=férias, 5=transporte, 6=moradia, 7=saúde, 8=lazer, 9=contas, 10=investimento, 11=presente, 12=outros)
def _resolve_category_name(cur, category_id: Optional[int], category_name: Optional[str]) -> Optional[int]:
    if category_name:
        cn = category_name.strip().lower()
        if cn in CATEGORY_ALIASES:
            cn = CATEGORY_ALIASES[cn]
        cur.execute("SELECT id FROM categories WHERE name = LOWER(%s) LIMIT 1;", (cn,))
        row = cur.fetchone()
        return row[0] if row else None
    if category_id:
        return int(category_id)
    return 2


# Tool: add_transaction
@tool("add_transaction", args_schema=AddTransactionArgs)
def add_transaction(
    amount: float,
    source_text: str,
    occurred_at: Optional[str] = None,
    type_id: Optional[int] = None,
    type_name: Optional[str] = None,
    category_id: int = None,
    category_name: Optional[str] = None,
    description: Optional[str] = None,
    payment_method: Optional[str] = None,
) -> dict:
    """Insere uma transação financeira no banco de dados Postgres.""" # docstring obrigatório da @tools do langchain (estranho, mas legal né?)
    conn = get_conn()
    cur = conn.cursor()
    try:
        resolved_type_id = _resolve_type_id(cur, type_id, type_name)
        resolved_category_id = _resolve_category_name(cur, category_id, category_name)
        
        amount = float(amount)
    
        if not resolved_type_id:
            return {"status": "error", "message": "Tipo inválido (use type_id ou type_name: INCOME/EXPENSES/TRANSFER)."}
        
        if not resolved_category_id:
            return {"status": "error", "message": "Categoria inválida"}

        if occurred_at:
            cur.execute(
                """
                INSERT INTO transactions
                    (amount, type, category_id, description, payment_method, occurred_at, source_text)
                VALUES
                    (%s, %s, %s, %s, %s, %s::timestamptz, %s)
                RETURNING id, occurred_at;
                """,
                (amount, resolved_type_id, resolved_category_id, description, payment_method, occurred_at, source_text),
            )
        else:
            cur.execute(
                """
                INSERT INTO transactions
                    (amount, type, category_id, description, payment_method, occurred_at, source_text)
                VALUES
                    (%s, %s, %s, %s, %s, NOW(), %s)
                RETURNING id, occurred_at;
                """,
                (amount, resolved_type_id, resolved_category_id, description, payment_method, source_text),
            )

        new_id, occurred = cur.fetchone()
        conn.commit()
        return {"status": "ok", "id": new_id, "occurred_at": str(occurred)}

    except Exception as e:
        conn.rollback()
        print("ERRO REAL:", e)  # 👈 MUITO IMPORTANTE
        raise e  # 👈 deixa o erro explodir de verdade
        return {"status": "error", "message": str(e)}
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


@tool("query_transactions", args_schema=QueryTransactionsArgs)
def query_transactions(
    source_text: Optional[str] = None, 
    type_id: Optional[int] = None, 
    initial_date: Optional[str] = None, 
    final_date: Optional[str] = None) -> dict:
    """Lista transações entre duas datas."""
    
    conn = get_conn()
    cur = conn.cursor()
    query = """SELECT source_text, amount, occurred_at, categories.name FROM transactions 
                JOIN categories ON category_id = categories.id"""
    params = []
    

    try:
        if source_text:
            query += " AND (source_text LIKE %s OR description LIKE %s)"
            params.extend([f"%{source_text}%", f"%{source_text}%"])

        if type_id:
            query += " AND type = %s"
            params.append(type_id)

        if initial_date and final_date:
            query += """ AND occurred_at >= %s::timestamp
                         AND occurred_at < %s::timestamp + INTERVAL '1 day'
                         GROUP BY source_text, amount, occurred_at, categories.name
                         ORDER BY occurred_at"""
            params.extend([initial_date, final_date])
        else:
            if initial_date:
                query += " AND (occurred_at AT TIME ZONE 'America/Sao_Paulo')::date = %s::date"
                params.append(initial_date)
            query += " ORDER BY occurred_at DESC"

        cur.execute(query, params)
        rows = cur.fetchall()
        

        return {
            "status": "ok",
            "transactions": rows
        }
    
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    
    finally:
        cur.close()
        conn.close()
        
# TOOL para buscar o balanço diário das transações
@tool("daily_balance")
def daily_balance() -> dict:
    """Mostra o balanço diário de transações."""
    
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(""" 
            SELECT 
                SUM(CASE WHEN type = 1 THEN amount ELSE -amount END) as balance
            FROM transactions
            WHERE (occurred_at AT TIME ZONE 'America/Sao_Paulo')::date = CURRENT_DATE
            GROUP BY DATE(occurred_at);
        """)

        rows = cur.fetchall()

        return {
            "status": "ok",
            "transactions": rows
        }
    
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    
    finally:
        cur.close()
        conn.close()    


# TOOL para buscar o balanço diário das transações
@tool("total_balance")
def total_balance() -> dict:
    """Mostra o balanço total de transações, do começo ao fim."""
    
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(""" 
            SELECT 
                SUM(CASE WHEN ts.type = 1 THEN ts.amount ELSE -ts.amount END) 
            FROM transactions ts 
            WHERE ts.type != 3;
        """)

        rows = cur.fetchall()

        return {
            "status": "ok",
            "transactions": rows
        }
    
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    
    finally:
        cur.close()
        conn.close()    
        

@tool("update_transaction", args_schema=UpdateTransactionArgs)
def update_transaction(
    id: Optional[int] = None,
    match_text: Optional[str] = None,
    date_local: Optional[str] = None,
    amount: Optional[float] = None,
    type_id: Optional[int] = None,
    type_name: Optional[str] = None,
    category_id: Optional[int] = None,
    category_name: Optional[str] = None,
    description: Optional[str] = None,
    payment_method: Optional[str] = None,
    occurred_at: Optional[str] = None,
) -> dict:
    """
    Atualiza uma transação existente.
    Estratégias:
      - Se 'id' for informado: atualiza diretamente por ID.
      - Caso contrário: localiza a transação mais recente que combine (match_text em source_text/description)
        E (date_local em America/Sao_Paulo), então atualiza.
    Retorna: status, rows_affected, id, e o registro atualizado.
    """
    if not any([amount, type_id, type_name, category_id, category_name, description, payment_method, occurred_at]):
        return {"status": "error", "message": "Nada para atualizar: forneça pelo menos um campo (amount, type, category, description, payment_method, occurred_at)."}

    conn = get_conn()
    cur = conn.cursor()
    try:
        # Resolve target_id
        target_id = id
        if target_id is None:
            if not match_text or not date_local:
                return {"status": "error", "message": "Sem 'id': informe match_text E date_local para localizar o registro."}

            # Buscar o mais recente no dia local informado que combine o texto
            cur.execute(
                f"""
                SELECT t.id
                FROM transactions t
                WHERE (t.source_text ILIKE %s OR t.description ILIKE %s)
                  AND {_local_date_filter_sql("t.occurred_at")}
                ORDER BY t.occurred_at DESC
                LIMIT 1;
                """,
                (f"%{match_text}%", f"%{match_text}%", date_local)
            )
            row = cur.fetchone()
            if not row:
                return {"status": "error", "message": "Nenhuma transação encontrada para os filtros fornecidos."}
            target_id = row[0]

        # Resolver type_id / category_id a partir de nomes, se fornecidos
        resolved_type_id = _resolve_type_id(cur, type_id, type_name) if (type_id or type_name) else None
        resolved_category_id = category_id
        if category_name and not category_id:
            resolved_category_id = _resolve_category_name(cur, category_name)

        # Montar SET dinâmico
        sets = []
        params: List[object] = []
        if amount is not None:
            sets.append("amount = %s")
            params.append(amount)
        if resolved_type_id is not None:
            sets.append("type = %s")
            params.append(resolved_type_id)
        if resolved_category_id is not None:
            sets.append("category_id = %s")
            params.append(resolved_category_id)
        if description is not None:
            sets.append("description = %s")
            params.append(description)
        if payment_method is not None:
            sets.append("payment_method = %s")
            params.append(payment_method)
        if occurred_at is not None:
            sets.append("occurred_at = %s::timestamptz")
            params.append(occurred_at)

        if not sets:
            return {"status": "error", "message": "Nenhum campo válido para atualizar."}

        params.append(target_id)

        cur.execute(
            f"UPDATE transactions SET {', '.join(sets)} WHERE id = %s;",
            params
        )
        rows_affected = cur.rowcount
        conn.commit()

        # Retornar o registro atualizado
        cur.execute(
            """
            SELECT
              t.id, t.occurred_at, t.amount, tt.type AS type_name,
              c.name AS category_name, t.description, t.payment_method, t.source_text
            FROM transactions t
            JOIN transaction_types tt ON tt.id = t.type
            LEFT JOIN categories c ON c.id = t.category_id
            WHERE t.id = %s;
            """,
            (target_id,)
        )
        r = cur.fetchone()
        updated = None
        if r:
            updated = {
                "id": r[0],
                "occurred_at": str(r[1]),
                "amount": float(r[2]),
                "type": r[3],
                "category": r[4],
                "description": r[5],
                "payment_method": r[6],
                "source_text": r[7],
            }

        return {
            "status": "ok",
            "rows_affected": rows_affected,
            "id": target_id,
            "updated": updated
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
TOOLS = [add_transaction, query_transactions, daily_balance, total_balance]