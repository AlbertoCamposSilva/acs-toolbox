"""
Acesso centralizado a segredos (Google Secret Manager).

Todos os segredos ficam em **um único segredo JSON** no Secret Manager
(``{"CHAVE": "valor", "postgresql": {"host": ...}}``). O programa informa
quais chaves quer; o conteúdo é baixado uma vez por processo e mantido só em
memória. Uma variável de ambiente já definida com o nome da chave tem
precedência (útil para testes, CI e uso offline).

Configuração (identificadores, não segredos), por variável de ambiente:

* ``ACS_TOOLBOX_GCP_PROJECT``: id do projeto Google Cloud.
* ``ACS_TOOLBOX_SECRET_NAME``: nome do segredo (padrão ``acs-toolbox-secrets``).

Requer o extra ``gcp`` (``uv add "acs-toolbox[gcp]"``) e credenciais de aplicação
(``gcloud auth application-default login``).

Nunca são registrados nem exibidos valores; as mensagens de erro citam só nomes de chaves.
"""
from __future__ import annotations

import copy
import json
import os
import threading
from collections.abc import Iterable
from typing import Any

ENV_PROJECT = 'ACS_TOOLBOX_GCP_PROJECT'
ENV_SECRET_NAME = 'ACS_TOOLBOX_SECRET_NAME'
DEFAULT_SECRET_NAME = 'acs-toolbox-secrets'

_MISSING: Any = object()
_lock = threading.Lock()
_cache: dict[tuple[str, str], dict[str, Any]] = {}


class SecretsNotConfigured(RuntimeError):
    """O cofre não está configurado (falta ``ACS_TOOLBOX_GCP_PROJECT``)."""


class SecretNotFound(KeyError):
    """Uma ou mais chaves não existem nem no ambiente nem no cofre."""

    def __init__(self, keys: Iterable[str]) -> None:
        self.keys = list(keys)
        super().__init__(f'Segredo(s) não encontrado(s): {", ".join(self.keys)}')

    def __str__(self) -> str:
        return str(self.args[0])


def _fetch_payload(project: str, name: str) -> dict[str, Any]:
    """Baixa e decodifica a versão mais recente do segredo JSON."""
    try:
        from google.cloud import secretmanager
    except ImportError as e:  # pragma: no cover - depende do extra
        raise ImportError(
            'Instale o extra "gcp": uv add "acs-toolbox[gcp]"') from e

    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(
        request={'name': f'projects/{project}/secrets/{name}/versions/latest'})
    try:
        data = json.loads(response.payload.data.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # ``from None``: o JSONDecodeError guarda o documento inteiro (o segredo).
        raise ValueError('O segredo não contém JSON válido em UTF-8.') from None
    if not isinstance(data, dict):
        raise ValueError('O segredo deve conter um objeto JSON (chave -> valor).')
    return data


def _config() -> tuple[str, str] | None:
    project = os.environ.get(ENV_PROJECT)
    if not project:
        return None
    return project, os.environ.get(ENV_SECRET_NAME) or DEFAULT_SECRET_NAME


def load_payload(refresh: bool = False) -> dict[str, Any]:
    """Cópia do conteúdo completo do cofre (cache por processo). Prefira ``get_secrets``."""
    cfg = _config()
    if cfg is None:
        raise SecretsNotConfigured(
            f'Defina a variável de ambiente {ENV_PROJECT} (id do projeto Google Cloud) '
            f'e, se necessário, {ENV_SECRET_NAME}.')
    with _lock:
        if refresh or cfg not in _cache:
            _cache[cfg] = _fetch_payload(*cfg)
        return copy.deepcopy(_cache[cfg])


def clear_cache() -> None:
    """Descarta o conteúdo em memória (o próximo acesso baixa de novo)."""
    with _lock:
        _cache.clear()


def get_secrets(*keys: str, default: Any = _MISSING) -> dict[str, Any]:
    """
    Devolve ``{chave: valor}`` para as chaves pedidas.

    Ordem: variável de ambiente com o mesmo nome; depois o cofre. Se alguma chave
    não for encontrada e não houver ``default``, levanta ``SecretNotFound`` listando
    todos os nomes ausentes. Se o cofre não estiver configurado, levanta
    ``SecretsNotConfigured`` (a menos que haja ``default``).
    """
    result: dict[str, Any] = {}
    pending = []
    for key in keys:
        if key in os.environ:
            result[key] = os.environ[key]
        else:
            pending.append(key)

    if pending:
        try:
            payload = load_payload()
        except SecretsNotConfigured:
            if default is _MISSING:
                raise
            payload = {}
        missing = []
        for key in pending:
            if key in payload:
                result[key] = payload[key]
            elif default is not _MISSING:
                result[key] = default
            else:
                missing.append(key)
        if missing:
            raise SecretNotFound(missing)
    return {key: result[key] for key in keys}


def get_secret(key: str, default: Any = _MISSING) -> Any:
    """Valor de uma chave (ver ``get_secrets``)."""
    return get_secrets(key, default=default)[key]


def load_env(*keys: str, override: bool = False) -> dict[str, Any]:
    """
    Copia as chaves para ``os.environ`` (migração de código que usa ``os.getenv``).

    Só aceita valores em texto; por padrão não sobrescreve variáveis já definidas.
    """
    values = get_secrets(*keys)
    for key, value in values.items():
        if not isinstance(value, str):
            raise TypeError(f'O segredo "{key}" não é texto; use get_secret().')
        if override or key not in os.environ:
            os.environ[key] = value
    return values
