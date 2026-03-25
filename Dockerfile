# Python 3.11 fisso: psycopg2-binary non è compatibile con Python 3.14 su Render.
# Nel dashboard del servizio: Environment = Docker, oppure usa solo PYTHON_VERSION=3.11.9 (vedi render.yaml).
FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY courseconnect-main/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

COPY courseconnect-main/ .

CMD exec gunicorn --bind 0.0.0.0:${PORT} app:app
