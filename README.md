# acs-toolbox

Utilitários de uso geral para automação, banco de dados PostgreSQL, downloads, progresso e segredos.
Referência completa das classes: [docs/acs_toolbox.md](https://github.com/AlbertoCamposSilva/acs-toolbox/blob/main/docs/acs_toolbox.md).

## Instalação (uv)

Em outro projeto gerenciado por uv:

```bash
uv add acs-toolbox                    # núcleo (Download, Progress)
uv add "acs-toolbox[database]"        # + Database (psycopg2, pandas, numpy)
uv add "acs-toolbox[webdriver]"       # + WebDriver (selenium)
uv add "acs-toolbox[gcp]"             # + segredos (Google Secret Manager)
uv add "acs-toolbox[all]"             # tudo
```

Como dependência de um `pyproject.toml`:

```toml
dependencies = ["acs-toolbox[database,webdriver]>=0.1"]
```

## Extras

| Extra       | Habilita                | Dependências                        |
|-------------|-------------------------|-------------------------------------|
| (núcleo)    | `Download`, `Progress`  | nenhuma                             |
| `database`  | `Database`              | pandas, numpy, psycopg2-binary      |
| `webdriver` | `WebDriver`             | selenium                            |
| `notebook`  | limpeza de saída Jupyter no `Progress` | ipython              |
| `gcp`       | `segredos` (Google Secret Manager) | google-cloud-secret-manager |

Importar um módulo sem o extra correspondente gera um `ImportError` que indica o comando de instalação.

## Configuração do banco

`Database()` obtém os parâmetros de conexão (`host`, `port`, `database`, `user`, `password`)
nesta ordem:

1. argumento `dbparams={...}`;
2. arquivo `.ini` (seção `[postgresql]`): argumento `config_file=...` ou variável de ambiente
   `ACS_TOOLBOX_DB_CONFIG`;
3. o segredo `postgresql` do cofre de segredos (ver abaixo).

Se nenhuma fonte estiver configurada, o erro explica as opções. Não versione o arquivo `.ini`.

## Segredos (Google Secret Manager)

O módulo `acs_toolbox.segredos` lê segredos de **um único segredo JSON** no Google Secret Manager,
em vez de `.env` ou arquivos espalhados. O programa pede só as chaves de que precisa:

```python
from acs_toolbox.segredos import get_secret, get_secrets, load_env

api_key = get_secret("MINHA_API_KEY")
cfg = get_secrets("DB_HOST", "DB_PORT")   # {"DB_HOST": ..., "DB_PORT": ...}
load_env("MINHA_API_KEY")                 # copia para os.environ (código que usa os.getenv)
```

- O conteúdo é baixado uma vez por processo e fica só em memória.
- Uma variável de ambiente com o nome da chave tem precedência (testes, CI, uso offline).
- Configuração por variáveis de ambiente (identificadores, não segredos):
  `ACS_TOOLBOX_GCP_PROJECT` (id do projeto) e `ACS_TOOLBOX_SECRET_NAME` (padrão `acs-toolbox-secrets`).
- Instalação e login: `uv add "acs-toolbox[gcp]"` e `gcloud auth application-default login`.
- Filtrar por chaves reduz a exposição no processo, mas não é uma barreira de acesso: quem lê o
  segredo recebe o JSON inteiro. Use segredos separados quando precisar de isolamento.

## Desenvolvimento

```bash
uv sync                # cria .venv e instala com extras + dev
uv run pytest          # testes; os de integração exigem ACS_TOOLBOX_TEST_DSN (PostgreSQL)
uv run ruff check .
uv run mypy
uv build               # gera dist/*.whl e dist/*.tar.gz
```

A publicação no PyPI é feita pelo GitHub Actions (Trusted Publishing) ao criar um release;
ver [.github/workflows/publish.yml](https://github.com/AlbertoCamposSilva/acs-toolbox/blob/main/.github/workflows/publish.yml).

## Licença

Apache License 2.0 — veja [LICENSE](https://github.com/AlbertoCamposSilva/acs-toolbox/blob/main/LICENSE).
Copyright 2026 Alberto de Campos e Silva.
