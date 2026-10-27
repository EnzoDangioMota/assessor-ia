# JUSTIFICATIVA

## 1. Quais arquivos você criou ou modificou? Indique o caminho de cada um.

**Criados**
- `app/perfil.py` — persistência: grava/consulta o dado estruturado no MongoDB e as preferências no Qdrant.
- `app/routes/perfil.py` — rota `POST /perfil`, único ponto de entrada HTTP do perfil.
- `app/tools/perfil.py` — tool `consultar_perfil_financeiro`, usada pelo especialista financeiro.
- `frontend/perfil.html`, `frontend/perfil.js`, `frontend/perfil.css` cópia identica da tela Perfil fornecida pelo grilo, colocada ao lado do `index.html` para ficar disponível em `/perfil.html`.

**Modificados**
- `app/schemas.py` — adicionei `PerfilRequest` (contrato da tela) e `PerfilResponse`.
- `app/vectorstore.py` — adicionei `COLLECTION_PERFIL` e a função `garantir_collection()`.
- `app/main.py` — registrei o router de `app/routes/perfil.py`.
- `app/graph.py` — importei `TOOLS_PERFIL` e passei `tools = TOOLS + TOOLS_PERFIL` para o `financeiro_agent` que já existe (nenhum agente novo).
- `app/prompts.py` — adicionei ao `FINANCEIRO_PROMPT` as regras de quando chamar a tool de perfil, de não inventar dado sem cadastro, e de não alterar perfil pelo chat.

Nada em `app/tools/financeiro.py`, `app/graph.py` (fora da linha de tools), roteador, agenda, FAQ, memória ou no frontend do chat foi tocado além do necessário para inserir a feature o perfil.

## 2. Por onde o perfil entra, e onde cada parte dele é gravada?

Entra só por `POST /perfil` que é consumida pela tela `perfil.html`. A partir disso `salvar_perfil()` em `app/perfil.py` grava renda/objetivo/tolerância no MongoDB collection `perfis` e o texto de preferências, já embeddado, no Qdrant collection `perfil_preferencias`, e as duas escritas disparadas pela mesma chamada, não em momentos diferentes.

## 3. Como as preferências são guardadas e consultadas, e por que não é busca por palavra?

São guardadas como um vetor de embedding do texto completo no Qdrant. A consulta gera o embedding do assunto da pergunta atual e busca por similaridade filtrada por `user_id`. Não é busca por palavra porque frases como "não quero nada agressivo" precisam ser reconhecidas como relevantes para uma pergunta sobre "cripto" mesmo sem a palavra "cripto" aparecer no texto. Regex/keyword não capturam isso, similaridade semântica sim.

## 4. Você criou uma tool ou duas? Por quê?

Uma só que foi `consultar_perfil_financeiro`. Ela devolve numérico + texto livre juntos porque o especialista sempre precisa dos dois ao mesmo tempo para aconselhar sem inventar (ex: renda alta não anula uma restrição escrita em preferências). Duas tools separadas arriscariam o agente chamar só uma e formar uma recomendação incompleta. uma tool combinada é uma única checagem "tem perfil? o que ele diz?" antes de qualquer conselho.

## 5. O que garante que o perfil de um usuário não apareceria para outro, se houvesse mais de um?

No Mongo, a consulta é por `_id = user_id` (chave direta). No Qdrant, toda busca inclui `query_filter` por `user_id`, e mesmo com múltiplos perfis na mesma collection, só pontos com aquele `user_id` no payload entram no resultado. Como o `user_id` vem do contexto da requisição e não é argumento da tool, o modelo não tem como pedir o perfil de outra pessoa.

## 6. Sua tool consulta o banco diretamente ou faz uma chamada HTTP na própria API? Por quê?

Consulta o banco diretamente Mongo + Qdrant, no mesmo padrão de `tools/faq.py` e `tools/memoria.py`. Não existe rota de leitura para chamar via HTTP. O enunciado proíbe de criar, e mesmo que existisse, dar um round-trip HTTP para a própria API adicionaria latência, um ponto de falha de rede e complexidade de auth sem nenhum ganho, já que a tool roda no mesmo processo que tem os clients de banco prontos.

## 7. Por que não existe um agente "perfil"?

Porque perfil não é uma intenção de conversa (como finanças, agenda ou FAQ), é só dado de apoio que só existe para o especialista financeiro aconselhar melhor. Ele nunca é o destino de uma pergunta do roteador, é consultado, via tool, dentro do fluxo que já existe para financeiro. Criar um agente seria dar a ele um domínio de conversa que o enunciado explicitamente diz que ele não tem.

## 8. Por que o chat não altera o cadastro?

Porque não existe nenhuma tool de escrita de perfil exposta para nenhum agente, só a de leitura. O prompt do financeiro também instrui explicitamente a recusar pedidos de alteração pelo chat e apontar para a tela. A tela é a única superfície com rota de escrita `POST /perfil`. O chat estruturalmente não tem como gravar, mesmo que o usuário peça.