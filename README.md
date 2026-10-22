# Colliers Hub · plataforma simulada para o lab de agentes

Uma plataforma fictícia da Colliers para os agentes da turma trabalharem em cima: **CRM, carteira de imóveis e contratos, cobrança, manutenção, caixa de entrada, agenda, comunicações e base de conhecimento**. Tudo é exposto por um servidor MCP genérico: o agente lê, cria, altera e exclui registros de qualquer módulo. As operações sensíveis param numa **fila de aprovação humana**, decidida no painel com um token.

Todos os dados são fictícios.

| Endereço | O que é |
| --- | --- |
| `/` | O Hub: módulos, registro completo, atividade ao vivo, chamadas MCP (pedido e resposta de cada uma), aprovações, políticas e auditoria |
| `/chat` | Chat do lab, com as mesmas ferramentas e dez agentes prontos |
| `/mcp` | Endpoint MCP (Streamable HTTP), sem autenticação |

## Material da aula

| Arquivo | O que é |
| --- | --- |
| [casos/CATALOGO_DE_CASOS.md](casos/CATALOGO_DE_CASOS.md) | Dez casos de uso com dor, especificação do agente, instruções prontas, chamadas MCP esperadas, testes e como montar em Claude, ChatGPT, Gemini e Copilot |
| [notebooks/agentes_de_processo.ipynb](notebooks/agentes_de_processo.ipynb) | O agente em código (as oito células do bloco 6) e agentes de processo trabalhando no Hub, com aprovação humana. Abre no Colab |
| `static/agentes/` | As instruções dos dez agentes, também disponíveis no chat do lab |

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

## Publicar no Render

O passo a passo completo, com solução de problemas, está no [TUTORIAL.md](TUTORIAL.md). Em resumo: suba o conteúdo desta pasta na raiz de um repositório do GitHub, crie um **Blueprint** no Render apontando para ele e preencha `ADMIN_TOKEN` e `OPENROUTER_API_KEY`. Depois rode `python verificar.py https://seu-servico.onrender.com SEU_TOKEN` para conferir tudo.

## Rodar no seu computador

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
OPENROUTER_API_KEY=sua-chave ADMIN_TOKEN=prof APROVADOR_TOKEN=aprova uvicorn app.main:app --reload
```

## Segurança

O endpoint MCP não tem autenticação, de propósito: qualquer pessoa com o endereço lê e escreve. Por isso só há dados fictícios. O campo `autor` é declarado por quem chama, não é login. As escritas têm limite de tamanho e de quantidade, e aprovações, políticas e reinício exigem token. Desligue o serviço depois da aula.
