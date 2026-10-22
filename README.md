# Colliers Lab

Ambiente de laboratório para o Módulo 2: uma operação imobiliária **fictícia** que os agentes leem e escrevem via MCP. Tudo roda num só serviço:

| Endereço | O que é |
| --- | --- |
| `/` | Painel ao vivo: feed de cada leitura e escrita, dados e fila de aprovações |
| `/chat` | Chat do lab: um agente com as mesmas ferramentas, para quem não puder conectar o próprio assistente |
| `/mcp` | Endpoint MCP (Streamable HTTP), sem autenticação |

## As ferramentas

As dores escolhidas vêm das contribuições da turma: datas críticas de contratos (04), registro no CRM e encaminhamento por linha de serviço (03) e régua de cobrança e cartas de reajuste (08).

| Ferramenta | Tipo | Degrau da escada de agência |
| --- | --- | --- |
| `listar_contratos`, `ler_contrato`, `listar_alertas` | leitura | 1. Ler |
| `buscar_oportunidades`, `ver_historico_oportunidade` | leitura | 1. Ler |
| `listar_inadimplencia`, `listar_pendencias` | leitura | 1. Ler |
| `rascunhar_carta` | escrita em rascunho | 2. Sugerir (a carta só sai com aprovação) |
| `solicitar_encaminhamento` | escrita pendente | 3. Escrever com aprovação |
| `criar_alerta_data_critica`, `registrar_interacao`, `atualizar_estagio` | escrita direta | 4. Agir sozinho |

As de leitura são marcadas como somente leitura no MCP; por isso assistentes como o ChatGPT pedem confirmação só nas de escrita. Toda escrita exige o campo `autor`, que aparece no painel.

## Deploy no Render (plano Starter)

1. Crie um repositório no GitHub e suba esta pasta.
2. No Render, clique em **New › Blueprint** e escolha o repositório. O `render.yaml` já configura um serviço web Docker no plano **Starter**, que não dorme.
3. Preencha as variáveis pedidas:
   - `OPENROUTER_API_KEY`: a chave usada pelo chat do lab. Crie uma chave só para isso no OpenRouter, com limite de crédito.
   - `ADMIN_TOKEN`: uma senha sua. Ela é pedida no painel para aprovar, rejeitar e reiniciar os dados.
4. Ao terminar o deploy, o endereço será algo como `https://colliers-lab.onrender.com`. O MCP fica em `https://colliers-lab.onrender.com/mcp`.

A cobrança é proporcional ao tempo ligado: suba na véspera e apague o serviço depois da aula.

Os dados ficam em disco temporário: se o serviço reiniciar ou for publicado de novo, eles voltam ao ponto de partida.

## Variáveis opcionais

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `MCP_PATH` | `mcp` | Mude para algo difícil de adivinhar (ex.: `mcp-turma-7x2`) se não quiser o endpoint num caminho óbvio |
| `MODELOS` | `openai/gpt-5-mini,google/gemini-2.5-flash,anthropic/claude-haiku-4.5` | Modelos do OpenRouter oferecidos no chat. Confira os ids em openrouter.ai/models e escolha modelos com suporte a tool calling |
| `CHAT_LIMITE_POR_10MIN` | `40` | Mensagens por IP a cada 10 minutos no chat do lab |

Se `ADMIN_TOKEN` não for definido, o servidor gera um token a cada inicialização e o escreve nos logs.

## Conectar os assistentes

- **ChatGPT:** ativar o modo desenvolvedor e criar um app ou conector com o endereço `/mcp`, sem autenticação. Em contas Business e Enterprise o administrador precisa liberar conectores personalizados antes.
- **Claude:** Configurações › Conectores › Adicionar conector personalizado, com o endereço `/mcp`.
- **Notebook da Parte 2:** o cliente MCP do SDK Python conecta direto no mesmo endereço.
- **Quem não puder conectar:** usa o `/chat`, que chama exatamente as mesmas ferramentas.

Confirme antes com a Colliers quais assistentes da turma permitem conectores personalizados.

## Rodar no seu computador

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
OPENROUTER_API_KEY=sua-chave ADMIN_TOKEN=prof uvicorn app.main:app --reload
```

Painel em http://localhost:8000, MCP em http://localhost:8000/mcp.

## Segurança

O endpoint MCP não tem autenticação, de propósito: qualquer pessoa com o endereço lê e escreve. Por isso **o lab só pode ter dados fictícios**. As escritas têm limite de tamanho e de quantidade, e as aprovações e o reinício exigem o token de instrutor. Desligue o serviço no Render depois da aula.
