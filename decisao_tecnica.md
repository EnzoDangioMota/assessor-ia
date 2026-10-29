# Decisão técnica: escrita só depois do veredito do juiz

## 1. O que decidimos e por que

Escolhemos a abordagem de transacionar. O turno inteiro passa a usar uma única transação no Postgres. As tools de escrita continuam fazendo o INSERT, o UPDATE e o DELETE, mas não dão mais `commit()`. Quem decide se a escrita fica é o juiz, no momento em que ele dá o veredito.

Na prática, a fronteira que autoriza uma escrita é o `no_juiz`, em `app/juiz.py`. Ele chama `TurnoTx.finalizar()` (em `app/tools/turno_tx.py`) e o resultado é este:

| Situação | O que acontece no banco | O que o usuário vê |
|---|---|---|
| Juiz aprova (`apoiada`, noul igual ou maior que 0,70) | COMMIT: a escrita fica, uma vez só | a frase original |
| Juiz recusa (`parcial`, `sem_apoio` ou abaixo do limiar) | ROLLBACK: tudo volta ao que era antes do turno | "Não consegui confirmar essa operação, então não salvei nada. Pode reformular o pedido?" |
| Juiz não responde (timeout, erro de rede, resposta inválida, sem chave) | ROLLBACK | a mesma frase acima |
| Juiz aprova, mas o COMMIT falha | nada fica gravado | "Não consegui salvar essa operação. Nada foi gravado. Tente novamente." |
| Exceção no grafo ou bloqueio do guardrail | ROLLBACK feito pelo `finally` de `executar_fluxo_assessor` | o que já acontecia antes |

Se o turno recusado não tinha nenhuma escrita (uma consulta, por exemplo), a frase continua sendo a de sempre, "Não tenho evidência para afirmar isso."

Escolhemos essa fronteira porque o juiz já é o último nó antes do fim do grafo e já tem o poder de trocar a frase. Só faltava a transação começar antes dele e terminar nele. Não criamos nó novo, agente novo, rota nova nem mudamos a API, e o juiz continua julgando a mesma frase com a mesma evidência.

A garantia vale para `add_transaction`, `update_transaction` e `add_event`. Cobrimos também `update_event` e `delete_event`, porque elas também alteram o banco e deixar as duas como estavam manteria o mesmo furo na agenda.

Alguns detalhes de como funciona, porque eles explicam por que ficou assim:

- A primeira escrita do turno abre a conexão. Cada tool roda dentro de um SAVEPOINT, então se uma tool falha só o trabalho dela é desfeito e as anteriores do turno continuam pendentes.
- O turno fica guardado num `ContextVar`, que funciona como uma variável separada por requisição. As tools rodam em threads do LangGraph e mesmo assim enxergam o turno certo. Quando o modelo pede duas escritas ao mesmo tempo, um lock faz uma tool usar a conexão por vez.
- As consultas (`query_transactions`, `total_balance`, `daily_balance`, `query_events`, `check_conflicts`) passam a usar a mesma conexão depois da primeira escrita. Sem isso, um pedido como "registre X e me diga o saldo" mostraria o saldo sem o X, e o juiz recusaria uma frase que estava certa.
- Fora do grafo (o servidor MCP usa as mesmas tools) o comportamento é o de antes: commit ao sair.

Fluxo de antes:

```
guardrail_entrada, roteador, especialista (tool: INSERT + COMMIT + fecha a conexão),
orquestrador, guardrail_saida, juiz (pode trocar a frase), fim
                                    a linha já estava no banco
```

Fluxo de depois:

```
iniciar_turno, guardrail_entrada, roteador, especialista (tool: SAVEPOINT + INSERT, sem COMMIT),
orquestrador, guardrail_saida, juiz
    aprovou: COMMIT, fim
    recusou ou não respondeu: ROLLBACK, fim
encerrar_turno no finally: ROLLBACK de qualquer coisa que ainda esteja aberta
```

## 2. O que consideramos e deixamos de fora

**Interceptar** (julgar a ação antes de chamar a tool). Funcionaria como um segundo julgamento, da chamada `add_transaction(...)` contra a fala do usuário. A vantagem é que a escrita recusada nunca chegaria ao banco e não haveria conexão aberta esperando. O problema é que o juiz que temos julga a frase, e a frase só existe depois da tool, porque depende do id, da data e do valor que ela devolve. Julgar a ação seria outro julgamento, com outras regras e mais uma chamada HTTP por escrita. Além disso, a frase final ainda poderia ser infiel mesmo com a ação aprovada, e aí precisaríamos de outro mecanismo para desfazer a escrita. Ou seja, sozinha ela não cumpre a regra de que turno recusado não deixa escrita.

**Adiar** (a tool grava como pendente e o veredito promove ou descarta). Precisaria de uma coluna `status` ou de uma tabela de ações pendentes. Ganharíamos uma coisa boa: nenhuma conexão ficaria aberta durante as chamadas ao modelo, e a intenção pendente sobreviveria a um restart. Em troca teríamos migração de esquema, e as cinco consultas teriam que filtrar só o que está confirmado. Se esquecêssemos um filtro, o saldo mostraria dado que nunca foi aprovado. Teríamos também linhas pendentes órfãs quando o processo cai, pedindo uma varredura, e a tool devolveria ao modelo o resultado de um efeito que ainda não existe. Ficou de fora por ser mais superfície e mudança de esquema para uma garantia que a transação já dá sem isso.

**Compensar** (o commit continua na tool e, na recusa, executamos a ação contrária). Seria um DELETE do id inserido, um UPDATE de volta aos valores antigos, um novo INSERT para o evento removido. A vantagem é que não muda o ciclo de conexões e não prende conexão nenhuma. O custo é que entre o commit e a compensação o dado fica visível para outro turno, para o saldo, para a agenda. A compensação também não é atômica: se o processo cair entre os dois passos, o dado fica para sempre. E reverter um UPDATE pode apagar uma edição que alguém fez nesse meio tempo. Como a prática pede que nada permaneça, uma garantia de melhor esforço não serve.

## 3. O efeito nas métricas do SRE

Usamos como referência o `app/observabilidade.py`: SLO de p95 de 8 s, erro de 5%, status `ok`, `erro` ou `bloqueado`. Uma observação importante: o monitor só conta tokens e custo das chamadas de chat model do LangChain. O juiz chama a API por `urllib`, então ele não aparece em tokens nem em custo hoje.

**Transacionar (a que escolhemos)**
- Latência e p95: não existe chamada nova. O que muda é o lugar do COMMIT, que sai da tool e vai para o juiz, mais o SAVEPOINT e o RELEASE por tool, algo em torno de milissegundos. O que cresce é o tempo em que a conexão fica aberta, do primeiro INSERT até o veredito (orquestrador, guardrail de saída e juiz, que tem timeout de 30 s). Com muitos turnos de escrita ao mesmo tempo isso consome conexões do Postgres, e se o limite for atingido a espera para conectar entra na latência do turno e pressiona os 8 s.
- Taxa de erro e status: um turno recusado termina numa frase segura sem exceção, então o status continua `ok`, como era, e a taxa de erro não sobe por causa de recusas. Exceção no grafo continua sendo `erro` (e agora desfaz a escrita também). O bloqueio do guardrail de entrada continua `bloqueado` e não conta como erro. Um caso novo é o COMMIT que falha depois da aprovação: vira a frase "Não consegui salvar..." e o status fica `ok`, porque `status_do_estado` só olha o guardrail de entrada. Deixamos assim de propósito: contar como erro exigiria mexer no monitor, que está fora do limite da prática, e o caso é raro.
- Tokens e custo: iguais, porque não acrescentamos nenhuma chamada de modelo.

**Interceptar (descartada)**
- Seria uma chamada a mais ao juiz por turno com escrita, antes da tool. Isso soma a latência de uma ida HTTP (com timeout de até 30 s) ao caminho de escrita e empurra o p95 contra os 8 s. Se a pré-checagem fosse um modelo via LangChain, tokens e custo subiriam e apareceriam no monitor. Se fosse HTTP como o juiz de hoje, a latência sobe e tokens e custo não acompanham, o que seria um ponto cego do monitor.
- Taxa de erro e status: se a pré-checagem recusa, o turno termina numa frase segura sem exceção e o status fica `ok`. Se a pré-checagem falha (HTTP, timeout), o mais seguro é recusar também, então o erro só aparece se a falha virar exceção no grafo.
- A conexão: não fica aberta esperando o veredito, porque a escrita só acontece depois. Esse é o ponto a favor dela no monitor, mas o preço é a chamada extra.

**Compensar (descartada)**
- É um segundo efeito no banco em cada recusa: uma ida a mais ao Postgres, sem LLM. Se a compensação falhar, vira exceção e conta como `erro`. No caminho normal de recusa o status continua `ok`.
- Latência e p95: a ida extra ao Postgres é de milissegundos e só acontece nos turnos recusados, então o p95 quase não muda. A conexão também não fica presa esperando o veredito, porque o commit já aconteceu na tool.
- Tokens e custo: iguais, porque a compensação não chama modelo.

**Resumo lado a lado**

| | Transacionar (escolhida) | Interceptar | Compensar |
|---|---|---|---|
| Latência e p95 | sem chamada nova; conexão aberta até o veredito | uma ida HTTP a mais por escrita, empurra o p95 contra os 8 s | só milissegundos, e só nas recusas |
| Taxa de erro | recusa não é erro; exceção é `erro` | recusa não é erro | falha na compensação vira `erro` |
| Status | `ok` / `erro` / `bloqueado` como antes | `ok` na recusa | `ok` na recusa, `erro` se a compensação falhar |
| Tokens e custo | iguais | sobem se for modelo; ponto cego se for HTTP | iguais |
| Mecanismo | conexão aberta à espera do veredito | uma chamada a mais | um segundo efeito no banco |

## 4. As outras decisões

**add_google_event.** Não existe neste projeto, procuramos no código e nos prompts. Se existisse, seria um efeito fora do Postgres que o ROLLBACK não desfaz. Ficaria fora da transação ou só rodaria depois do COMMIT. Conferimos com uma busca no código e não há nenhuma referência a esse nome.

**salvar_mensagem (Mongo).** Continua como estava, depois do juiz, gravando a frase que o usuário viu, inclusive a de recusa. Ela é o histórico da conversa e não uma escrita do turno coberta pela regra. Se o processo cair depois do COMMIT e antes dela, a escrita aprovada existe sem registro no histórico.

**Juiz sem resposta.** Escolhemos falhar fechado. Timeout, erro de rede, resposta inválida e falta de chave já trocavam a frase pela frase segura, e agora também fazem ROLLBACK. O usuário vê que nada foi salvo e o banco fica igual ao de antes. O custo é perder uma operação válida quando o juiz está fora do ar, e o usuário pode simplesmente repetir o pedido.

**Processo que cai entre dois passos.** Antes do veredito, a conexão cai e o Postgres descarta a transação não confirmada, então não sobra nada. Como segurança extra, a sessão tem `idle_in_transaction_session_timeout` de 90 s (via `SET LOCAL`), para uma transação esquecida não segurar trava para sempre. Depois do COMMIT e antes de a resposta chegar ao usuário, a escrita aprovada permanece e o usuário não vê a confirmação.

**Repetição do mesmo pedido.** Depois de uma recusa não sobrou nada, então repetir é seguro e grava no máximo uma vez. Depois de uma aprovação, repetir grava de novo, porque não há chave de idempotência (era assim antes também). Duas chamadas idênticas dentro do mesmo turno também gravam duas vezes.

**Uma limitação que encontramos.** O histórico do LangGraph (o checkpointer) guarda as mensagens das tools do turno recusado, que dizem algo como "id X criado". A frase final do turno diz que nada foi salvo, o que orienta o modelo, mas ele ainda poderia citar esse id num turno seguinte. Não chegamos a testar esse cenário e o deixamos como risco conhecido: o id citado não existiria no banco, e o limite da prática não pede tratar o histórico do checkpointer.

**Limitação que já existia (roteador).** O roteador usa o modelo rápido do Groq, que às vezes tenta chamar uma tool que não existe, e a API responde 400 antes de qualquer especialista rodar. O turno termina em erro 500 e nenhuma transação chega a abrir, então a garantia não é afetada: repetir o pedido é seguro. Não tratamos isso por estar fora do limite da prática (outros fluxos).

**Evidência.** Em cada tentativa usamos um marcador único na mensagem do chat e conferimos o banco com uma consulta que lista, nas duas tabelas, tudo que tem um marcador `MARCA1x` (em `source_text`, `description` ou `title`), antes e depois. O rótulo do juiz vem do log do terminal.

| Tool | Marcador | Antes | Log do juiz | Depois | Resultado |
|---|---|---|---|---|---|
| add_transaction, recusa | `MARCA14` | nenhuma linha | `[juiz] erro http 401` | nenhuma linha | sem efeito |
| add_transaction, aprovação | `MARCA11` | nenhuma linha | `[juiz] apoiada noul=0.86` | `transactions` id 17, valor 12.34 | uma linha |
| update_transaction, recusa | `MARCA11` (para 99,99) | id 17, valor 12.34 | `[juiz] erro http 401` | id 17, valor 12.34 | valor antigo |
| update_transaction, aprovação | `MARCA11` (para 15,00) | id 17, valor 12.34 | `[juiz] apoiada noul=0.93` | id 17, valor 15.00 | alterado uma vez |
| add_event, recusa | `MARCA16` | nenhuma linha | `[juiz] erro http 401` | nenhuma linha | sem efeito |
| add_event, aprovação | `MARCA15` | `events` só com o id 3 (`MARCA13`) | `[juiz] apoiada noul=0.80` | `events` id 5, `MARCA15`, 30/10 às 15h | uma linha |

Nas três recusas o chat mostrou "Não consegui confirmar essa operação, então não salvei nada. Pode reformular o pedido?". Essa frase só aparece quando houve uma escrita no turno que foi desfeita. Quando a tool não chegou a gravar, a frase é a genérica, "Não tenho evidência para afirmar isso.", e por isso descartamos duas tentativas que a mostraram e repetimos até ver a frase certa. Na tabela de eventos, o id 4 ficou sem linha entre o 3 e o 5: é compatível com o INSERT desfeito do `MARCA16`, já que as sequências do Postgres não voltam atrás num rollback.

Para provocar a recusa de forma garantida, subimos a API com a chave do juiz inválida, o que faz o juiz responder com erro HTTP (`[juiz] erro http 401`) e o turno ser recusado. Esse caminho é o do juiz que não responde, e não o de uma recusa por mérito. Não chegamos a provocar uma recusa por mérito (veredito `parcial` ou `sem_apoio`, como no caso da compra em dólares). O código faz os dois caminhos passarem pela mesma função, `_reprovar`, que chama `_encerrar_escrita(False)` e desfaz a transação, então o efeito no banco é o mesmo.

## 5. Arquivos criados e modificados

Criados:
- `app/tools/turno_tx.py`: a transação do turno (`TurnoTx`, `escrita()`, `leitura()`, `iniciar_turno()`, `encerrar_turno()`).

Modificados:
- `app/tools/financeiro.py`: as tools passam a usar `escrita()` e `leitura()` e deixam de dar `commit()`. Também corrigimos o `update_transaction`, que não funcionava (faltava a função `_local_date_filter_sql`, a chamada a `_resolve_category_name` estava com argumento a menos e ela nem estava em `TOOLS`).
- `app/tools/agenda.py`: `add_event`, `update_event`, `delete_event` e as consultas passam a usar `escrita()` e `leitura()`, sem `commit()`.
- `app/juiz.py`: o veredito agora confirma ou desfaz a transação do turno (`_encerrar_escrita`), e há duas frases novas para quando nada foi salvo.
- `app/graph.py`: `executar_fluxo_assessor` abre o turno antes de rodar o grafo e chama `encerrar_turno()` no `finally`.
- `app/prompts.py`: o prompt do financeiro mandava converter datas para `DD-MM-YYYY`, formato que o Postgres rejeita e que contradiz as tools, que declaram `YYYY-MM-DD`. Passou a `YYYY-MM-DD`. É um ajuste de baixo risco, fora da solução em si, feito porque a data inválida derrubava `add_transaction` e `update_transaction` antes de o juiz entrar.
