"""Confere se o Colliers Hub publicado está funcionando.

Uso:
    python verificar.py https://seu-servico.onrender.com
    python verificar.py https://seu-servico.onrender.com SEU_ADMIN_TOKEN

Só usa a biblioteca padrão do Python: não precisa instalar nada. Não altera dados.
"""

import json
import sys
import urllib.error
import urllib.request

OK, FALHA = "  ok   ", "  FALHA"
problemas = 0


def pedir(url, corpo=None, cab=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, headers={"Content-Type": "application/json", **(cab or {})})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def checar(nome, condicao, detalhe=""):
    global problemas
    print(f"{OK if condicao else FALHA}  {nome}" + (f"  ({detalhe})" if detalhe else ""))
    if not condicao:
        problemas += 1


def mcp(base, metodo, params, n):
    cab = {"Accept": "application/json, text/event-stream"}
    st, txt = pedir(base + "/mcp", {"jsonrpc": "2.0", "id": n, "method": metodo, "params": params}, cab)
    if st != 200:
        return st, None
    for linha in txt.splitlines():  # a resposta pode vir como evento SSE
        if linha.startswith("data:"):
            txt = linha[5:].strip()
    try:
        return st, json.loads(txt)
    except ValueError:
        return st, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    base = sys.argv[1].rstrip("/")
    token = sys.argv[2] if len(sys.argv) > 2 else None
    print(f"\nVerificando {base}\n(o primeiro acesso pode demorar alguns segundos)\n")

    st, txt = pedir(base + "/saude")
    checar("Serviço no ar (/saude)", st == 200, f"HTTP {st}")
    if st != 200:
        print("\nO serviço não respondeu. No Render, veja se o deploy terminou e abra a aba Logs.")
        sys.exit(1)

    st, txt = pedir(base + "/")
    checar("Painel do Hub (/)", st == 200 and "Colliers" in txt, f"HTTP {st}")
    st, txt = pedir(base + "/chat")
    checar("Chat do lab (/chat)", st == 200, f"HTTP {st}")
    st, txt = pedir(base + "/static/estilo.css")
    checar("Arquivos de estilo (/static)", st == 200, f"HTTP {st}")

    st, txt = pedir(base + "/api/schema")
    try:
        ents = json.loads(txt)["entidades"]
        checar("Módulos carregados", len(ents) >= 15, f"{len(ents)} módulos")
        vazios = [k for k, v in ents.items() if v["total"] == 0]
        checar("Dados iniciais", not vazios, "vazios: " + ", ".join(vazios) if vazios else "todos com registros")
    except (ValueError, KeyError):
        checar("Módulos carregados", False, f"HTTP {st}")

    st, txt = pedir(base + "/api/chat/config")
    try:
        cfg = json.loads(txt)
        checar("Chat com chave do OpenRouter", cfg["habilitado"], "configure OPENROUTER_API_KEY" if not cfg["habilitado"] else f"{len(cfg['modelos'])} modelos")
    except (ValueError, KeyError):
        checar("Configuração do chat", False, f"HTTP {st}")

    st, r = mcp(base, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "verificar", "version": "1"}}, 1)
    checar("MCP responde (initialize)", bool(r and "result" in r), f"HTTP {st}")
    st, r = mcp(base, "tools/list", {}, 2)
    nomes = [t["name"] for t in (r or {}).get("result", {}).get("tools", [])]
    checar("MCP lista as ferramentas", len(nomes) == 9, ", ".join(nomes) or f"HTTP {st}")
    st, r = mcp(base, "tools/call", {"name": "listar", "arguments": {"entidade": "contratos", "limite": 1}}, 3)
    res = (r or {}).get("result", {})
    texto = json.dumps(res, ensure_ascii=False)
    checar("MCP executa uma leitura", bool(res) and not res.get("isError") and "CTR-001" in texto, "listar contratos")

    st, txt = pedir(base + "/api/chamadas?limite=1")
    checar("Registro das chamadas MCP", st == 200 and '"ferramenta": "listar"' in txt.replace('":"', '": "'), "página Chamadas MCP")

    if token:
        st, txt = pedir(base + "/api/aprovacoes/0", {"token": token, "aprovar": False})
        checar("ADMIN_TOKEN aceito", st != 403, "token incorreto" if st == 403 else "token válido")

    print(f"\nEndereço para conectar os assistentes: {base}/mcp")
    print("Tudo certo." if not problemas else f"{problemas} item(ns) com problema. Veja o TUTORIAL.md, seção Se algo der errado.")
    sys.exit(1 if problemas else 0)


if __name__ == "__main__":
    main()
