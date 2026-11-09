FROM ghcr.io/astral-sh/uv:0.9.5 AS uv
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

COPY --from=uv /uv /uvx /usr/local/bin/
# The base image's optional Yarn repository has an expired signing key.
# This Python project does not use Yarn.
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends make ripgrep nodejs \
    && rm -rf /var/lib/apt/lists/*
