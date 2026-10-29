"""Unidade de trabalho do turno: as tools escrevem, o juiz decide se o commit acontece."""

from __future__ import annotations

import contextvars
import itertools
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

import psycopg2

from app.config import DATABASE_URL

# Se o processo travar com a transação aberta, o Postgres derruba a sessão e desfaz a escrita) depois de um tempo parado. 
# Precisa ser maior que o timeout do juiz (30 s) somado ao tempo do orquestrador.
IDLE_IN_TRANSACTION_MS = 90_000

def _conectar():
    return psycopg2.connect(DATABASE_URL)


def _conectar_para_escrita():
    """Conexão do turno. O SET LOCAL vale só para a transação aberta (funciona atrás de pooler)."""
    conn = _conectar()
    with conn.cursor() as cur:
        cur.execute(f"SET LOCAL idle_in_transaction_session_timeout = {int(IDLE_IN_TRANSACTION_MS)}")
    return conn


class TurnoTx:
    """Uma transação por turno. Quem decide o commit é o juiz, não a tool."""

    def __init__(self) -> None:
        self._conn = None
        self._lock = threading.RLock()  # tools em paralelo usam a mesma conexão: uma por vez
        self._seq = itertools.count(1)
        self._quebrada = False
        self.escreveu = False           # alguma escrita deste turno está pendente ou confirmada
        self.estado = "aberto"          # aberto | confirmado | desfeito

    # ------------------------------------------------------------------ uso pelas tools
    @contextmanager
    def cursor(self, escrita: bool) -> Iterator:
        with self._lock:
            if self.estado != "aberto":
                raise RuntimeError(f"turno já {self.estado}: nova escrita não é permitida")

            if self._conn is None:
                if not escrita:
                    # leitura antes de qualquer escrita: igual a antes, conexão própria e curta
                    conn = _conectar()
                    try:
                        with conn.cursor() as cur:
                            yield cur
                    finally:
                        conn.close()
                    return
                self._conn = _conectar_para_escrita()

            nome = f"sp_{next(self._seq)}"
            cur = self._conn.cursor()
            try:
                cur.execute(f"SAVEPOINT {nome}")
                try:
                    yield cur
                except BaseException:
                    # desfaz só o que ESTA tool fez; as anteriores do turno continuam pendentes
                    try:
                        cur.execute(f"ROLLBACK TO SAVEPOINT {nome}")
                        cur.execute(f"RELEASE SAVEPOINT {nome}")
                    except Exception:
                        self._quebrada = True
                    raise
                else:
                    cur.execute(f"RELEASE SAVEPOINT {nome}")
                    if escrita:
                        self.escreveu = True
            finally:
                cur.close()

    def finalizar(self, aprovado: bool) -> None:
        """Único ponto que confirma ou desfaz. Idempotente. Levanta se o commit falhar."""
        with self._lock:
            if self.estado != "aberto":
                return
            conn, self._conn = self._conn, None
            if conn is None:                      # turno sem escrita
                self.estado = "confirmado" if aprovado else "desfeito"
                return
            try:
                if aprovado and not self._quebrada:
                    conn.commit()
                    self.estado = "confirmado"
                else:
                    conn.rollback()
                    self.estado = "desfeito"
                    if aprovado:
                        raise RuntimeError("transação do turno comprometida; escrita desfeita")
            except Exception:
                if self.estado == "aberto":
                    self.estado = "desfeito"
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                raise
            finally:
                try:
                    conn.close()
                except Exception:
                    pass


# ---------------------------------------------------------------------- contexto do turno
_turno: contextvars.ContextVar[Optional[TurnoTx]] = contextvars.ContextVar("turno_tx", default=None)


def iniciar_turno() -> TurnoTx:
    turno = TurnoTx()
    _turno.set(turno)
    return turno


def turno_atual() -> Optional[TurnoTx]:
    return _turno.get()


def encerrar_turno() -> None:
    """Rede de segurança: o que ainda estiver aberto é desfeito. Nunca levanta."""
    turno = _turno.get()
    _turno.set(None)
    if turno is None:
        return
    try:
        turno.finalizar(aprovado=False)
    except Exception as exc:
        print(f"[turno] rollback final falhou: {exc}")


# ---------------------------------------------------------------------- API das tools
@contextmanager
def escrita() -> Iterator:
    """Cursor para tools que gravam. Dentro do grafo: não dá commit, o juiz decide."""
    turno = turno_atual()
    if turno is not None:
        with turno.cursor(escrita=True) as cur:
            yield cur
        return

    # Fora do grafo (ex.: app/mcp_server.py): comportamento de antes, commit ao sair.
    conn = _conectar()
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def leitura() -> Iterator:
    """Cursor para consultas. Dentro do turno enxerga as escritas ainda não confirmadas."""
    turno = turno_atual()
    if turno is not None:
        with turno.cursor(escrita=False) as cur:
            yield cur
        return

    conn = _conectar()
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()