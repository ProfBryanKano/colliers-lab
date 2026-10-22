"""Servidor MCP do Colliers Hub (plataforma simulada).

São 10 ferramentas genéricas que servem para qualquer caso de uso: o agente
descobre os módulos com descrever_plataforma e depois lê, cria, altera e
exclui registros. O que precisa de aprovação humana é decidido pelo servidor,
pela política de cada módulo, e não pelo modelo.

Marcas MCP: leitura = read_only_hint; excluir = destructive_hint. Assistentes
como Claude e ChatGPT pedem confirmação antes de ferramentas sem read_only.
"""

from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from . import db, plataforma as p
from .schema import ENTIDADES

LEITURA = ToolAnnotations(read_only_hint=True, destructive_hint=False)
ESCRITA = ToolAnnotations(read_only_hint=False, destructive_hint=False)
DESTRUTIVA = ToolAnnotations(read_only_hint=False, destructive_hint=True)

origem = p.origem  # reexportado para o main.py
LISTA = ", ".join(ENTIDADES)

mcp = MCPServer(
    "Colliers Hub",
    instructions=(
        "Plataforma simulada da Colliers para laboratório, com dados FICTÍCIOS: CRM, carteira de imóveis e contratos, "
        "cobranças, chamados de manutenção, caixa de entrada de demandas, agenda, comunicações e base de conhecimento. "
        "Comece por descrever_plataforma para ver os módulos, os campos e a política de aprovação de cada um. "
        "Toda escrita pede autor (nome do grupo ou da pessoa). Algumas escritas vão para aprovação humana: "
        "nesse caso nada muda até alguém aprovar no painel."
    ),
)


def _ok(fn, *a, **k):
    try:
        return fn(*a, **k)
    except p.Erro as e:
        return {"erro": str(e)}


def _log_leitura(ferramenta: str, resumo: str, entidade: str = "", rid: str = "") -> None:
    db.evento(ferramenta, "leitura", "", resumo, p.origem.get(), entidade, rid)


# ---------------------------------------------------------------- leitura


@mcp.tool(annotations=LEITURA)
def descrever_plataforma() -> dict:
    """Descreve a plataforma: módulos (entidades), campos, opções válidas, referências entre
    módulos e a política de cada um (o que é livre, o que pede aprovação humana e o que é
    bloqueado). Use antes de qualquer escrita."""
    _log_leitura("descrever_plataforma", "Consultou os módulos e as políticas")
    return p.descrever()


LISTAR_DESC = (
    f"Lista registros de um módulo. Entidades: {LISTA}. "
    "filtros é um objeto campo → valor. Valor simples compara igualdade (sem diferenciar maiúsculas e acentos); "
    "lista significa 'um destes'; objeto usa operadores =, !=, >, >=, <, <=, contem, em. "
    'Exemplos: {"status": "Em aberto", "dias_atraso": {">": 30}} · {"vencimento": {"<=": "2027-03-31"}}. '
    "Campos calculados (dias_atraso, dias_para_vencimento, dias_ate) também podem ser filtrados. "
    "busca procura o texto em todos os campos. Cada referência vem com o nome legível (campo_id_nome). "
    "Resultados paginados: limite (até 200) e pagina."
)


@mcp.tool(annotations=LEITURA, description=LISTAR_DESC)
def listar(entidade: str, filtros: dict[str, Any] | None = None, busca: str | None = None,
           ordenar_por: str | None = None, decrescente: bool = False, limite: int = 50, pagina: int = 1) -> dict:
    r = _ok(p.listar, entidade, filtros, busca, ordenar_por, decrescente, limite, pagina)
    if "erro" not in r:
        extra = f" com filtros {filtros}" if filtros else ""
        _log_leitura("listar", f"{ENTIDADES[r['entidade']]['nome']}: {r['total']} registro(s){extra}"[:200], r["entidade"])
    return r


@mcp.tool(annotations=LEITURA)
def ler(entidade: str, id: str) -> dict:
    """Lê um registro completo pelo id (por exemplo CTR-001, EMP-003, DEM-005), com os nomes
    das referências, os registros ligados a ele em outros módulos (aditivos de um contrato,
    interações de uma oportunidade, cobranças de um locatário...) e pedidos de aprovação pendentes."""
    r = _ok(p.ler, entidade, id)
    if "erro" not in r:
        _log_leitura("ler", f"Leu {r['registro']['id']} ({p.titulo(r['entidade'], r['registro'])})", r["entidade"], r["registro"]["id"])
    return r


@mcp.tool(annotations=LEITURA)
def buscar(texto: str) -> dict:
    """Busca um texto em todos os módulos de uma vez (nome de empresa, pessoa, imóvel, assunto...).
    Devolve entidade, id e título de cada achado. Use ler para ver o registro."""
    r = _ok(p.buscar, texto)
    if isinstance(r, dict):
        return r
    _log_leitura("buscar", f"Buscou “{texto[:40]}”: {len(r)} resultado(s)")
    return {"resultados": r}


@mcp.tool(annotations=LEITURA)
def consultar_aprovacao(aprovacao_id: int) -> dict:
    """Mostra a situação de um pedido de aprovação humana: pendente, aprovada, rejeitada ou
    falhou, com o comentário de quem decidiu e o resultado."""
    r = _ok(p.consultar_aprovacao, aprovacao_id)
    if "erro" not in r:
        _log_leitura("consultar_aprovacao", f"Consultou o pedido #{aprovacao_id}: {r['status']}")
    return r


# ---------------------------------------------------------------- escrita


@mcp.tool(annotations=ESCRITA)
def criar(entidade: str, dados: dict[str, Any], autor: str, justificativa: str = "") -> dict:
    """Cria um registro num módulo. dados é um objeto com os campos (veja descrever_plataforma).
    Referências usam ids (empresa_id: "EMP-001"); datas em AAAA-MM-DD. Em comunicacoes, criar
    gera só um rascunho. Se a política exigir aprovação, devolve status pendente_aprovacao e
    nada é criado até um humano aprovar. justificativa ajuda quem vai aprovar."""
    r = _ok(p.criar, entidade, dados, autor, justificativa)
    if "erro" in r:
        db.evento("criar", "erro", autor, f"Recusado: {r['erro']}"[:200], p.origem.get(), "")
    return r


@mcp.tool(annotations=ESCRITA)
def atualizar(entidade: str, id: str, alteracoes: dict[str, Any], autor: str, justificativa: str = "") -> dict:
    """Altera campos de um registro. alteracoes traz só os campos que mudam, por exemplo
    {"status": "Encaminhada", "encaminhada_para_id": "COL-001"}. Campos sensíveis (como o
    responsável de uma oportunidade ou o valor de uma cobrança) e módulos protegidos vão para
    aprovação humana: nesse caso nada muda até alguém aprovar."""
    r = _ok(p.atualizar, entidade, id, alteracoes, autor, justificativa)
    if "erro" in r:
        db.evento("atualizar", "erro", autor, f"Recusado: {r['erro']}"[:200], p.origem.get(), "")
    return r


@mcp.tool(annotations=DESTRUTIVA)
def excluir(entidade: str, id: str, motivo: str, autor: str) -> dict:
    """Exclui um registro. Não funciona se outros registros dependem dele. Em vários módulos a
    exclusão exige aprovação humana e em alguns é bloqueada. Informe sempre o motivo."""
    r = _ok(p.excluir, entidade, id, motivo, autor)
    if "erro" in r:
        db.evento("excluir", "erro", autor, f"Recusado: {r['erro']}"[:200], p.origem.get(), "")
    return r


@mcp.tool(annotations=ESCRITA)
def enviar_comunicacao(comunicacao_id: str, autor: str, justificativa: str = "") -> dict:
    """Envia ao destinatário uma comunicação que está em rascunho (e-mail, carta ou notificação
    formal). É uma ação externa e irreversível: por padrão vai para aprovação humana e só sai
    depois que alguém aprovar no painel."""
    r = _ok(p.enviar_comunicacao, comunicacao_id, autor, justificativa)
    if "erro" in r:
        db.evento("enviar_comunicacao", "erro", autor, f"Recusado: {r['erro']}"[:200], p.origem.get(), "comunicacoes")
    return r
