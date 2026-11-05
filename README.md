# Assessor IA

## Executar a API e o chat

Instale as dependências de `requirements.txt`, configure as credenciais no `.env` e, na raiz do projeto, inicie a API:

```powershell
python -m uvicorn app.main:app --reload
```

O chat fica em `http://localhost:8000/`. O monitoramento fica em `http://localhost:8000/monitor.html` e seu endpoint JSON em `http://localhost:8000/monitor`.

## Arquivos do usuário

Na tela do chat, anexe planilhas `.xlsx`, PDFs pesquisáveis, arquivos `.csv`, `.txt`/`.md` ou imagens `.png`, `.jpg`, `.jpeg` e `.webp` (até 10 MB). O texto extraído é dividido em trechos, convertido em embeddings e salvo na collection `documentos_usuario` do Qdrant, filtrado pelo `user_id`. O mesmo nome enviado novamente substitui o arquivo anterior daquele usuário. É possível listar e remover arquivos pela própria tela.

O chat consulta os trechos relevantes quando uma pergunta sobre finanças ou agenda depende dos arquivos. Excel, PDF, CSV e texto são extraídos localmente; imagens são transcritas pelo Gemini configurado em `GEMINI_MODEL`. A indexação usa o modelo de embeddings já adotado pela aplicação. Portanto, não é necessário trocar o modelo: mantenha `GEMINI_API_KEY`, `QDRANT_URL` e as demais configurações existentes. O conteúdo de imagens é enviado ao Gemini e os embeddings dos textos são enviados ao provedor configurado; não anexe dados que não queira processar nesses serviços. PDFs digitalizados sem texto pesquisável ainda não são lidos — envie a página como imagem.

## Juiz de evidências (JEV)

O chat confere respostas finais com o JEV da TypeSafe antes de entregá-las. A conferência cobre respostas do roteador, do FAQ e as respostas que passaram pelo guardrail de saída. Se `TYPESAFE_API_KEY` não estiver configurada ou o serviço falhar, o chat usa a resposta segura `Não tenho evidência para afirmar isso.`; a variável é opcional e não impede a API de iniciar. Configure sua chave no `.env` e reinicie o servidor. Não compartilhe nem versione essa chave.

## Servidor MCP

O arquivo `.cursor/mcp.json` registra o servidor MCP local. O Cursor precisa usar um Python que tenha as dependências do projeto, inclusive `mcp[cli]`. Se `python` não apontar para esse ambiente, atualize `command` no JSON para o caminho do executável Python correto. O processo usa o mesmo `DATABASE_URL` do Assessor e publica as ferramentas financeiras e de agenda em stdio.

## Observabilidade e LangSmith

`/monitor` agrega os últimos 50 turnos do processo atual. Armazena horário, sessão, latência, rota, status, tokens e custo estimado; não armazena prompt nem resposta. Os dados ficam apenas em memória e são apagados quando a API reinicia. O p95 e a taxa de erro são comparados aos limites de 8 segundos e 5%. Modelos sem preço cadastrado são indicados no painel e não são apresentados como custo zero conhecido.

O tracing remoto é opcional. Para habilitá-lo, acrescente ao `.env` e reinicie a API:

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=sua-chave
LANGSMITH_PROJECT=assessor-aula
```

Os traces enviados ao LangSmith incluem o conteúdo das chamadas ao modelo; use dados fictícios ao testar e não compartilhe a chave.