# Colliers Hub · plataforma simulada para o lab de agentes

Uma plataforma fictícia da Colliers para os agentes da turma trabalharem em cima: **CRM, carteira de imóveis e contratos, cobrança, manutenção, caixa de entrada, agenda, comunicações e base de conhecimento**. Tudo é exposto por um servidor MCP genérico: o agente lê, cria, altera e exclui registros de qualquer módulo. As operações sensíveis param numa **fila de aprovação humana**, decidida no painel com um token.

Todos os dados são fictícios.

| Endereço | O que é |
| --- | --- |
| `/` | O Hub: módulos, registro completo, feed ao vivo, aprovações, políticas e auditoria |
| `/chat` | Chat do lab, com as mesmas ferramentas e seis modelos de agente prontos |
| `/mcp` | Endpoint MCP (Streamable HTTP), sem autenticação |

## Módulos (15)

| Grupo | Módulos |
| --- | --- |
| CRM | Empresas, Contatos, Oportunidades, Interações |
| Carteira | Imóveis, Contratos, Aditivos, Datas críticas |
| Operação | Cobranças, Chamados, Caixa de entrada (demandas), Agenda e tarefas, Comunicações |
| Referência | Base de conhecimento (políticas e tabelas de decisão), Colaboradores |

Os módulos estão definidos em `app/schema.py`. Para criar um módulo novo, acrescente uma entrada lá: MCP, validação, painel e auditoria passam a funcionar sozinhos. Os dados iniciais ficam em `app/seed.py`.

## As 9 ferramentas MCP

| Ferramenta | Tipo | Para quê |
| --- | --- | --- |
| `descrever_plataforma` | leitura | Módulos, campos, opções válidas, referências e a política de cada módulo |
| `listar` | leitura | Registros de um módulo, com filtros (`=`, `>`, `<=`, `contem`, `em`...), busca, ordenação e paginação |
| `ler` | leitura | Um registro completo, com os nomes das referências e os registros ligados a ele |
| `buscar` | leitura | Um texto em todos os módulos |
| `consultar_aprovacao` | leitura | Situação de um pedido de aprovação e o comentário de quem decidiu |
| `criar` | escrita | Cria um registro |
| `atualizar` | escrita | Altera campos de um registro |
| `excluir` | escrita, destrutiva | Exclui um registro (recusado se outros registros dependem dele) |
| `enviar_comunicacao` | escrita | Envia um rascunho de e-mail ou carta para fora |

## Governança: livre, com aprovação ou bloqueado

Cada módulo tem uma política para criar, alterar e excluir. Além disso, alguns **campos sensíveis** pedem aprovação mesmo quando alterar é livre (por exemplo o responsável de uma oportunidade e o valor ou status de uma cobrança). Tudo isso é aplicado pelo servidor, então nenhum prompt consegue pular uma aprovação. Na aba **Políticas** do painel dá para mudar qualquer regra ao vivo, com o token de administrador.

Quando uma escrita precisa de aprovação, o agente recebe `pendente_aprovacao` com o número do pedido e nada muda. No painel, a aba **Aprovações** mostra o que vai mudar (antes e depois, o registro a excluir ou o e-mail completo). Aprovar executa exatamente o que foi pedido; rejeitar não muda nada, e o comentário volta para o agente em `consultar_aprovacao`. A aba **Auditoria** registra toda escrita que aconteceu, com autor, origem e número da aprovação.

## Deploy no Render

1. Suba esta pasta num repositório do GitHub.
2. No Render: **New › Blueprint** e escolha o repositório. O `render.yaml` cria um serviço Docker no plano Starter, que não dorme.
3. Variáveis:
   - `OPENROUTER_API_KEY`: chave só para o chat do lab, com limite de crédito.
   - `ADMIN_TOKEN`: token do administrador (políticas e reinício; também aprova).
   - `APROVADOR_TOKEN`: token de quem só aprova. Se ficar vazio, vale o `ADMIN_TOKEN`.
4. O MCP fica em `https://<seu-servico>.onrender.com/mcp`.

As datas são calculadas a partir do dia em que o serviço sobe (horário de Brasília). Se publicar na véspera, use **Conectar › Reiniciar dados** na manhã da aula. Os dados ficam em disco temporário e voltam ao início a cada reinício do serviço. As políticas voltam ao padrão quando o serviço reinicia.

Variáveis opcionais: `MCP_PATH` (padrão `mcp`), `MODELOS` (modelos do OpenRouter no chat), `CHAT_LIMITE_POR_10MIN` (padrão 40).

## Rodar no seu computador

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
OPENROUTER_API_KEY=sua-chave ADMIN_TOKEN=prof APROVADOR_TOKEN=aprova uvicorn app.main:app --reload
```

## Segurança

O endpoint MCP não tem autenticação, de propósito: qualquer pessoa com o endereço lê e escreve. Por isso só há dados fictícios. O campo `autor` é declarado por quem chama, não é login. As escritas têm limite de tamanho e de quantidade, e aprovações, políticas e reinício exigem token. Desligue o serviço depois da aula.
