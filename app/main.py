"""Colliers Hub: plataforma simulada + servidor MCP + painel + chat, num só serviço.

Rotas:
  /            painel da plataforma (módulos, feed ao vivo, aprovações, governança)
  /chat        chat do lab: um agente com as mesmas ferramentas MCP
  /mcp         endpoint MCP (Streamable HTTP); o caminho muda com MCP_PATH
"""

import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from . import db, plataforma as p, seed
from .schema import ENTIDADES, MODOS
from .tools import mcp

MCP_PATH = "/" + os.environ.get("MCP_PATH", "mcp").strip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or secrets.token_urlsafe(8)
APROVADOR_TOKEN = os.environ.get("APROVADOR_TOKEN") or ADMIN_TOKEN
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_URL = os.environ.get("OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions")
MODELOS = [m.strip() for m in os.environ.get(
    "MODELOS", "openai/gpt-5-mini,google/gemini-2.5-flash,anthropic/claude-haiku-4.5"
).split(",") if m.strip()]
CHAT_LIMITE = int(os.environ.get("CHAT_LIMITE_POR_10MIN", "40"))
STATIC = Path(__file__).resolve().parent.parent / "static"

mcp_app = mcp.streamable_http_app(
    streamable_http_path=MCP_PATH,
    stateless_http=True,
    # O lab é público por natureza (dados fictícios); a proteção de DNS rebinding
    # é para servidores locais e bloquearia o domínio do deploy.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    host="0.0.0.0",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed.semear()
    if "ADMIN_TOKEN" not in os.environ:
        print(f"[colliers-hub] ADMIN_TOKEN não definido. Token gerado para esta execução: {ADMIN_TOKEN}", flush=True)
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Colliers Hub", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def painel():
    return FileResponse(STATIC / "index.html")


@app.get("/chat")
def chat_page():
    return FileResponse(STATIC / "chat.html")


@app.get("/saude")
def saude():
    return {"ok": True}


# ---------------------------------------------------------------- API do painel


def _url_mcp(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", request.url.netloc))
    return f"{proto}://{host}{MCP_PATH}"


def _token(valor, *aceitos) -> None:
    if not valor or not any(secrets.compare_digest(str(valor), t) for t in aceitos):
        raise HTTPException(status_code=403, detail="Token inválido.")


def _erro(fn, *a, **k):
    try:
        return fn(*a, **k)
    except p.Erro as e:
        raise HTTPException(400, str(e))


@app.get("/api/estado")
def estado(request: Request):
    return {"versao": db.estado["versao"], "ultimo_evento": db.estado["ultimo_evento"], "hoje": db.hoje().isoformat(),
            "pendentes": len(db.aprovacoes("pendente")), "mcp_url": _url_mcp(request)}


@app.get("/api/schema")
def schema():
    ents = {}
    for nome, e in ENTIDADES.items():
        ents[nome] = {"nome": e["nome"], "grupo": e["grupo"], "descricao": e["descricao"], "prefixo": e["prefixo"],
                      "titulo": e["titulo"], "colunas": e["colunas"], "virtuais": e.get("virtuais", []),
                      "campos": e["campos"], "politica": db.politicas[nome], "sensiveis": db.sensiveis[nome],
                      "total": db.contar(nome)}
    return {"entidades": ents, "acoes": db.acoes, "modos": MODOS}


@app.get("/api/registros/{entidade}")
def registros(entidade: str, busca: str | None = None):
    return _erro(p.listar, entidade, None, busca, None, False, 200, 1)


@app.get("/api/registro/{entidade}/{rid}")
def registro(entidade: str, rid: str):
    r = _erro(p.ler, entidade, rid)
    r["historico"] = db.consultar("SELECT quando, operacao, autor, origem, aprovacao_id, antes, depois FROM auditoria "
                                  "WHERE entidade = ? AND registro_id = ? ORDER BY id DESC LIMIT 30", (r["entidade"], r["registro"]["id"]))
    return r


@app.get("/api/feed")
def feed(apos: int = 0):
    eventos = db.consultar("SELECT * FROM eventos WHERE id > ? ORDER BY id DESC LIMIT 80", (apos,))
    return {"ultimo": db.estado["ultimo_evento"], "eventos": eventos}


@app.get("/api/aprovacoes")
def lista_aprovacoes(status: str | None = None):
    lista = db.aprovacoes(status)
    for a in lista:
        if a["registro_id"]:
            reg = db.um(a["entidade"], a["registro_id"])
            a["titulo"] = p.titulo(a["entidade"], reg) if reg else ""
        else:
            a["titulo"] = p.titulo(a["entidade"], a["dados"] if isinstance(a["dados"], dict) else {})
        a["entidade_nome"] = ENTIDADES[a["entidade"]]["nome"]
        nomes = {}
        for bloco in (a["dados"], a["antes"]):
            if isinstance(bloco, dict):
                for campo, v in bloco.items():
                    d = ENTIDADES[a["entidade"]]["campos"].get(campo, {})
                    if d.get("tipo") == "ref" and v:
                        alvo = db.um(d["ref"], v)
                        nomes[v] = p.titulo(d["ref"], alvo) if alvo else v
        a["nomes"] = nomes
    return lista


@app.post("/api/aprovacoes/{aid}")
async def decidir(aid: int, request: Request):
    corpo = await request.json()
    _token(corpo.get("token"), APROVADOR_TOKEN, ADMIN_TOKEN)
    por = (corpo.get("por") or "Aprovador").strip()[:60]
    return _erro(p.decidir, aid, bool(corpo.get("aprovar")), por, (corpo.get("comentario") or "").strip()[:500])


@app.get("/api/chamadas")
def chamadas(apos: int = 0, limite: int = 60):
    linhas = db.consultar("SELECT * FROM chamadas WHERE id > ? ORDER BY id DESC LIMIT ?", (apos, min(limite, 200)))
    for c in linhas:
        for k in ("argumentos", "resultado"):
            try:
                c[k] = json.loads(c[k])
            except (TypeError, ValueError):
                pass
    ultimo = db.consultar("SELECT MAX(id) AS m FROM chamadas")[0]["m"] or 0
    return {"ultimo": ultimo, "chamadas": linhas}


@app.get("/api/mcp/ferramentas")
async def ferramentas_mcp():
    lista = await mcp.list_tools()
    return [t.model_dump(by_alias=True, exclude_none=True, mode="json") for t in lista]


@app.get("/api/auditoria")
def auditoria(limite: int = 150):
    return db.consultar("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (min(limite, 500),))


@app.post("/api/politicas")
async def politicas(request: Request):
    c = await request.json()
    _token(c.get("token"), ADMIN_TOKEN)
    if c.get("restaurar"):
        db.restaurar_politicas()
        msg = "Políticas restauradas ao padrão."
    elif c.get("acao"):
        if c["acao"] not in db.acoes or c.get("modo") not in MODOS:
            raise HTTPException(400, "Ação ou modo inválido.")
        db.acoes[c["acao"]] = c["modo"]
        msg = f"Ação {c['acao']}: {c['modo'].replace('aprovacao', 'com aprovação')}."
    elif "sensiveis" in c:
        ent = c.get("entidade")
        if ent not in ENTIDADES or not all(x in ENTIDADES[ent]["campos"] for x in c["sensiveis"]):
            raise HTTPException(400, "Entidade ou campos inválidos.")
        db.sensiveis[ent] = list(c["sensiveis"])
        msg = f"Campos sensíveis de {ent}: {', '.join(c['sensiveis']) or 'nenhum'}."
    else:
        ent, op, modo = c.get("entidade"), c.get("operacao"), c.get("modo")
        if ent not in ENTIDADES or op not in ("criar", "atualizar", "excluir") or modo not in MODOS:
            raise HTTPException(400, "Entidade, operação ou modo inválido.")
        db.politicas[ent][op] = modo
        nomes = {"livre": "livre", "aprovacao": "com aprovação", "bloqueado": "bloqueado"}
        msg = f"{ENTIDADES[ent]['nome']}: {op} agora é {nomes[modo]}."
    db.tocar()
    db.evento("governanca", "sistema", "Administrador", msg, "Painel")
    return {"ok": True, "mensagem": msg}


@app.post("/api/reiniciar")
async def reiniciar(request: Request):
    c = await request.json()
    _token(c.get("token"), ADMIN_TOKEN)
    seed.semear()
    return {"ok": True}


# ---------------------------------------------------------------- chat do lab

_janelas: dict[str, deque] = defaultdict(deque)


def _limite_ok(ip: str) -> bool:
    agora_s, fila = time.time(), _janelas[ip]
    while fila and agora_s - fila[0] > 600:
        fila.popleft()
    if len(fila) >= CHAT_LIMITE:
        return False
    fila.append(agora_s)
    return True


@app.get("/api/chat/config")
def chat_config():
    agentes = json.loads((STATIC / "agentes" / "agentes.json").read_text(encoding="utf-8"))
    return {"modelos": MODELOS, "habilitado": bool(OPENROUTER_KEY), "agentes": agentes}


@app.post("/api/chat")
async def chat(request: Request):
    if not OPENROUTER_KEY:
        return JSONResponse({"erro": "O chat do lab está desligado: falta configurar OPENROUTER_API_KEY no servidor."}, 503)
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    if not _limite_ok(ip):
        return JSONResponse({"erro": "Muitas mensagens em pouco tempo. Espere um minuto e tente de novo."}, 429)

    corpo = await request.json()
    modelo = corpo.get("modelo") if corpo.get("modelo") in MODELOS else MODELOS[0]
    nome = (corpo.get("nome") or "").strip()[:60] or "Participante"
    instrucoes = (corpo.get("instrucoes") or "").strip()[:8000]
    historico = [m for m in corpo.get("mensagens", [])[-20:]
                 if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]

    # Prompt mínimo de propósito: sem instruções, o agente só sabe a data, quem fala
    # e que tem ferramentas. É a "agência sem prompt específico".
    sistema = (f"Hoje é {db.hoje().isoformat()}. Você está conversando com {nome}; "
               "use esse nome no campo autor das ferramentas de escrita.")
    if instrucoes:
        sistema += "\n\nInstruções definidas pelo usuário:\n" + instrucoes

    ferramentas_mcp = await mcp.list_tools()
    tipo_por_nome = {t.name: ("leitura" if t.annotations and t.annotations.read_only_hint else "escrita") for t in ferramentas_mcp}
    ferramentas = [{"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema}}
                   for t in ferramentas_mcp]

    mensagens = [{"role": "system", "content": sistema}, *historico]
    passos = []
    tok = p.origem.set("Chat do lab")
    try:
        async with httpx.AsyncClient(timeout=120) as cliente:
            for _ in range(24):
                r = await cliente.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "X-Title": "Colliers Hub"},
                    json={"model": modelo, "messages": mensagens, "tools": ferramentas, "temperature": 0.2},
                )
                if r.status_code != 200:
                    return JSONResponse({"erro": f"O provedor do modelo respondeu {r.status_code}: {r.text[:300]}"}, 502)
                msg = r.json()["choices"][0]["message"]
                chamadas = msg.get("tool_calls") or []
                if not chamadas:
                    return {"resposta": msg.get("content") or "", "passos": passos, "modelo": modelo}
                mensagens.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": chamadas})
                for ch in chamadas:
                    nome_f = ch["function"]["name"]
                    try:
                        args = json.loads(ch["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    try:
                        resultado = await mcp.call_tool(nome_f, args)
                        texto = _texto_resultado(resultado)
                    except Exception as e:  # argumentos inválidos para o esquema da ferramenta
                        texto = json.dumps({"erro": f"Chamada inválida: {e}"}, ensure_ascii=False)
                    tipo = tipo_por_nome.get(nome_f, "escrita")
                    if '"pendente_aprovacao"' in texto:
                        tipo = "pendente"
                    passos.append({"ferramenta": nome_f, "tipo": tipo, "argumentos": args, "resultado": texto[:2000]})
                    mensagens.append({"role": "tool", "tool_call_id": ch["id"], "content": texto[:16000]})
        return {"resposta": "Parei depois de 24 rodadas de ferramentas. Tente um pedido mais específico.", "passos": passos, "modelo": modelo}
    except httpx.HTTPError as e:
        return JSONResponse({"erro": f"Falha de conexão com o provedor do modelo: {e}"}, 502)
    finally:
        p.origem.reset(tok)


def _texto_resultado(resultado) -> str:
    estruturado = getattr(resultado, "structured_content", None)
    if estruturado:
        return json.dumps(estruturado, ensure_ascii=False)
    partes = [getattr(c, "text", "") for c in getattr(resultado, "content", []) or []]
    return "\n".join(x for x in partes if x) or "{}"


# O MCP fica por último, para não capturar as rotas acima.
app.mount("/", mcp_app)
