# Tutorial: publicar o Colliers Hub no Render

São quatro passos: subir no GitHub, criar o serviço no Render, conferir e conectar os assistentes. Leva uns 15 minutos, quase tudo esperando o build.

## O que você precisa

- Uma conta no GitHub e uma no Render (pode entrar no Render com a conta do GitHub).
- Uma chave do OpenRouter para o chat do lab (openrouter.ai › Keys). Crie uma chave só para a aula, com limite de crédito.
- Uma senha inventada por você para ser o `ADMIN_TOKEN`. Ela libera aprovações, mudança de políticas e o reinício dos dados.

## Passo 1. Subir o código no GitHub

O ponto que mais quebra o deploy: **o `Dockerfile` e o `render.yaml` precisam ficar na raiz do repositório**, e não dentro de uma pasta `colliers-lab`.

A raiz do repositório deve ficar assim:

```
Dockerfile
render.yaml
requirements.txt
verificar.py
README.md
TUTORIAL.md
GUIA_DO_INSTRUTOR.md
app/
static/
```

### Pelo site do GitHub (sem instalar nada)

1. Em github.com, clique em **New repository**. Dê um nome (por exemplo `colliers-hub`), pode ser **Private**, e crie **sem** README.
2. Na página do repositório vazio, clique em **uploading an existing file**.
3. Abra a pasta `colliers-lab` que veio no zip, selecione **tudo o que está dentro dela** (os arquivos e as pastas `app` e `static`) e arraste para a página. Use Chrome ou Edge: eles mantêm as pastas.
4. Clique em **Commit changes**.
5. Confira na página do repositório que `Dockerfile` aparece logo na lista principal, ao lado das pastas `app` e `static`.

### Pelo terminal (se preferir)

```bash
cd colliers-lab
git init
git add .
git commit -m "Colliers Hub"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/colliers-hub.git
git push -u origin main
```

### Se você já tinha o lab antigo no GitHub e no Render

Substitua o conteúdo do repositório antigo pelo novo (apague os arquivos antigos e suba os novos, ou faça `git push` por cima). O Render publica de novo sozinho em alguns minutos. Pule para o passo 3 e só confira se a variável `ADMIN_TOKEN` existe em **Environment**.

## Passo 2. Criar o serviço no Render

1. Em dashboard.render.com, clique em **New** › **Blueprint**.
2. Conecte a conta do GitHub, se for a primeira vez, e escolha o repositório.
3. O Render lê o `render.yaml` e mostra um serviço chamado `colliers-lab`. Ele pede duas variáveis:
   - `ADMIN_TOKEN`: a senha que você inventou.
   - `OPENROUTER_API_KEY`: a chave do OpenRouter.
4. Clique em **Apply**. O primeiro build leva de 3 a 6 minutos.
5. Quando o serviço ficar **Live**, o endereço aparece no topo, algo como `https://colliers-lab-xxxx.onrender.com`.

O plano é o **Starter**, que não dorme. A cobrança é proporcional ao tempo ligado: suba na véspera e suspenda depois da aula. O plano gratuito também funciona, mas o serviço dorme sem uso e o primeiro acesso demora quase um minuto, o que atrapalha na sala.

### Variáveis opcionais

Em **Environment**, você pode acrescentar:

| Variável | Para quê |
| --- | --- |
| `APROVADOR_TOKEN` | Uma segunda senha que só aprova e rejeita pedidos. Útil para entregar a um aluno no papel de gerente. Sem ela, vale o `ADMIN_TOKEN`. |
| `MODELOS` | Modelos do OpenRouter oferecidos no chat, separados por vírgula. |
| `MCP_PATH` | Muda o endereço do MCP de `/mcp` para outro caminho, se não quiser um endereço óbvio. |

Mudar uma variável reinicia o serviço e recria os dados iniciais.

## Passo 3. Conferir

Abra o endereço no navegador: deve aparecer o Colliers Hub, com a visão geral, os módulos à esquerda e a atividade ao vivo.

Para uma conferência completa, rode no seu computador (só precisa de Python, sem instalar nada):

```bash
python verificar.py https://colliers-lab-xxxx.onrender.com SEU_ADMIN_TOKEN
```

Ele testa o painel, o chat, os 15 módulos, o MCP (lista as 9 ferramentas e faz uma leitura) e se o token está certo. No fim, aparece "Tudo certo." e o endereço para conectar os assistentes.

## Passo 4. Conectar os assistentes

O endereço do MCP é o do serviço com `/mcp` no fim, por exemplo `https://colliers-lab-xxxx.onrender.com/mcp`. Ele também aparece no Hub, em **Conectar um agente**.

- **Claude:** Configurações › Conectores › Adicionar conector personalizado. Cole o endereço e salve.
- **ChatGPT:** ative o modo desenvolvedor nas configurações e crie um conector com o endereço. Em contas Business e Enterprise, o administrador precisa liberar conectores personalizados antes.
- **Quem não puder conectar:** usa o chat do lab, em `/chat`, que tem as mesmas ferramentas e seis agentes prontos.

Faça um teste pedindo: "O que esta plataforma tem?". A chamada aparece na atividade ao vivo do Hub.

## Na manhã da aula

1. Abra o Hub › **Conectar um agente** › **Reiniciar os dados**. As datas dos contratos e cobranças passam a contar a partir de hoje.
2. Rode o `verificar.py` mais uma vez.
3. Deixe o Hub aberto no projetor. Na primeira aprovação, o navegador pede o token e o seu nome; ele guarda os dois até você fechar a aba.

## Se algo der errado

| O que aparece | Causa provável | Como resolver |
| --- | --- | --- |
| Build falha com "Dockerfile not found" ou "no such file" | Os arquivos foram para dentro de uma pasta no GitHub | Deixe `Dockerfile`, `app/` e `static/` na raiz do repositório (passo 1) |
| Deploy fica em "In progress" e depois falha no health check | O servidor não iniciou | Render › serviço › **Logs**. A última linha de erro diz o motivo. Faça **Manual Deploy › Clear build cache & deploy** |
| O Hub abre sem estilo ou com a tela branca | Arquivos da pasta `static` não subiram | Confira se `static/estilo.css`, `static/index.html` e `static/agentes/` estão no GitHub |
| Chat diz que está desligado | Falta `OPENROUTER_API_KEY` | Render › **Environment** › adicione a chave e salve |
| Chat responde com erro 401 ou 402 do provedor | Chave inválida ou sem crédito | Gere outra chave ou acrescente crédito no OpenRouter |
| "Token incorreto" ao aprovar | Senha digitada diferente da variável | Feche a aba do Hub, abra de novo e digite o token outra vez |
| O ChatGPT não deixa criar o conector | Conectores personalizados bloqueados na conta | Use o Claude ou o chat do lab |
| Os dados parecem velhos ou bagunçados | Uso de outras turmas ou testes | **Conectar um agente** › **Reiniciar os dados** |

## Depois da aula

No Render, abra o serviço › **Settings** › **Suspend Service** (ou **Delete**). O endpoint MCP não tem login e aceita escrita de qualquer pessoa com o endereço, por isso o Hub só tem dados fictícios e não deve ficar ligado sem necessidade.
