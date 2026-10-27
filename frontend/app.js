const API_BASE = window.location.origin;
const SESSION_STORAGE_KEY = "assistente_session_id";

const composer = document.getElementById("composer");
const perguntaInput = document.getElementById("pergunta");
const enviarButton = document.getElementById("enviar");
const thread = document.getElementById("thread");
const threadEmpty = document.getElementById("thread-empty");
const hint = document.getElementById("hint");
const resetButton = document.getElementById("reset-session");
const sessionIdElement = document.getElementById("session-id");
const statusDot = document.getElementById("status-dot");
const fileInput = document.getElementById("arquivo");
const filesList = document.getElementById("files-list");
const filesStatus = document.getElementById("files-status");
const USER_ID = "usuario_teste";

function gerarSessionId() {
    if (crypto.randomUUID) {
        return crypto.randomUUID();
    }

    return "sessao-" + Date.now();
}

let sessionId = localStorage.getItem(SESSION_STORAGE_KEY);

if (!sessionId) {
    sessionId = gerarSessionId();
    localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
}

if (sessionIdElement) {
    sessionIdElement.textContent = sessionId;
}

function adicionarMensagem(texto, tipo) {
    if (threadEmpty) {
        threadEmpty.style.display = "none";
    }

    const mensagem = document.createElement("div");

    mensagem.classList.add("message");
    mensagem.classList.add(`message--${tipo}`);
    mensagem.textContent = texto;

    thread.appendChild(mensagem);
    thread.scrollTop = thread.scrollHeight;

    return mensagem;
}

function setHint(texto) {
    if (hint) {
        hint.textContent = texto;
    }
}

function setStatus(online) {
    if (statusDot) {
        statusDot.classList.toggle("status--offline", !online);
    }
}

async function enviarPergunta(pergunta) {
    try {
        enviarButton.disabled = true;
        perguntaInput.disabled = true;

        setHint("Pensando...");

        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                session_id: sessionId,
                user_id: USER_ID,
                pergunta: pergunta
            })
        });

        if (!response.ok) {
            const erro = await response.text();
            throw new Error(erro || `Erro ${response.status}`);
        }

        const data = await response.json().catch(() => ({}));

        console.log("Resposta:", data);

        adicionarMensagem(
            data.resposta || data.response || data.message || "Não recebi uma resposta.",
            "assistant"
        );

        setHint("Pronto.");
        setStatus(true);

    } catch (error) {
        console.error("Erro:", error);

        adicionarMensagem(
            "Erro ao enviar a pergunta: " + error.message,
            "error"
        );

        setHint("Erro ao conectar com a API.");
        setStatus(false);

    } finally {
        enviarButton.disabled = false;
        perguntaInput.disabled = false;
        perguntaInput.focus();
    }
}

composer.addEventListener("submit", async (event) => {
    event.preventDefault();

    const pergunta = perguntaInput.value.trim();

    if (!pergunta) {
        return;
    }

    adicionarMensagem(pergunta, "user");

    perguntaInput.value = "";

    await enviarPergunta(pergunta);
});

perguntaInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        composer.requestSubmit();
    }
});

async function encerrarSessaoAtual(id) {
    try {
        const response = await fetch(
            `${API_BASE}/sessions/${encodeURIComponent(id)}/encerrar`,
            {
                method: "POST"
            }
        );

        if (!response.ok) {
            return null;
        }

        const data = await response.json();

        return data.resumo;

    } catch (error) {
        console.error("Erro ao encerrar sessão:", error);
        return null;
    }
}

async function iniciarNovaSessao() {
    resetButton.disabled = true;

    await encerrarSessaoAtual(sessionId);

    sessionId = gerarSessionId();

    localStorage.setItem(
        SESSION_STORAGE_KEY,
        sessionId
    );

    if (sessionIdElement) {
        sessionIdElement.textContent = sessionId;
    }

    thread.innerHTML = "";

    if (threadEmpty) {
        thread.appendChild(threadEmpty);
        threadEmpty.style.display = "block";
    }

    setHint("Nova sessão iniciada.");

    resetButton.disabled = false;

    perguntaInput.focus();
}

resetButton.addEventListener(
    "click",
    iniciarNovaSessao
);

function setFilesStatus(texto, erro = false) {
    filesStatus.textContent = texto;
    filesStatus.classList.toggle("is-error", erro);
}

async function carregarArquivos() {
    const response = await fetch(
        `${API_BASE}/documents?user_id=${encodeURIComponent(USER_ID)}`
    );
    if (!response.ok) {
        throw new Error(`Não foi possível listar arquivos (HTTP ${response.status}).`);
    }

    const data = await response.json();
    filesList.replaceChildren();
    for (const arquivo of data.documents) {
        const item = document.createElement("li");
        item.className = "files__item";

        const nome = document.createElement("span");
        nome.className = "files__name";
        nome.textContent = `${arquivo.file_name} · ${arquivo.chunks} trechos`;

        const remover = document.createElement("button");
        remover.type = "button";
        remover.className = "files__remove";
        remover.textContent = "remover";
        remover.setAttribute("aria-label", `Remover ${arquivo.file_name}`);
        remover.addEventListener("click", async () => {
            remover.disabled = true;
            try {
                const result = await fetch(
                    `${API_BASE}/documents/${encodeURIComponent(arquivo.document_id)}?user_id=${encodeURIComponent(USER_ID)}`,
                    { method: "DELETE" }
                );
                if (!result.ok) {
                    throw new Error(`Não foi possível remover o arquivo (HTTP ${result.status}).`);
                }
                await carregarArquivos();
                setFilesStatus("Arquivo removido.");
            } catch (error) {
                setFilesStatus(error.message, true);
                remover.disabled = false;
            }
        });

        item.append(nome, remover);
        filesList.append(item);
    }
}

fileInput.addEventListener("change", async () => {
    const arquivo = fileInput.files[0];
    if (!arquivo) {
        return;
    }
    if (arquivo.size > 10 * 1024 * 1024) {
        setFilesStatus("O arquivo excede o limite de 10 MB.", true);
        fileInput.value = "";
        return;
    }

    const form = new FormData();
    form.append("arquivo", arquivo);
    setFilesStatus("Lendo e indexando arquivo...");
    fileInput.disabled = true;
    try {
        const response = await fetch(
            `${API_BASE}/documents?user_id=${encodeURIComponent(USER_ID)}`,
            { method: "POST", body: form }
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || `Erro ${response.status}`);
        }
        await carregarArquivos();
        setFilesStatus(`${data.file_name} pronto para consulta.`);
    } catch (error) {
        setFilesStatus(error.message, true);
    } finally {
        fileInput.disabled = false;
        fileInput.value = "";
    }
});

carregarArquivos().catch((error) => setFilesStatus(error.message, true));

async function verificarAPI() {
    try {
        const response = await fetch(`${API_BASE}/health`);

        if (!response.ok) {
            throw new Error("API indisponível");
        }

        setStatus(true);
        setHint("Assistente pronto.");

    } catch (error) {
        console.error("API:", error);

        setStatus(false);
        setHint("API indisponível.");
    }
}

verificarAPI();