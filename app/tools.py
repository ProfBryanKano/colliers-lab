"""Servidor MCP do Colliers Lab.

Cada função decorada com @mcp.tool vira uma ferramenta que qualquer assistente
compatível com MCP enxerga. A docstring é a descrição que o modelo lê para
decidir quando usar a ferramenta.

Ferramentas de leitura são marcadas como read_only_hint=True. As de escrita
não, e por isso assistentes como o ChatGPT pedem confirmação antes de usá-las.
"""

import contextvars
from datetime import date

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from . import db

# Origem da chamada ("MCP" quando vem de um assistente externo,
# "Chat do lab" quando vem do chat embutido). Aparece no feed ao vivo.
origem = contextvars.ContextVar("origem", default="MCP")

LEITURA = ToolAnnotations(read_only_hint=True, destructive_hint=False)
ESCRITA = ToolAnnotations(read_only_hint=False, destructive_hint=False)

LINHAS = ["Industrial e Logística", "Mercado de Capitais", "Escritórios Corporativos", "Terrenos"]
ESTAGIOS = ["Prospecção", "Qualificação", "Proposta", "Negociação", "Fechado", "Perdido"]
TIPOS_ALERTA = ["renovação", "reajuste", "vencimento", "outro"]
LIMITE_LINHAS = 3000  # proteção simples contra excesso de escritas

mcp = MCPServer(
    "Colliers Lab",
    instructions=(
        "Ambiente de laboratório com dados FICTÍCIOS de uma operação imobiliária: "
        "contratos de locação, oportunidades do CRM, inadimplência de inquilinos, "
        "alertas de datas críticas e cartas. Use as ferramentas de leitura para "
        "consultar e as de escrita para registrar. Toda escrita pede o campo autor: "
        "use o nome do grupo ou da pessoa."
    ),
)


def _log(ferramenta: str, tipo: str, resumo: str, autor: str = "") -> None:
    db.registrar_evento(ferramenta, tipo, autor, resumo, origem.get())


def _autor_ok(autor: str) -> str | None:
    if not autor or not autor.strip():
        return "Informe o campo autor (nome do grupo ou da pessoa) para registrar a escrita."
    return None


def _cheio(tabela: str) -> bool:
    return db.contar(tabela) >= LIMITE_LINHAS


# ---------------------------------------------------------------- LEITURA


@mcp.tool(annotations=LEITURA)
def listar_contratos(vencendo_em_dias: int | None = None, cliente: str | None = None) -> list[dict]:
    """Lista os contratos de locação (sem o texto completo). Filtre por contratos
    que vencem nos próximos N dias (vencendo_em_dias) ou por parte do nome do cliente."""
    sql, p = "SELECT id, cliente, imovel, cidade, tipo, area_m2, inicio, vencimento, valor_mensal, indice_reajuste, mes_reajuste, aviso_previo_dias FROM contratos WHERE 1=1", []
    if vencendo_em_dias is not None:
        sql += " AND julianday(vencimento) - julianday(?) BETWEEN 0 AND ?"
        p += [date.today().isoformat(), vencendo_em_dias]
    if cliente:
        sql += " AND cliente LIKE ?"
        p.append(f"%{cliente}%")
    linhas = db.consultar(sql + " ORDER BY vencimento", tuple(p))
    _log("listar_contratos", "leitura", f"{len(linhas)} contrato(s) consultado(s)")
    return linhas


@mcp.tool(annotations=LEITURA)
def ler_contrato(contrato_id: str) -> dict:
    """Lê o texto completo de um contrato (cláusulas de prazo, reajuste, renovação
    e aviso prévio). Use o id, por exemplo C-101."""
    r = db.consultar("SELECT * FROM contratos WHERE id = ?", (contrato_id.strip().upper(),))
    if not r:
        return {"erro": f"Contrato {contrato_id} não encontrado. Use listar_contratos para ver os ids."}
    _log("ler_contrato", "leitura", f"Leu o contrato {r[0]['id']} ({r[0]['cliente']})")
    return r[0]


@mcp.tool(annotations=LEITURA)
def listar_alertas(contrato_id: str | None = None) -> list[dict]:
    """Lista os alertas de datas críticas já cadastrados, opcionalmente de um contrato."""
    if contrato_id:
        r = db.consultar("SELECT * FROM alertas WHERE contrato_id = ? ORDER BY data", (contrato_id.strip().upper(),))
    else:
        r = db.consultar("SELECT * FROM alertas ORDER BY data")
    _log("listar_alertas", "leitura", f"{len(r)} alerta(s) consultado(s)")
    return r


@mcp.tool(annotations=LEITURA)
def buscar_oportunidades(linha_servico: str | None = None, estagio: str | None = None, texto: str | None = None) -> list[dict]:
    """Busca oportunidades no CRM. Linhas de serviço: Industrial e Logística,
    Mercado de Capitais, Escritórios Corporativos, Terrenos. Estágios: Prospecção,
    Qualificação, Proposta, Negociação, Fechado, Perdido. 'texto' procura no nome
    da empresa e na descrição."""
    sql, p = "SELECT * FROM oportunidades WHERE 1=1", []
    if linha_servico:
        sql += " AND linha_servico LIKE ?"
        p.append(f"%{linha_servico}%")
    if estagio:
        sql += " AND estagio LIKE ?"
        p.append(f"%{estagio}%")
    if texto:
        sql += " AND (empresa LIKE ? OR descricao LIKE ?)"
        p += [f"%{texto}%", f"%{texto}%"]
    r = db.consultar(sql + " ORDER BY valor_estimado DESC", tuple(p))
    _log("buscar_oportunidades", "leitura", f"{len(r)} oportunidade(s) encontrada(s)")
    return r


@mcp.tool(annotations=LEITURA)
def ver_historico_oportunidade(oportunidade_id: str) -> dict:
    """Mostra uma oportunidade com todas as interações registradas e os
    encaminhamentos pedidos para ela."""
    oid = oportunidade_id.strip().upper()
    op = db.consultar("SELECT * FROM oportunidades WHERE id = ?", (oid,))
    if not op:
        return {"erro": f"Oportunidade {oportunidade_id} não encontrada."}
    _log("ver_historico_oportunidade", "leitura", f"Histórico de {oid} ({op[0]['empresa']})")
    return {
        "oportunidade": op[0],
        "interacoes": db.consultar("SELECT * FROM interacoes WHERE oportunidade_id = ? ORDER BY id", (oid,)),
        "encaminhamentos": db.consultar("SELECT * FROM encaminhamentos WHERE oportunidade_id = ? ORDER BY id", (oid,)),
    }


@mcp.tool(annotations=LEITURA)
def listar_inadimplencia(min_dias_atraso: int = 0) -> list[dict]:
    """Lista inquilinos com aluguel em atraso, do mais atrasado para o menos atrasado."""
    r = db.consultar("SELECT * FROM inadimplencia WHERE dias_atraso >= ? ORDER BY dias_atraso DESC", (min_dias_atraso,))
    _log("listar_inadimplencia", "leitura", f"{len(r)} inquilino(s) em atraso consultado(s)")
    return r


@mcp.tool(annotations=LEITURA)
def listar_pendencias() -> dict:
    """Lista o que está aguardando aprovação humana: encaminhamentos de
    oportunidades e cartas em rascunho."""
    r = {
        "encaminhamentos_pendentes": db.consultar("SELECT * FROM encaminhamentos WHERE status = 'pendente' ORDER BY id"),
        "cartas_em_rascunho": db.consultar("SELECT * FROM cartas WHERE status = 'rascunho' ORDER BY id"),
    }
    _log("listar_pendencias", "leitura", "Consultou a fila de aprovações")
    return r


# ---------------------------------------------------------------- ESCRITA


@mcp.tool(annotations=ESCRITA)
def criar_alerta_data_critica(contrato_id: str, data: str, tipo: str, descricao: str, autor: str) -> dict:
    """Cria um alerta de data crítica para um contrato. data no formato AAAA-MM-DD.
    tipo: renovação, reajuste, vencimento ou outro. Exemplo de uso: a data-limite
    do aviso prévio de renovação é o vencimento menos os dias de aviso prévio."""
    if (e := _autor_ok(autor)):
        return {"erro": e}
    cid = contrato_id.strip().upper()
    if not db.consultar("SELECT id FROM contratos WHERE id = ?", (cid,)):
        return {"erro": f"Contrato {contrato_id} não existe."}
    try:
        date.fromisoformat(data)
    except ValueError:
        return {"erro": "Data inválida. Use o formato AAAA-MM-DD, por exemplo 2027-03-15."}
    tipo = tipo.strip().lower()
    if tipo not in TIPOS_ALERTA:
        return {"erro": f"tipo deve ser um destes: {', '.join(TIPOS_ALERTA)}."}
    if _cheio("alertas"):
        return {"erro": "Limite de alertas do lab atingido. Peça ao instrutor para reiniciar os dados."}
    novo = db.executar(
        "INSERT INTO alertas (contrato_id, data, tipo, descricao, autor, criado_em) VALUES (?,?,?,?,?,?)",
        (cid, data, tipo, descricao[:500], autor.strip()[:60], db.agora()),
    )
    _log("criar_alerta_data_critica", "escrita", f"Alerta de {tipo} em {data} para {cid}", autor)
    return {"ok": True, "alerta_id": novo, "mensagem": f"Alerta de {tipo} criado para {cid} em {data}."}


@mcp.tool(annotations=ESCRITA)
def registrar_interacao(oportunidade_id: str, resumo: str, proximos_passos: str, autor: str) -> dict:
    """Registra no CRM uma reunião, ligação ou e-mail com o cliente, com o resumo
    e os próximos passos combinados."""
    if (e := _autor_ok(autor)):
        return {"erro": e}
    oid = oportunidade_id.strip().upper()
    if not db.consultar("SELECT id FROM oportunidades WHERE id = ?", (oid,)):
        return {"erro": f"Oportunidade {oportunidade_id} não existe."}
    if _cheio("interacoes"):
        return {"erro": "Limite de interações do lab atingido."}
    novo = db.executar(
        "INSERT INTO interacoes (oportunidade_id, resumo, proximos_passos, autor, criado_em) VALUES (?,?,?,?,?)",
        (oid, resumo[:1000], proximos_passos[:500], autor.strip()[:60], db.agora()),
    )
    db.executar("UPDATE oportunidades SET atualizado_em = ? WHERE id = ?", (db.agora(), oid))
    _log("registrar_interacao", "escrita", f"Interação registrada em {oid}", autor)
    return {"ok": True, "interacao_id": novo}


@mcp.tool(annotations=ESCRITA)
def atualizar_estagio(oportunidade_id: str, novo_estagio: str, autor: str) -> dict:
    """Muda o estágio de uma oportunidade no funil (Prospecção, Qualificação,
    Proposta, Negociação, Fechado, Perdido). Aplica na hora, sem aprovação."""
    if (e := _autor_ok(autor)):
        return {"erro": e}
    oid = oportunidade_id.strip().upper()
    est = next((s for s in ESTAGIOS if s.lower() == novo_estagio.strip().lower()), None)
    if not est:
        return {"erro": f"Estágio inválido. Use um destes: {', '.join(ESTAGIOS)}."}
    if not db.consultar("SELECT id FROM oportunidades WHERE id = ?", (oid,)):
        return {"erro": f"Oportunidade {oportunidade_id} não existe."}
    db.executar("UPDATE oportunidades SET estagio = ?, atualizado_em = ? WHERE id = ?", (est, db.agora(), oid))
    _log("atualizar_estagio", "escrita", f"{oid} movida para {est}", autor)
    return {"ok": True, "mensagem": f"{oid} agora está em {est}."}


@mcp.tool(annotations=ESCRITA)
def solicitar_encaminhamento(oportunidade_id: str, time_destino: str, justificativa: str, autor: str) -> dict:
    """Pede o encaminhamento de uma oportunidade para um time especialista. NÃO
    aplica na hora: fica pendente até um humano aprovar no painel."""
    if (e := _autor_ok(autor)):
        return {"erro": e}
    oid = oportunidade_id.strip().upper()
    if not db.consultar("SELECT id FROM oportunidades WHERE id = ?", (oid,)):
        return {"erro": f"Oportunidade {oportunidade_id} não existe."}
    time = next((l for l in LINHAS if l.lower() == time_destino.strip().lower()), None)
    if not time:
        return {"erro": f"Time inválido. Use uma linha de serviço: {', '.join(LINHAS)}."}
    if _cheio("encaminhamentos"):
        return {"erro": "Limite de encaminhamentos do lab atingido."}
    novo = db.executar(
        "INSERT INTO encaminhamentos (oportunidade_id, time_destino, justificativa, status, autor, criado_em) VALUES (?,?,?,?,?,?)",
        (oid, time, justificativa[:500], "pendente", autor.strip()[:60], db.agora()),
    )
    _log("solicitar_encaminhamento", "pendente", f"{oid} para {time}, aguardando aprovação", autor)
    return {"ok": True, "encaminhamento_id": novo, "status": "pendente",
            "mensagem": "Pedido registrado. Ele só vale depois que um humano aprovar no painel."}


@mcp.tool(annotations=ESCRITA)
def rascunhar_carta(tipo: str, referencia_id: str, texto: str, autor: str) -> dict:
    """Salva o rascunho de uma carta ao cliente ou inquilino. tipo: cobranca ou
    reajuste. referencia_id: id do inquilino (IN-...) ou do contrato (C-...).
    A carta NÃO é enviada: fica em rascunho até um humano aprovar no painel."""
    if (e := _autor_ok(autor)):
        return {"erro": e}
    tipo = tipo.strip().lower().replace("ç", "c")
    if tipo not in ("cobranca", "reajuste"):
        return {"erro": "tipo deve ser cobranca ou reajuste."}
    ref = referencia_id.strip().upper()
    existe = db.consultar("SELECT id FROM inadimplencia WHERE id = ?", (ref,)) or db.consultar("SELECT id FROM contratos WHERE id = ?", (ref,))
    if not existe:
        return {"erro": f"Referência {referencia_id} não encontrada (use um id IN-... ou C-...)."}
    if _cheio("cartas"):
        return {"erro": "Limite de cartas do lab atingido."}
    novo = db.executar(
        "INSERT INTO cartas (tipo, referencia_id, texto, status, autor, criado_em) VALUES (?,?,?,?,?,?)",
        (tipo, ref, texto[:3000], "rascunho", autor.strip()[:60], db.agora()),
    )
    _log("rascunhar_carta", "pendente", f"Carta de {'cobrança' if tipo == 'cobranca' else 'reajuste'} para {ref} em rascunho", autor)
    return {"ok": True, "carta_id": novo, "status": "rascunho",
            "mensagem": "Rascunho salvo. A carta só é enviada depois da aprovação humana."}
