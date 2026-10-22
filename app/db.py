"""Armazenamento genérico da plataforma: registros, aprovações, auditoria e feed.

Todos os módulos ficam numa tabela só (registros), com os dados em JSON. Isso
deixa a plataforma genérica: um módulo novo em schema.py já funciona aqui.
"""

import copy
import json
import os
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

from .schema import ACOES_PADRAO, ENTIDADES, POLITICAS_PADRAO

DB_PATH = os.environ.get("DB_PATH", "/tmp/colliers_hub.db")
FUSO = timezone(timedelta(hours=-3))  # horário de Brasília, sem depender de tzdata

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

# Estado em memória: versão (para o painel buscar só o que mudou) e governança.
estado = {"versao": 1, "ultimo_evento": 0}
politicas: dict[str, dict] = {}
sensiveis: dict[str, list[str]] = {}
acoes: dict[str, str] = {}


def restaurar_politicas() -> None:
    politicas.clear()
    politicas.update(copy.deepcopy(POLITICAS_PADRAO))
    sensiveis.clear()
    for nome, ent in ENTIDADES.items():
        sensiveis[nome] = [c for c, d in ent["campos"].items() if d.get("sensivel")]
    acoes.clear()
    acoes.update(ACOES_PADRAO)


restaurar_politicas()


def hoje() -> date:
    return datetime.now(FUSO).date()


def agora() -> str:
    return datetime.now(FUSO).strftime("%Y-%m-%d %H:%M:%S")


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def tocar() -> None:
    estado["versao"] += 1


SCHEMA_SQL = """
DROP TABLE IF EXISTS registros;
DROP TABLE IF EXISTS contadores;
DROP TABLE IF EXISTS aprovacoes;
DROP TABLE IF EXISTS auditoria;
DROP TABLE IF EXISTS eventos;
CREATE TABLE registros (
  entidade TEXT, id TEXT, dados TEXT, criado_em TEXT, criado_por TEXT,
  atualizado_em TEXT, atualizado_por TEXT, PRIMARY KEY (entidade, id)
);
CREATE TABLE contadores (entidade TEXT PRIMARY KEY, n INTEGER);
CREATE TABLE aprovacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, operacao TEXT, entidade TEXT, registro_id TEXT,
  dados TEXT, antes TEXT, motivo_aprovacao TEXT, autor TEXT, justificativa TEXT, origem TEXT,
  status TEXT, criado_em TEXT, decidido_em TEXT, decidido_por TEXT, comentario TEXT, resultado TEXT
);
CREATE TABLE auditoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, operacao TEXT, entidade TEXT, registro_id TEXT,
  antes TEXT, depois TEXT, autor TEXT, origem TEXT, aprovacao_id INTEGER
);
CREATE TABLE eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, ferramenta TEXT, tipo TEXT,
  autor TEXT, resumo TEXT, origem TEXT, entidade TEXT, registro_id TEXT
);
"""


def criar_tabelas() -> None:
    with _lock:
        conn().executescript(SCHEMA_SQL)
        conn().commit()


# ---------------------------------------------------------------- registros


def _linha(r: sqlite3.Row) -> dict:
    d = json.loads(r["dados"])
    return {"id": r["id"], **d, "_criado_em": r["criado_em"], "_criado_por": r["criado_por"],
            "_atualizado_em": r["atualizado_em"], "_atualizado_por": r["atualizado_por"]}


def todos(entidade: str) -> list[dict]:
    with _lock:
        rs = conn().execute("SELECT * FROM registros WHERE entidade = ? ORDER BY id", (entidade,)).fetchall()
    return [_linha(r) for r in rs]


def um(entidade: str, rid: str) -> dict | None:
    with _lock:
        r = conn().execute("SELECT * FROM registros WHERE entidade = ? AND id = ?", (entidade, rid)).fetchone()
    return _linha(r) if r else None


def contar(entidade: str) -> int:
    with _lock:
        return conn().execute("SELECT COUNT(*) FROM registros WHERE entidade = ?", (entidade,)).fetchone()[0]


def proximo_id(entidade: str) -> str:
    pref = ENTIDADES[entidade]["prefixo"]
    with _lock:
        r = conn().execute("SELECT n FROM contadores WHERE entidade = ?", (entidade,)).fetchone()
        n = (r["n"] if r else 0) + 1
        conn().execute("INSERT OR REPLACE INTO contadores VALUES (?, ?)", (entidade, n))
    return f"{pref}-{n:03d}"


def _limpo(dados: dict) -> dict:
    return {k: v for k, v in dados.items() if k != "id" and not k.startswith("_")}


def inserir(entidade: str, dados: dict, autor: str) -> str:
    with _lock:
        rid = proximo_id(entidade)
        t = agora()
        conn().execute("INSERT INTO registros VALUES (?,?,?,?,?,?,?)",
                       (entidade, rid, json.dumps(_limpo(dados), ensure_ascii=False), t, autor, t, autor))
        conn().commit()
        tocar()
    return rid


def gravar(entidade: str, rid: str, dados: dict, autor: str) -> None:
    with _lock:
        conn().execute("UPDATE registros SET dados = ?, atualizado_em = ?, atualizado_por = ? WHERE entidade = ? AND id = ?",
                       (json.dumps(_limpo(dados), ensure_ascii=False), agora(), autor, entidade, rid))
        conn().commit()
        tocar()


def apagar(entidade: str, rid: str) -> None:
    with _lock:
        conn().execute("DELETE FROM registros WHERE entidade = ? AND id = ?", (entidade, rid))
        conn().commit()
        tocar()


# ---------------------------------------------------------------- feed e auditoria


def evento(ferramenta: str, tipo: str, autor: str, resumo: str, origem: str,
           entidade: str = "", registro_id: str = "") -> None:
    with _lock:
        cur = conn().execute(
            "INSERT INTO eventos (quando, ferramenta, tipo, autor, resumo, origem, entidade, registro_id) VALUES (?,?,?,?,?,?,?,?)",
            (agora(), ferramenta, tipo, autor or "", resumo[:300], origem, entidade, registro_id))
        conn().commit()
        estado["ultimo_evento"] = cur.lastrowid


def auditar(operacao: str, entidade: str, rid: str, antes, depois, autor: str, origem: str, aprovacao_id=None) -> None:
    with _lock:
        conn().execute(
            "INSERT INTO auditoria (quando, operacao, entidade, registro_id, antes, depois, autor, origem, aprovacao_id) VALUES (?,?,?,?,?,?,?,?,?)",
            (agora(), operacao, entidade, rid, json.dumps(antes, ensure_ascii=False) if antes is not None else None,
             json.dumps(depois, ensure_ascii=False) if depois is not None else None, autor, origem, aprovacao_id))
        conn().commit()


def consultar(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


# ---------------------------------------------------------------- aprovações


def _aprov(r: dict) -> dict:
    for k in ("dados", "antes", "resultado"):
        if r.get(k):
            try:
                r[k] = json.loads(r[k])
            except (TypeError, ValueError):
                pass
    return r


def nova_aprovacao(operacao: str, entidade: str, rid: str | None, dados, antes, motivo: str,
                   autor: str, justificativa: str, origem: str) -> int:
    with _lock:
        cur = conn().execute(
            "INSERT INTO aprovacoes (operacao, entidade, registro_id, dados, antes, motivo_aprovacao, autor, justificativa, origem, status, criado_em) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (operacao, entidade, rid, json.dumps(dados, ensure_ascii=False), json.dumps(antes, ensure_ascii=False) if antes else None,
             motivo, autor, justificativa, origem, "pendente", agora()))
        conn().commit()
        tocar()
        return cur.lastrowid


def aprovacao(aid: int) -> dict | None:
    r = consultar("SELECT * FROM aprovacoes WHERE id = ?", (aid,))
    return _aprov(r[0]) if r else None


def aprovacoes(status: str | None = None, limite: int = 200) -> list[dict]:
    if status:
        rs = consultar("SELECT * FROM aprovacoes WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limite))
    else:
        rs = consultar("SELECT * FROM aprovacoes ORDER BY id DESC LIMIT ?", (limite,))
    return [_aprov(r) for r in rs]


def fechar_aprovacao(aid: int, status: str, por: str, comentario: str, resultado) -> None:
    with _lock:
        conn().execute("UPDATE aprovacoes SET status = ?, decidido_em = ?, decidido_por = ?, comentario = ?, resultado = ? WHERE id = ?",
                       (status, agora(), por, comentario, json.dumps(resultado, ensure_ascii=False), aid))
        conn().commit()
        tocar()
