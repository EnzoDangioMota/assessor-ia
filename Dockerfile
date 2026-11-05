FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencias primeiro: a camada so e refeita quando o requirements.txt muda.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY data ./data

# Usuario sem privilegios para executar a API.
RUN useradd --create-home appuser
USER appuser

# O Render define PORT (padrao 10000); localmente usa 10000 tambem.
EXPOSE 10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
