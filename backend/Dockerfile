FROM python:3.11-slim

WORKDIR /app

# system deps (torch/flagembedding иногда требуют базовые либы)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# код будет примонтирован volume-ом в compose, но можно и копировать:
# COPY . /app

ENV PYTHONUNBUFFERED=1
