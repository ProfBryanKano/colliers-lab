"""Colliers Lab: painel web + servidor MCP + chat do lab, num só serviço.

Rotas:
  /            painel ao vivo (o que os agentes leem e escrevem)
  /chat        chat do lab, para quem não puder conectar o próprio assistente
  /mcp         endpoint MCP (Streamable HTTP) — o caminho muda com MCP_PATH
"""

import json
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mcp.server.transport_security import TransportSecuritySettings

from . import db
from .tools import mcp, origem

MCP_PATH = "/" + os.environ.get("MCP_PATH", "mcp").strip("/")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN") or secrets.token_urlsafe(8)
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
    db.semear()
    if "ADMIN_TOKEN" not in os.environ:
        print(f"[colliers-lab] ADMIN_TOKEN não definido. Token gerado para esta execução: {ADMIN_TOKEN}", flush=True)
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Colliers Lab", lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---------------------------------------------------------------- páginas


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


@app.get("/api/feed")
def feed(apos: int = 0):
    eventos = db.consultar("SELECT * FROM eventos WHERE id > ? ORDER BY id DESC LIMIT 60", (apos,))
    return {"ultimo": db.estado["ultimo_evento"], "eventos": eventos}


@app.get("/api/dados")
def dados(request: Request, versao: int = 0):
    v = db.estado["versao_dados"]
    if versao == v:
        return {"versao": v, "inalterado": True}
    return {
        "versao": v,
        "mcp_url": _url_mcp(request),
        "contratos": db.consultar("SELECT id, cliente, imovel, cidade, tipo, area_m2, inicio, vencimento, valor_mensal, indice_reajuste, mes_reajuste, aviso_previo_dias FROM contratos ORDER BY vencimento"),
        "alertas": db.consultar("SELECT * FROM alertas ORDER BY data"),
        "oportunidades": db.consultar("SELECT * FROM oportunidades ORDER BY valor_estimado DESC"),
        "interacoes": db.consultar("SELECT * FROM interacoes ORDER BY id DESC LIMIT 200"),
        "inadimplencia": db.consultar("SELECT * FROM inadimplencia ORDER BY dias_atraso DESC"),
        "cartas": db.consultar("SELECT * FROM cartas ORDER BY id DESC LIMIT 200"),
        "encaminhamentos": db.consultar("SELECT * FROM encaminhamentos ORDER BY id DESC LIMIT 200"),
    }


def _checar_token(token: str | None) -> None:
    if not token or not secrets.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=403, detail="Token de instrutor inválido.")


@app.post("/api/decidir")
async def decidir(request: Request):
    corpo = await request.json()
    _checar_token(corpo.get("token"))
    tipo, item, aprovar = corpo.get("tipo"), int(corpo.get("id", 0)), bool(corpo.get("aprovar"))
    if tipo == "encaminhamento":
        linha = db.consultar("SELECT * FROM encaminhamentos WHERE id = ? AND status = 'pendente'", (item,))
        if not linha:
            raise HTTPException(404, "Encaminhamento não está mais pendente.")
        status = "aprovado" if aprovar else "rejeitado"
        db.executar("UPDATE encaminhamentos SET status = ?, decidido_em = ? WHERE id = ?", (status, db.agora(), item))
        if aprovar:
            db.executar("UPDATE oportunidades SET responsavel = ?, atualizado_em = ? WHERE id = ?",
                        (linha[0]["time_destino"], db.agora(), linha[0]["oportunidade_id"]))
        db.registrar_evento("aprovacao_humana", "aprovacao", "Instrutor",
                            f"Encaminhamento {item} de {linha[0]['oportunidade_id']} {status}", "Painel")
    elif tipo == "carta":
        linha = db.consultar("SELECT * FROM cartas WHERE id = ? AND status = 'rascunho'", (item,))
        if not linha:
            raise HTTPException(404, "Carta não está mais em rascunho.")
        status = "enviada" if aprovar else "descartada"
        db.executar("UPDATE cartas SET status = ?, decidido_em = ? WHERE id = ?", (status, db.agora(), item))
        db.registrar_evento("aprovacao_humana", "aprovacao", "Instrutor",
                            f"Carta {item} para {linha[0]['referencia_id']} {status}", "Painel")
    else:
        raise HTTPException(400, "tipo deve ser encaminhamento ou carta.")
    return {"ok": True, "status": status}


@app.post("/api/reiniciar")
async def reiniciar(request: Request):
    corpo = await request.json()
    _checar_token(corpo.get("token"))
    db.semear()
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
    return {"modelos": MODELOS, "habilitado": bool(OPENROUTER_KEY)}


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
    instrucoes = (corpo.get("instrucoes") or "").strip()[:4000]
    historico = [m for m in corpo.get("mensagens", [])[-20:]
                 if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)]

    # Prompt mínimo de propósito: sem instruções do aluno, o agente só sabe a data,
    # quem está falando e que tem ferramentas. É a "agência sem prompt específico".
    sistema = f"Hoje é {date.today().isoformat()}. Você está conversando com {nome}; use esse nome no campo autor das ferramentas de escrita."
    if instrucoes:
        sistema += "\n\nInstruções definidas pelo usuário:\n" + instrucoes

    ferramentas_mcp = await mcp.list_tools()
    tipo_por_nome = {t.name: ("leitura" if t.annotations and t.annotations.read_only_hint else "escrita") for t in ferramentas_mcp}
    ferramentas = [{"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema}}
                   for t in ferramentas_mcp]

    mensagens = [{"role": "system", "content": sistema}, *historico]
    passos = []
    token_origem = origem.set("Chat do lab")
    try:
        async with httpx.AsyncClient(timeout=90) as cliente:
            for _ in range(8):
                r = await cliente.post(
                    OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {OPENROUTER_KEY}", "X-Title": "Colliers Lab"},
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
                    resultado = await mcp.call_tool(nome_f, args)
                    texto = _texto_resultado(resultado)
                    passos.append({"ferramenta": nome_f, "tipo": tipo_por_nome.get(nome_f, "escrita"),
                                   "argumentos": args, "resultado": texto[:1500]})
                    mensagens.append({"role": "tool", "tool_call_id": ch["id"], "content": texto[:12000]})
        return {"resposta": "Parei depois de 8 rodadas de ferramentas. Tente um pedido mais específico.", "passos": passos, "modelo": modelo}
    except httpx.HTTPError as e:
        return JSONResponse({"erro": f"Falha de conexão com o provedor do modelo: {e}"}, 502)
    finally:
        origem.reset(token_origem)


def _texto_resultado(resultado) -> str:
    estruturado = getattr(resultado, "structured_content", None)
    if estruturado:
        return json.dumps(estruturado, ensure_ascii=False)
    partes = [getattr(c, "text", "") for c in getattr(resultado, "content", []) or []]
    return "\n".join(p for p in partes if p) or "{}"


# O MCP fica por último, para não capturar as rotas acima.
app.mount("/", mcp_app)
