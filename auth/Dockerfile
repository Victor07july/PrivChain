FROM python:3.13-bookworm AS builder
SHELL ["/bin/bash", "-c"] 
WORKDIR /usr/app
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y libmagic-dev nodejs npm
COPY . /usr/app

# Instalar bibliotecas Solidity para compilação de contratos
RUN npm install -g @openzeppelin/contracts@4.9.6
# Adicione mais bibliotecas aqui se necessário:
# RUN npm install -g @chainlink/contracts@0.8.0

RUN pip install uv
RUN uv venv
RUN uv sync

ENV PATH="/usr/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/usr/app/.venv"

RUN source .venv/bin/activate
RUN uv pip install -r pyproject.toml

FROM builder AS dev
# RUN pip install -r src/config/requirements/dev.txt
ENTRYPOINT ["/bin/sh", "docker/api-entrypoint-scripts/docker-entrypoint.sh"]


FROM builder AS prod
ENTRYPOINT ["/bin/sh", "docker/api-entrypoint-scripts/docker-entrypoint.sh"]
