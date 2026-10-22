"""Banco SQLite do lab, com dados 100% fictícios.

Os dados são recriados a cada inicialização (e pelo botão "Reiniciar dados"),
então o lab sempre começa do mesmo ponto.
"""

import os
import sqlite3
import threading
from datetime import date, datetime, timedelta

DB_PATH = os.environ.get("DB_PATH", "/tmp/colliers_lab.db")
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

# Versões usadas pelo painel para buscar só o que mudou.
estado = {"versao_dados": 1, "ultimo_evento": 0}


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def consultar(sql: str, params: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in conn().execute(sql, params).fetchall()]


def executar(sql: str, params: tuple = ()) -> int:
    with _lock:
        cur = conn().execute(sql, params)
        conn().commit()
        estado["versao_dados"] += 1
        return cur.lastrowid


def contar(tabela: str) -> int:
    with _lock:
        return conn().execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def registrar_evento(ferramenta: str, tipo: str, autor: str, resumo: str, origem: str) -> None:
    with _lock:
        conn().execute(
            "INSERT INTO eventos (quando, ferramenta, tipo, autor, resumo, origem) VALUES (?,?,?,?,?,?)",
            (agora(), ferramenta, tipo, autor or "", resumo[:300], origem),
        )
        conn().commit()
        estado["ultimo_evento"] = conn().execute("SELECT MAX(id) FROM eventos").fetchone()[0]


SCHEMA = """
DROP TABLE IF EXISTS contratos;
DROP TABLE IF EXISTS alertas;
DROP TABLE IF EXISTS oportunidades;
DROP TABLE IF EXISTS interacoes;
DROP TABLE IF EXISTS encaminhamentos;
DROP TABLE IF EXISTS inadimplencia;
DROP TABLE IF EXISTS cartas;
DROP TABLE IF EXISTS eventos;

CREATE TABLE contratos (
  id TEXT PRIMARY KEY, cliente TEXT, imovel TEXT, cidade TEXT, tipo TEXT,
  area_m2 INTEGER, inicio TEXT, vencimento TEXT, valor_mensal REAL,
  indice_reajuste TEXT, mes_reajuste INTEGER, aviso_previo_dias INTEGER, texto TEXT
);
CREATE TABLE alertas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, contrato_id TEXT, data TEXT, tipo TEXT,
  descricao TEXT, autor TEXT, criado_em TEXT
);
CREATE TABLE oportunidades (
  id TEXT PRIMARY KEY, empresa TEXT, linha_servico TEXT, estagio TEXT,
  valor_estimado REAL, responsavel TEXT, origem TEXT, descricao TEXT, atualizado_em TEXT
);
CREATE TABLE interacoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, oportunidade_id TEXT, resumo TEXT,
  proximos_passos TEXT, autor TEXT, criado_em TEXT
);
CREATE TABLE encaminhamentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, oportunidade_id TEXT, time_destino TEXT,
  justificativa TEXT, status TEXT, autor TEXT, criado_em TEXT, decidido_em TEXT
);
CREATE TABLE inadimplencia (
  id TEXT PRIMARY KEY, inquilino TEXT, empreendimento TEXT, contrato_id TEXT,
  dias_atraso INTEGER, valor_em_aberto REAL, ultimo_contato TEXT
);
CREATE TABLE cartas (
  id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT, referencia_id TEXT, texto TEXT,
  status TEXT, autor TEXT, criado_em TEXT, decidido_em TEXT
);
CREATE TABLE eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT, quando TEXT, ferramenta TEXT, tipo TEXT,
  autor TEXT, resumo TEXT, origem TEXT
);
"""


def _texto_contrato(c: dict) -> str:
    return f"""CONTRATO DE LOCAÇÃO NÃO RESIDENCIAL Nº {c['id']} (DOCUMENTO FICTÍCIO PARA FINS DIDÁTICOS)

LOCATÁRIA: {c['cliente']}
IMÓVEL: {c['imovel']}, {c['cidade']}, área privativa de {c['area_m2']} m².

CLÁUSULA 1 – OBJETO. Locação do imóvel acima para uso como {c['tipo'].lower()}.
CLÁUSULA 2 – PRAZO. Vigência de {c['inicio']} a {c['vencimento']}.
CLÁUSULA 3 – ALUGUEL. Valor mensal de R$ {_brl(c['valor_mensal'])}, com vencimento todo dia 10.
CLÁUSULA 4 – REAJUSTE. Reajuste anual pelo {c['indice_reajuste']}, aplicado sempre no mês {c['mes_reajuste']:02d} de cada ano.
CLÁUSULA 5 – RENOVAÇÃO. A LOCATÁRIA que desejar renovar deverá manifestar interesse por escrito com antecedência mínima de {c['aviso_previo_dias']} dias do vencimento.
CLÁUSULA 6 – RESCISÃO ANTECIPADA. Multa equivalente a 3 aluguéis, proporcional ao prazo restante.
CLÁUSULA 7 – BENFEITORIAS. Dependem de aprovação prévia e por escrito da LOCADORA.
CLÁUSULA 8 – SEGURO. A LOCATÁRIA manterá seguro patrimonial do imóvel durante toda a vigência.
"""


def _brl(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def semear() -> None:
    hoje = date.today()

    def d(dias: int) -> str:
        return (hoje + timedelta(days=dias)).isoformat()

    contratos = [
        # id, cliente, imóvel, cidade, tipo, área, início (dias), vencimento (dias), valor, índice, mês, aviso
        ("C-101", "Vértice Tecnologia", "Torre Aurora, 14º andar", "São Paulo", "Escritório", 1200, -1700, 125, 186000, "IGP-M", 3, 180),
        ("C-102", "Alfa Logística", "Condomínio Logístico Cajamar, galpão G3", "Cajamar", "Galpão logístico", 18500, -1400, 300, 412000, "IPCA", 7, 180),
        ("C-103", "Nexo Farma", "Centro Empresarial Paulista Norte, conj. 801", "São Paulo", "Escritório", 640, -900, 70, 98000, "IPCA", 11, 90),
        ("C-104", "Atlas Varejo", "Parque Industrial Extrema, módulo 5", "Extrema", "Galpão logístico", 9200, -1000, 210, 201000, "IGP-M", 1, 180),
        ("C-105", "Lumen Seguros", "Edifício Mirante Berrini, 6º ao 8º andar", "São Paulo", "Escritório", 3300, -2000, 460, 520000, "IPCA", 5, 240),
        ("C-106", "Rio Claro Alimentos", "Centro de Distribuição Anhanguera, doca 2", "Jundiaí", "Galpão logístico", 12700, -600, 520, 265000, "IPCA", 9, 180),
        ("C-107", "Cobalto Energia", "Edifício Atlântico, sala 1203", "Rio de Janeiro", "Escritório", 420, -1300, 45, 61000, "IGP-M", 12, 90),
        ("C-108", "Orbe Educação", "Campus Corporativo Barra Funda, bloco B", "São Paulo", "Escritório", 2100, -800, 640, 238000, "IPCA", 2, 180),
        ("C-109", "Ponte Telecom", "Galpão Viracopos Sul, módulo 2", "Campinas", "Galpão logístico", 6400, -1500, 160, 132000, "IGP-M", 6, 120),
        ("C-110", "Grupo Horizonte", "Torre Aurora, 20º andar", "São Paulo", "Escritório", 1200, -300, 900, 192000, "IPCA", 10, 180),
    ]
    oportunidades = [
        ("OP-201", "Vértice Tecnologia", "Escritórios Corporativos", "Qualificação", 2200000, "[sem responsável]", "Vencimento de contrato", "Contrato atual vence em breve; avaliar expansão para 1.800 m²."),
        ("OP-202", "Fundo Imobiliário Cerrado", "Mercado de Capitais", "Prospecção", 85000000, "Mercado de Capitais", "Movimentação de fundo", "Fundo sinalizou venda de dois ativos logísticos."),
        ("OP-203", "Alfa Logística", "Industrial e Logística", "Proposta", 4900000, "Industrial e Logística", "Cliente da base", "Busca segundo galpão de 15.000 m² no eixo Anhanguera."),
        ("OP-204", "Família Duarte (family office)", "Mercado de Capitais", "Prospecção", 120000000, "[sem responsável]", "Indicação", "Estrutura patrimonial tradicional; avaliar migração para fundo."),
        ("OP-205", "Construtora Vale Verde", "Terrenos", "Qualificação", 18000000, "Terrenos", "Site", "Procura terreno de 20.000 m² para residencial na zona sul."),
        ("OP-206", "Nexo Farma", "Escritórios Corporativos", "Negociação", 1100000, "Escritórios Corporativos", "Vencimento de contrato", "Renovação com possível redução de área."),
        ("OP-207", "Atlas Varejo", "Industrial e Logística", "Qualificação", 2600000, "[sem responsável]", "Vencimento de contrato", "Avaliar renovação ou mudança para galpão maior."),
        ("OP-208", "Grupo Horizonte", "Terrenos", "Prospecção", 9500000, "[sem responsável]", "Venda cruzada", "Cliente de escritórios citou terreno ocioso em Campinas."),
    ]
    inadimplencia = [
        ("IN-301", "Café Esquina Ltda.", "Shopping Center Vila Nova", "C-901", 12, 18400, d(-5)),
        ("IN-302", "Ótica Clara", "Shopping Center Vila Nova", "C-902", 47, 36200, d(-30)),
        ("IN-303", "Studio Fit Academia", "Mall Jardim Sul", "C-903", 95, 88700, d(-60)),
        ("IN-304", "Papelaria Ponto", "Mall Jardim Sul", "C-904", 5, 6100, d(-2)),
        ("IN-305", "Restaurante Sabor da Serra", "Centro Comercial Alphaville", "C-905", 63, 52300, d(-41)),
        ("IN-306", "Clínica Bem Estar", "Centro Comercial Alphaville", "C-906", 30, 27500, d(-20)),
    ]

    with _lock:
        c = conn()
        c.executescript(SCHEMA)
        for (cid, cli, imo, cid_, tipo, area, ini, ven, val, ind, mes, aviso) in contratos:
            reg = dict(id=cid, cliente=cli, imovel=imo, cidade=cid_, tipo=tipo, area_m2=area,
                       inicio=d(ini), vencimento=d(ven), valor_mensal=val, indice_reajuste=ind,
                       mes_reajuste=mes, aviso_previo_dias=aviso)
            reg["texto"] = _texto_contrato(reg)
            c.execute(
                "INSERT INTO contratos VALUES (:id,:cliente,:imovel,:cidade,:tipo,:area_m2,:inicio,:vencimento,:valor_mensal,:indice_reajuste,:mes_reajuste,:aviso_previo_dias,:texto)",
                reg,
            )
        for o in oportunidades:
            c.execute("INSERT INTO oportunidades VALUES (?,?,?,?,?,?,?,?,?)", (*o, agora()))
        for i in inadimplencia:
            c.execute("INSERT INTO inadimplencia VALUES (?,?,?,?,?,?,?)", i)
        c.execute(
            "INSERT INTO interacoes (oportunidade_id, resumo, proximos_passos, autor, criado_em) VALUES (?,?,?,?,?)",
            ("OP-203", "Visita ao galpão G3 com o diretor de operações.", "Enviar três opções de galpão até sexta.", "Equipe Industrial", agora()),
        )
        c.commit()
        estado["versao_dados"] += 1
    registrar_evento("reiniciar_dados", "sistema", "Instrutor", "Dados fictícios recriados.", "Sistema")
