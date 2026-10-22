"""Regras da plataforma: validação, consultas, escrita e governança.

Tudo o que o MCP, o chat e o painel fazem passa por aqui. As políticas
(livre, aprovacao, bloqueado) são aplicadas pelo servidor, não pelo modelo:
nenhum prompt consegue pular uma aprovação.
"""

import contextvars
import unicodedata
from datetime import date

from . import db
from .schema import ENTIDADES

origem = contextvars.ContextVar("origem", default="MCP")
LIMITE_REGISTROS = 2000  # proteção simples contra escritas em massa por entidade


class Erro(Exception):
    pass


def _sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t)) if unicodedata.category(c) != "Mn").lower().strip()


def entidade_ok(entidade: str) -> str:
    e = _sem_acento(entidade or "").replace(" ", "_")
    if e in ENTIDADES:
        return e
    for nome, d in ENTIDADES.items():
        if _sem_acento(d["nome"]) == _sem_acento(entidade or ""):
            return nome
    raise Erro(f"Entidade '{entidade}' não existe. Use uma destas: {', '.join(ENTIDADES)}.")


def titulo(entidade: str, reg: dict | None) -> str:
    if not reg:
        return ""
    return str(reg.get(ENTIDADES[entidade]["titulo"]) or reg.get("id"))[:80]


# ---------------------------------------------------------------- campos calculados


def com_virtuais(entidade: str, reg: dict) -> dict:
    r = dict(reg)
    h = db.hoje()
    try:
        if entidade == "contratos" and r.get("vencimento"):
            r["dias_para_vencimento"] = (date.fromisoformat(r["vencimento"]) - h).days
        elif entidade == "cobrancas":
            atraso = 0
            if r.get("status") in ("Em aberto", "Em negociação") and r.get("vencimento"):
                atraso = max(0, (h - date.fromisoformat(r["vencimento"])).days)
            r["dias_atraso"] = atraso
        elif entidade in ("alertas", "tarefas") and r.get("data"):
            r["dias_ate"] = (date.fromisoformat(r["data"]) - h).days
    except ValueError:
        pass
    return r


def com_nomes(entidade: str, reg: dict) -> dict:
    """Acrescenta o nome legível de cada referência: empresa_id -> empresa_id_nome."""
    r = dict(reg)
    for campo, d in ENTIDADES[entidade]["campos"].items():
        if d["tipo"] == "ref" and r.get(campo):
            alvo = db.um(d["ref"], r[campo])
            r[campo + "_nome"] = titulo(d["ref"], alvo) if alvo else "(não encontrado)"
    return r


def publico(entidade: str, reg: dict, nomes: bool = True) -> dict:
    r = com_virtuais(entidade, reg)
    if nomes:
        r = com_nomes(entidade, r)
    return {k: v for k, v in r.items() if not k.startswith("_")} | {
        "criado_por": reg.get("_criado_por"), "atualizado_em": reg.get("_atualizado_em"), "atualizado_por": reg.get("_atualizado_por")}


# ---------------------------------------------------------------- validação


def _valor(entidade: str, campo: str, d: dict, v):
    if v is None or v == "":
        return None
    t = d["tipo"]
    if t in ("texto", "texto_longo"):
        v = str(v).strip()
        lim = 8000 if t == "texto_longo" else 300
        return v[:lim]
    if t in ("numero", "moeda"):
        try:
            if isinstance(v, str):
                t2 = v.replace("R$", "").replace(" ", "")
                n = float(t2.replace(".", "").replace(",", ".")) if "," in t2 else float(t2)
            else:
                n = float(v)
        except ValueError:
            raise Erro(f"{campo}: '{v}' não é um número.")
        return int(n) if n.is_integer() else round(n, 2)
    if t == "data":
        try:
            return date.fromisoformat(str(v).strip()[:10]).isoformat()
        except ValueError:
            raise Erro(f"{campo}: data inválida '{v}'. Use AAAA-MM-DD.")
    if t == "booleano":
        if isinstance(v, bool):
            return v
        return _sem_acento(v) in ("true", "sim", "1", "s", "verdadeiro")
    if t == "opcao":
        for o in d["opcoes"]:
            if _sem_acento(o) == _sem_acento(v):
                return o
        raise Erro(f"{campo}: '{v}' não é válido. Opções: {', '.join(d['opcoes'])}.")
    if t == "ref":
        rid = str(v).strip().upper()
        if not db.um(d["ref"], rid):
            raise Erro(f"{campo}: {rid} não existe em {d['ref']}.")
        return rid
    return v


def validar(entidade: str, dados: dict, parcial: bool, atual: dict | None = None) -> dict:
    if not isinstance(dados, dict) or not dados:
        raise Erro("Envie os campos num objeto, por exemplo {\"status\": \"Concluído\"}.")
    campos = ENTIDADES[entidade]["campos"]
    limpo, desconhecidos = {}, []
    for k, v in dados.items():
        if k in ("id",) or k.startswith("_") or k.endswith("_nome") or k in ("criado_por", "atualizado_em", "atualizado_por"):
            continue
        if k not in campos:
            desconhecidos.append(k)
            continue
        if campos[k].get("sistema"):
            raise Erro(f"O campo {k} é controlado pela plataforma e não pode ser alterado diretamente.")
        limpo[k] = _valor(entidade, k, campos[k], v)
    if desconhecidos:
        raise Erro(f"Campos inexistentes em {entidade}: {', '.join(desconhecidos)}. Campos válidos: {', '.join(campos)}.")
    final = {**(atual or {}), **limpo}
    faltando = [c for c, d in campos.items() if d.get("obrigatorio") and final.get(c) in (None, "")]
    if faltando:
        raise Erro(f"Campos obrigatórios faltando: {', '.join(faltando)}.")
    return limpo


# ---------------------------------------------------------------- leitura


def _comparar(valor, cond) -> bool:
    if isinstance(cond, dict):
        for op, alvo in cond.items():
            op = op.strip().lower()
            if valor is None:
                return op in ("=", "==", "eq") and alvo is None
            try:
                a, b = (float(valor), float(alvo)) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else (str(valor), str(alvo))
            except (TypeError, ValueError):
                a, b = str(valor), str(alvo)
            ok = {
                "=": a == b, "==": a == b, "eq": a == b, "!=": a != b, "ne": a != b,
                ">": a > b, "gt": a > b, ">=": a >= b, "gte": a >= b, "<": a < b, "lt": a < b, "<=": a <= b, "lte": a <= b,
                "contem": _sem_acento(b) in _sem_acento(a), "contém": _sem_acento(b) in _sem_acento(a),
                "em": _sem_acento(a) in [_sem_acento(x) for x in (alvo if isinstance(alvo, list) else [alvo])],
                "in": _sem_acento(a) in [_sem_acento(x) for x in (alvo if isinstance(alvo, list) else [alvo])],
            }.get(op)
            if ok is None:
                raise Erro(f"Operador '{op}' não suportado. Use =, !=, >, >=, <, <=, contem, em.")
            if not ok:
                return False
        return True
    if isinstance(cond, list):
        return _sem_acento(valor) in [_sem_acento(x) for x in cond]
    if isinstance(cond, bool) or isinstance(valor, bool):
        return bool(valor) == (cond if isinstance(cond, bool) else _sem_acento(cond) in ("true", "sim", "1"))
    return _sem_acento(valor if valor is not None else "") == _sem_acento(cond)


def listar(entidade: str, filtros: dict | None = None, busca: str | None = None, ordenar_por: str | None = None,
           decrescente: bool = False, limite: int = 50, pagina: int = 1) -> dict:
    entidade = entidade_ok(entidade)
    regs = [com_virtuais(entidade, r) for r in db.todos(entidade)]
    if filtros:
        if not isinstance(filtros, dict):
            raise Erro("filtros deve ser um objeto, por exemplo {\"status\": \"Em aberto\", \"dias_atraso\": {\">\": 60}}.")
        validos = set(ENTIDADES[entidade]["campos"]) | set(ENTIDADES[entidade].get("virtuais", [])) | {"id"}
        for campo in filtros:
            if campo not in validos:
                raise Erro(f"Não dá para filtrar por '{campo}'. Campos: {', '.join(sorted(validos))}.")
        regs = [r for r in regs if all(_comparar(r.get(c), v) for c, v in filtros.items())]
    if busca:
        b = _sem_acento(busca)
        regs = [r for r in regs if b in _sem_acento(" ".join(str(v) for k, v in r.items() if not k.startswith("_")))]
    if ordenar_por:
        regs.sort(key=lambda r: (r.get(ordenar_por) is None, r.get(ordenar_por) if r.get(ordenar_por) is not None else ""), reverse=decrescente)
    total = len(regs)
    limite = max(1, min(int(limite or 50), 200))
    pagina = max(1, int(pagina or 1))
    fatia = regs[(pagina - 1) * limite: pagina * limite]
    return {"entidade": entidade, "total": total, "pagina": pagina, "por_pagina": limite,
            "registros": [publico(entidade, r) for r in fatia]}


def relacionados(entidade: str, rid: str, limite: int = 25) -> dict:
    saida = {}
    for nome, ent in ENTIDADES.items():
        refs = [c for c, d in ent["campos"].items() if d["tipo"] == "ref" and d["ref"] == entidade]
        texto_rel = "relacionado_a" in ent["campos"]
        if not refs and not texto_rel:
            continue
        achados = [r for r in db.todos(nome) if any(r.get(c) == rid for c in refs) or (texto_rel and r.get("relacionado_a") == rid)]
        if achados:
            saida[nome] = [{"id": r["id"], "titulo": titulo(nome, r)} for r in achados[:limite]]
    return saida


def ler(entidade: str, rid: str) -> dict:
    entidade = entidade_ok(entidade)
    rid = (rid or "").strip().upper()
    r = db.um(entidade, rid)
    if not r:
        raise Erro(f"{rid} não existe em {entidade}. Use listar para ver os ids.")
    pend = [a["id"] for a in db.aprovacoes("pendente") if a["entidade"] == entidade and a["registro_id"] == rid]
    return {"entidade": entidade, "registro": publico(entidade, r), "relacionados": relacionados(entidade, rid),
            "aprovacoes_pendentes": pend}


def buscar(texto: str, limite: int = 30) -> list[dict]:
    b = _sem_acento(texto or "")
    if len(b) < 2:
        raise Erro("Escreva pelo menos 2 letras para buscar.")
    achados = []
    for nome in ENTIDADES:
        for r in db.todos(nome):
            if b in _sem_acento(" ".join(str(v) for k, v in r.items() if not k.startswith("_"))) or b in _sem_acento(r["id"]):
                achados.append({"entidade": nome, "id": r["id"], "titulo": titulo(nome, r)})
                if len(achados) >= limite:
                    return achados
    return achados


def descrever() -> dict:
    ents = {}
    for nome, e in ENTIDADES.items():
        campos = {}
        for c, d in e["campos"].items():
            info = {"tipo": d["tipo"]}
            if d.get("obrigatorio"):
                info["obrigatorio"] = True
            if d.get("opcoes"):
                info["opcoes"] = d["opcoes"]
            if d.get("ref"):
                info["referencia"] = d["ref"]
            if d.get("sistema"):
                info["somente_plataforma"] = True
            if c in db.sensiveis.get(nome, []):
                info["sensivel"] = True
            campos[c] = info
        ents[nome] = {"nome": e["nome"], "grupo": e["grupo"], "descricao": e["descricao"], "prefixo_id": e["prefixo"],
                      "campos": campos, "campos_calculados": e.get("virtuais", []),
                      "politica": dict(db.politicas[nome]), "registros": db.contar(nome)}
    return {
        "plataforma": "Colliers Hub (simulação para o laboratório; dados fictícios)",
        "hoje": db.hoje().isoformat(),
        "como_funciona": (
            "Toda escrita pede autor (nome do grupo ou da pessoa). A política de cada entidade diz se criar, atualizar e excluir "
            "são livres, precisam de aprovação humana ou estão bloqueadas. Campos sensíveis pedem aprovação mesmo quando atualizar é livre. "
            "Quando algo vai para aprovação, nada muda até um humano aprovar no painel: acompanhe com consultar_aprovacao."),
        "politica_de_acoes": dict(db.acoes),
        "entidades": ents,
    }


# ---------------------------------------------------------------- escrita


def _autor(autor: str) -> str:
    a = " ".join((autor or "").split())[:60]
    if not a:
        raise Erro("Informe o campo autor (nome do grupo ou da pessoa).")
    return a


def _resumo_mudanca(entidade: str, antes: dict, alteracoes: dict) -> str:
    def f(x):
        return "—" if x in (None, "") else str(x)[:60]
    partes = [f"{c}: {f(antes.get(c))} → {f(v)}" for c, v in alteracoes.items() if antes.get(c) != v]
    return "; ".join(partes)[:220] or "sem mudanças"


def _aplicar(op: str, entidade: str, rid: str | None, dados: dict | None, autor: str, aprovacao_id=None) -> dict:
    """Executa de fato a operação (já autorizada). Usado direto e na aprovação."""
    o = origem.get()
    if op == "criar":
        if db.contar(entidade) >= LIMITE_REGISTROS:
            raise Erro("Limite de registros do lab atingido para esta entidade.")
        limpo = validar(entidade, dados, parcial=False)
        if entidade == "comunicacoes":
            limpo["status"] = "Rascunho"
        novo = db.inserir(entidade, limpo, autor)
        db.auditar("criar", entidade, novo, None, limpo, autor, o, aprovacao_id)
        return {"id": novo, "registro": publico(entidade, db.um(entidade, novo))}
    atual = db.um(entidade, rid)
    if not atual:
        raise Erro(f"{rid} não existe mais em {entidade}.")
    if op == "atualizar":
        base = {k: v for k, v in atual.items() if k != "id" and not k.startswith("_")}
        limpo = validar(entidade, dados, parcial=True, atual=base)
        novo = {**base, **limpo}
        db.gravar(entidade, rid, novo, autor)
        db.auditar("atualizar", entidade, rid, base, novo, autor, o, aprovacao_id)
        return {"id": rid, "registro": publico(entidade, db.um(entidade, rid))}
    if op == "excluir":
        rel = relacionados(entidade, rid)
        if rel:
            lista = ", ".join(f"{len(v)} em {k}" for k, v in rel.items())
            raise Erro(f"{rid} não pode ser excluído porque há registros ligados a ele ({lista}). Trate esses registros antes.")
        base = {k: v for k, v in atual.items() if not k.startswith("_")}
        db.apagar(entidade, rid)
        db.auditar("excluir", entidade, rid, base, None, autor, o, aprovacao_id)
        return {"id": rid, "excluido": True}
    if op == "enviar":
        if atual.get("status") not in ("Rascunho", "Aguardando aprovação"):
            raise Erro(f"A comunicação {rid} está '{atual.get('status')}'. Só rascunhos podem ser enviados.")
        base = {k: v for k, v in atual.items() if k != "id" and not k.startswith("_")}
        novo = {**base, "status": "Enviada", "enviada_em": db.hoje().isoformat()}
        db.gravar(entidade, rid, novo, autor)
        db.auditar("enviar", entidade, rid, base, novo, autor, o, aprovacao_id)
        return {"id": rid, "status": "Enviada", "para": atual.get("para")}
    raise Erro(f"Operação desconhecida: {op}.")


def _pedir_aprovacao(op: str, entidade: str, rid, dados, antes, motivo: str, autor: str, justificativa: str, resumo: str) -> dict:
    aid = db.nova_aprovacao(op, entidade, rid, dados, antes, motivo, autor, justificativa, origem.get())
    db.evento(f"{op}", "pendente", autor, f"Pedido #{aid}: {resumo} ({motivo})", origem.get(), entidade, rid or "")
    return {"status": "pendente_aprovacao", "aprovacao_id": aid, "motivo": motivo,
            "mensagem": f"Nada foi alterado ainda. O pedido #{aid} está na fila de aprovação humana. "
                        f"Avise o usuário e acompanhe com consultar_aprovacao({aid})."}


def _bloqueado(op: str, entidade: str, autor: str, resumo: str) -> dict:
    db.evento(op, "bloqueado", autor, f"Bloqueado: {resumo}", origem.get(), entidade)
    raise Erro(f"A política da plataforma não permite {op} em {entidade} por agentes. Peça a um humano da área.")


def criar(entidade: str, dados: dict, autor: str, justificativa: str = "") -> dict:
    entidade, autor = entidade_ok(entidade), _autor(autor)
    resumo = f"criar em {ENTIDADES[entidade]['nome']}"
    modo = db.politicas[entidade]["criar"]
    if modo == "bloqueado":
        _bloqueado("criar", entidade, autor, resumo)
    limpo = validar(entidade, dados, parcial=False)
    resumo = f"criar {ENTIDADES[entidade]['nome'].lower()}: {titulo(entidade, limpo)}"
    if modo == "aprovacao":
        return _pedir_aprovacao("criar", entidade, None, limpo, None, "criar exige aprovação nesta entidade", autor, justificativa, resumo)
    r = _aplicar("criar", entidade, None, limpo, autor)
    db.evento("criar", "escrita", autor, f"{r['id']} criado: {titulo(entidade, limpo)}", origem.get(), entidade, r["id"])
    return {"status": "concluido", **r}


def atualizar(entidade: str, rid: str, alteracoes: dict, autor: str, justificativa: str = "") -> dict:
    entidade, autor = entidade_ok(entidade), _autor(autor)
    rid = (rid or "").strip().upper()
    atual = db.um(entidade, rid)
    if not atual:
        raise Erro(f"{rid} não existe em {entidade}.")
    modo = db.politicas[entidade]["atualizar"]
    if modo == "bloqueado":
        _bloqueado("atualizar", entidade, autor, f"atualizar {rid}")
    base = {k: v for k, v in atual.items() if k != "id" and not k.startswith("_")}
    limpo = validar(entidade, alteracoes, parcial=True, atual=base)
    mudou = {k: v for k, v in limpo.items() if base.get(k) != v}
    if not mudou:
        return {"status": "sem_mudancas", "mensagem": "Os valores enviados já são os atuais. Nada mudou."}
    resumo = f"{rid}: {_resumo_mudanca(entidade, base, mudou)}"
    sens = [c for c in mudou if c in db.sensiveis.get(entidade, [])]
    if modo == "aprovacao" or sens:
        motivo = "atualizar exige aprovação nesta entidade" if modo == "aprovacao" else f"campo sensível: {', '.join(sens)}"
        antes = {k: base.get(k) for k in mudou}
        return _pedir_aprovacao("atualizar", entidade, rid, mudou, antes, motivo, autor, justificativa, resumo)
    r = _aplicar("atualizar", entidade, rid, mudou, autor)
    db.evento("atualizar", "escrita", autor, resumo, origem.get(), entidade, rid)
    return {"status": "concluido", **r}


def excluir(entidade: str, rid: str, motivo: str, autor: str) -> dict:
    entidade, autor = entidade_ok(entidade), _autor(autor)
    rid = (rid or "").strip().upper()
    atual = db.um(entidade, rid)
    if not atual:
        raise Erro(f"{rid} não existe em {entidade}.")
    if not (motivo or "").strip():
        raise Erro("Informe o motivo da exclusão.")
    modo = db.politicas[entidade]["excluir"]
    resumo = f"excluir {rid} ({titulo(entidade, atual)})"
    if modo == "bloqueado":
        _bloqueado("excluir", entidade, autor, resumo)
    rel = relacionados(entidade, rid)
    if rel:
        lista = ", ".join(f"{len(v)} em {k}" for k, v in rel.items())
        raise Erro(f"{rid} não pode ser excluído porque há registros ligados a ele ({lista}).")
    if modo == "aprovacao":
        antes = {k: v for k, v in atual.items() if not k.startswith("_")}
        return _pedir_aprovacao("excluir", entidade, rid, {"motivo": motivo}, antes, "excluir exige aprovação nesta entidade", autor, motivo, resumo)
    r = _aplicar("excluir", entidade, rid, None, autor)
    db.evento("excluir", "escrita", autor, f"{resumo}: {motivo[:80]}", origem.get(), entidade, rid)
    return {"status": "concluido", **r}


def enviar_comunicacao(rid: str, autor: str, justificativa: str = "") -> dict:
    autor = _autor(autor)
    rid = (rid or "").strip().upper()
    c = db.um("comunicacoes", rid)
    if not c:
        raise Erro(f"Comunicação {rid} não existe. Crie o rascunho em comunicacoes primeiro.")
    if c.get("status") != "Rascunho":
        raise Erro(f"A comunicação {rid} está '{c.get('status')}'. Só rascunhos podem ser enviados.")
    modo = db.acoes.get("enviar_comunicacao", "aprovacao")
    resumo = f"enviar {rid} para {c.get('para')}: {c.get('assunto')}"
    if modo == "bloqueado":
        _bloqueado("enviar_comunicacao", "comunicacoes", autor, resumo)
    if modo == "aprovacao":
        base = {k: v for k, v in c.items() if k != "id" and not k.startswith("_")}
        db.gravar("comunicacoes", rid, {**base, "status": "Aguardando aprovação"}, autor)
        return _pedir_aprovacao("enviar", "comunicacoes", rid, {"status": "Enviada"}, {"status": "Rascunho"},
                                "comunicação externa exige aprovação", autor, justificativa, resumo)
    r = _aplicar("enviar", "comunicacoes", rid, None, autor)
    db.evento("enviar_comunicacao", "escrita", autor, resumo, origem.get(), "comunicacoes", rid)
    return {"status": "concluido", **r}


def consultar_aprovacao(aid: int) -> dict:
    a = db.aprovacao(int(aid))
    if not a:
        raise Erro(f"Pedido de aprovação #{aid} não existe.")
    return {k: a[k] for k in ("id", "operacao", "entidade", "registro_id", "status", "motivo_aprovacao", "autor",
                              "criado_em", "decidido_em", "decidido_por", "comentario", "resultado", "dados")}


def decidir(aid: int, aprovar: bool, por: str, comentario: str = "") -> dict:
    a = db.aprovacao(int(aid))
    if not a or a["status"] != "pendente":
        raise Erro("Esse pedido não está mais pendente.")
    rotulo = f"#{aid} ({a['operacao']} {a['entidade']}{' ' + a['registro_id'] if a['registro_id'] else ''})"
    tok = origem.set("Painel de aprovação")
    try:
        if not aprovar:
            if a["operacao"] == "enviar":
                c = db.um("comunicacoes", a["registro_id"])
                if c:
                    base = {k: v for k, v in c.items() if k != "id" and not k.startswith("_")}
                    db.gravar("comunicacoes", a["registro_id"], {**base, "status": "Rascunho"}, por)
            db.fechar_aprovacao(aid, "rejeitada", por, comentario, None)
            db.evento("decisao_humana", "aprovacao", por, f"Rejeitou {rotulo}" + (f": {comentario}" if comentario else ""), "Painel", a["entidade"], a["registro_id"] or "")
            return {"status": "rejeitada"}
        try:
            r = _aplicar(a["operacao"], a["entidade"], a["registro_id"], a["dados"] if a["operacao"] != "excluir" else None,
                         a["autor"], aprovacao_id=aid)
        except Erro as e:
            db.fechar_aprovacao(aid, "falhou", por, f"{comentario} | {e}".strip(" |"), None)
            db.evento("decisao_humana", "erro", por, f"Aprovou {rotulo}, mas falhou: {e}", "Painel", a["entidade"], a["registro_id"] or "")
            return {"status": "falhou", "erro": str(e)}
        db.fechar_aprovacao(aid, "aprovada", por, comentario, r)
        db.evento("decisao_humana", "aprovacao", por, f"Aprovou {rotulo}" + (f": {comentario}" if comentario else ""), "Painel",
                  a["entidade"], r.get("id") or a["registro_id"] or "")
        return {"status": "aprovada", "resultado": r}
    finally:
        origem.reset(tok)
