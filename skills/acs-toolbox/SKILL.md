---
name: acs-toolbox
description: Como usar a biblioteca Python acs-toolbox (PyPI) — Database (PostgreSQL/psycopg2 com upsert de DataFrame, inserção de listas de dicionários, leitura massiva via COPY), WebDriver (Selenium/Chrome configurado para downloads), Download (esperar e renomear arquivos baixados), Progress (progresso com estimativa de término) e segredos (Google Secret Manager). Use sempre que o projeto importar acs_toolbox ou tiver acs-toolbox nas dependências, quando o usuário pedir para adicionar/usar/migrar para o acs-toolbox, ou quando ele quiser nesses projetos consultar/gravar no PostgreSQL, automatizar downloads com Chrome, mostrar progresso de um laço longo ou ler credenciais do Secret Manager — mesmo que não cite o nome da biblioteca.
---

# acs-toolbox

Biblioteca de utilitários do autor para os seus projetos Python. Prefira-a a reescrever o mesmo
código (conexão Postgres, espera de download, barra de progresso, leitura de segredos): ela já trata
casos que costumam dar errado — escape de identificadores SQL, downloads parciais `.crdownload`,
travas de arquivo do Windows, segredos que não vazam em logs.

A referência completa de cada classe, com todos os parâmetros, está em
`references/api.md`. Leia a seção do módulo que for usar antes de escrever código não trivial.

## Instalação

Cada módulo tem um extra; instale só o necessário:

| Módulo | Extra | Dependências |
|---|---|---|
| `acs_toolbox.download`, `acs_toolbox.progress` | (núcleo) | nenhuma |
| `acs_toolbox.database` | `database` | pandas, numpy, psycopg2-binary |
| `acs_toolbox.webdriver` | `webdriver` | selenium |
| `acs_toolbox.segredos` | `gcp` | google-cloud-secret-manager |
| limpeza de saída no Jupyter (`Progress`) | `notebook` | ipython |

```bash
uv add "acs-toolbox[database,webdriver]"   # projeto com uv
pip install "acs-toolbox[all]"             # ou pip
```

No `pyproject.toml`: `dependencies = ["acs-toolbox[database]>=0.1"]`. Se um import falhar com
"Instale o extra ...", é o extra que falta — não instale os pacotes avulsos.

## Qual módulo usar

- **Ler/gravar no PostgreSQL** → `Database`. Consultas: `query`/`execute`. Muitos registros:
  `insert_list_of_dicts` (lista de dicts) ou `upsert_dataframe` (DataFrame grande, via COPY).
  Ler muito: `read_sql_to_df`.
- **Baixar arquivos de um site** → `WebDriver` (abre o Chrome já apontado para a pasta) +
  `Download` (espera terminar e renomeia).
- **Laço demorado** → `Progress`.
- **Senhas, tokens, parâmetros de conexão** → `segredos`, nunca valores no código.

## Database

```python
from acs_toolbox.database import Database

with Database() as db:  # commit ao sair; rollback em exceção; fecha a conexão
    linhas, colunas = db.query("SELECT id, nome FROM clientes WHERE uf = %s", "SP")
    db.execute("UPDATE clientes SET ativo = %s WHERE id = %s", (True, 42))
    chaves, _ = db.insert_list_of_dicts("vendas.itens", itens, id_columns=["id"])
    db.upsert_dataframe(df, "vendas.resumo", primary_key_col="id", verbose=False)
    df2 = db.read_sql_to_df("SELECT * FROM vendas.resumo WHERE ano = %s", 2026,
                            dtypes={"codigo": str})
```

Configuração da conexão, nesta ordem: `dbparams={...}` → arquivo `.ini` com seção `[postgresql]`
(`config_file=` ou variável `ACS_TOOLBOX_DB_CONFIG`) → chave `postgresql` do cofre de segredos.
Em código novo, prefira o cofre ou `ACS_TOOLBOX_DB_CONFIG` a caminhos fixos; nunca escreva senha
no código e mantenha `*.ini` no `.gitignore`.

Pontos que costumam causar erro:
- Valores sempre como parâmetros (`%s`), nunca com f-string no SQL. Com parâmetros, `%` literal vira
  `%%`. Um parâmetro único pode ir sem lista.
- `ON CONFLICT` (em `insert_list_of_dicts`, `insert_dict`, `upsert_dataframe`) exige
  `PRIMARY KEY`/`UNIQUE` nas colunas de conflito — crie a restrição se a tabela não tiver.
- `upsert_dataframe`: a tabela precisa existir e as colunas do DataFrame devem ter exatamente os
  nomes das colunas da tabela (maiúsculas contam). Renomeie antes (`df.rename(columns=...)`).
- `insert_list_of_dicts`: todos os dicionários com as mesmas chaves. Retorna `(linhas, nomes)` com
  `id_columns`; com `[]`, o número de linhas.
- `read_sql_to_df` passa por CSV: datas chegam como texto (`pd.to_datetime` depois) e códigos
  numéricos precisam de `dtypes={"col": str}` para manter zeros à esquerda.
- `autocommit=True` (padrão) confirma cada comando. Para uma transação única, use
  `Database(autocommit=False)` e chame `db.commit()`.
- Erros de conexão são levantados no construtor (`psycopg2.OperationalError`); trate-os ali.
- Regras de um domínio (tabelas, consultas próprias) vão numa subclasse de `Database` no projeto,
  não em funções soltas.

## WebDriver + Download

```python
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from acs_toolbox.download import Download
from acs_toolbox.webdriver import WebDriver

pasta = r"C:\dados\baixados"
with WebDriver(downloads_path=pasta, roda_silencioso=True) as wd:
    wd.driver.get("https://exemplo.com/relatorios")
    inicio = time.time()                      # antes do clique!
    wd.wait.until(EC.element_to_be_clickable((By.ID, "exportar"))).click()
    dl = Download(path=pasta)
    arquivo = dl.wait_the_download(start_time=inicio, wait_time=300)
    destino = dl.rename_file("relatorio_setembro", old_file_name=arquivo)  # mantém a extensão
```

- Passe a **mesma pasta** ao `WebDriver` e ao `Download`.
- Marque `start_time` antes de disparar o download; sem ele, um arquivo antigo da pasta pode ser
  aceito. `wait_the_download` levanta `TimeoutError` se não terminar.
- `wd.driver` é o Selenium puro; `wd.wait` é um `WebDriverWait` com `tempo_espera` segundos.
- Por padrão o Chrome valida certificados. Só para intranet com certificado inválido use
  `ignora_erros_certificado=True`; para sites HTTP internos, `dominios_seguros=["http://..."]`.
- Use `roda_silencioso=False` para ver o navegador ao depurar.
- Fluxos de um site específico (login, navegação) ficam numa subclasse de `WebDriver`.

## Progress

```python
from acs_toolbox.progress import Progress

prog = Progress(len(itens), same_line=True, texto_inicial="Processando: ")
for item in itens:
    processar(item)
    prog.next()
```

`Progress` não é iterável: crie com o total (inteiro > 0) e chame `next()` uma vez por item.
`esperar_em_horario_comercial=True` pausa a cada item (2 s em horário comercial, 0 s fora) para
não sobrecarregar sistemas de terceiros; `start()` reinicia o relógio após uma etapa inicial lenta.

## segredos

```python
from acs_toolbox.segredos import get_secret, get_secrets, load_env

token = get_secret("API_TOKEN")
smtp = get_secrets("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
debug = get_secret("DEBUG", default="0")
```

- Todos os segredos ficam num único segredo JSON no Google Secret Manager. Configure
  `ACS_TOOLBOX_GCP_PROJECT` (e, se não for o padrão `acs-toolbox-secrets`, `ACS_TOOLBOX_SECRET_NAME`);
  localmente, `gcloud auth application-default login`.
- Variável de ambiente com o nome da chave tem precedência — é assim que se testa e roda em CI sem
  acessar o cofre.
- `load_env(...)` copia para `os.environ` quando o código existente usa `os.getenv`.
- Chave ausente → `SecretNotFound`; cofre não configurado → `SecretsNotConfigured` (a menos que haja
  `default`). Nunca imprima nem logue os valores.

## Migração de código antigo (versões internas anteriores à 0.1.0)

Ao encontrar código escrito para versões internas, ajuste:

| Antes | Agora |
|---|---|
| `from acs_toolbox.secrets import ...` | `from acs_toolbox.segredos import ...` |
| `WebDriver` ignorava erros de certificado | passe `ignora_erros_certificado=True` se precisar |
| `wd.header` (User-Agent fixo) | `WebDriver(user_agent="...")` |
| `db.insert_dict(column_name=..., dict=...)` | `db.insert_dict(table_name=..., data=...)` |
| `Database()` imprimia a falha e seguia | a exceção é levantada no construtor |
| `check_newer_file()` devolvia `False` | devolve `None` |
| `Progress(...)` com `max` inválido: `Exception` | `ValueError` |
| caminho padrão fixo para o `.ini` | defina `ACS_TOOLBOX_DB_CONFIG` ou use o cofre |
