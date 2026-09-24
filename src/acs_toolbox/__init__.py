"""
Pacote acs_toolbox
------------------
Utilitários de uso geral para automação, banco de dados (PostgreSQL),
downloads e acompanhamento de progresso.

Os submódulos são carregados sob demanda, para que ``import acs_toolbox``
não exija todas as dependências opcionais (extras ``database``,
``webdriver``, ``notebook`` e ``gcp``).
"""

from importlib import import_module
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("acs-toolbox")
except PackageNotFoundError:  # pragma: no cover - executando sem instalação
    __version__ = "0+unknown"

__all__ = [
    "database",
    "download",
    "progress",
    "segredos",
    "webdriver",
]


def __getattr__(name):
    if name in __all__:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals()) + __all__)
