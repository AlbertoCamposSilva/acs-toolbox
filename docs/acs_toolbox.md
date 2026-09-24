# Referência técnica do acs-toolbox

Classes e funções de uso geral: `Database`, `Download`, `Progress`, `WebDriver` e o módulo `segredos`.
Todos ficam em submódulos (`acs_toolbox.database`, etc.), carregados sob demanda. Importar um
submódulo sem o extra correspondente gera `ImportError` com o comando de instalação.

---

## 1. `Database` (`acs_toolbox.database`, extra `database`)

Gerencia conexões e operações PostgreSQL com `psycopg2`. Ao ser importado, registra adaptadores
para os tipos do `numpy` (inteiros, floats, `bool_` e `ndarray`): os valores são convertidos para
o tipo Python equivalente e escapados pelo `psycopg2` (`NaN` vira `'NaN'::float`; um `ndarray`
vira uma tupla, útil em `WHERE id IN %s`). Não configura o `logging` da aplicação: emite erros no
logger `acs_toolbox.database` (só a mensagem; o SQL com valores vai para o nível `DEBUG`).

### 1.1. Inicialização

```python
db = Database(
    show_sql=False,
    on_conflict_do_update=True,
    config_file=None,
    dbparams=None,
    connection=None,
    autocommit=True,
)
```

* **`show_sql`** (bool): imprime as queries SQL no console (com os valores).
* **`on_conflict_do_update`** (bool): comportamento padrão em conflito de chaves nas inserções em lote.
* **`config_file`** (str, opcional): caminho do `.ini` (seção `[postgresql]`). Se omitido, usa
  `$ACS_TOOLBOX_DB_CONFIG` e, se essa também não existir, o segredo `postgresql` do cofre (seção 5).
* **`dbparams`** (dict, opcional): parâmetros de conexão diretos; substitui o `.ini` e o cofre.
  Também é usado ao reabrir a conexão com `open()`.
* **`connection`** (objeto, opcional): conexão `psycopg2` já existente (ex.: pool). Não é fechada
  pelo `Database`.
* **`autocommit`** (bool): commit automático após cada comando e consulta.

Erros de configuração e de conexão são propagados (ex.: `psycopg2.OperationalError`).

### 1.2. Métodos estáticos

* **`db_engine(config_file, dbparams)` / `engine(config_file, dbparams)`**: string de conexão
  SQLAlchemy, com usuário e senha codificados para URL. Aceita `database` ou `dbname`.
* **`config_db_connection(config_file, section, dbparams)`**: devolve os parâmetros como dicionário.
  `FileNotFoundError` se o `.ini` não existir, `ValueError` se faltar a seção, `TypeError` se
  `dbparams` não for dicionário.

### 1.3. Conexão e transações

* Suporta `with Database() as db:` (commit se `autocommit`; `rollback` em exceções; sempre fecha a
  conexão própria).
* **`open()`**, **`commit()`**, **`rollback()`**, **`close(commit=True)`**.

### 1.4. Operações SQL

* **`execute(sql, params=None)`**: DML/DDL; retorna `rowcount`. Em erro, faz rollback, loga e relança.
* **`query(sql, params=None, many=True)`**: retorna `(linhas, nomes_colunas)`.
* Um parâmetro único (`str`, `int`, `date`, `Decimal`...) pode ser passado sem lista.
* **`fetchall()` / `fetchone()`**.
* **`check_if_table_exists(table_name, schema='public')`**: consulta `information_schema`
  (aceita também `schema.tabela`).

### 1.5. Inserções e upserts

Nomes de tabelas e colunas são escapados. Nomes simples (letras, dígitos, `_`) seguem sem aspas,
como o PostgreSQL faz (`Nome` equivale a `nome`); os demais vão entre aspas (`"minha coluna"`).
Tabelas aceitam `schema.tabela`.

* **`insert_many(sql, params_list, params=None)`**: substitui `{params_list}` no SQL pelas tuplas.
* **`insert_list_of_dicts(table_name, list_of_dicts, id_columns)`**: insere uma lista de dicionários
  (todos com as mesmas chaves, em qualquer ordem). Com `id_columns`, faz `ON CONFLICT` (atualiza ou
  ignora, conforme `on_conflict_do_update`) e devolve as chaves; com `[]`, devolve o número de linhas.
* **`insert_dict(table_name, data, on_conflict=None, on_conflict_do_nothing=False)`**. Os nomes antigos
  `column_name=` e `dict=` ainda funcionam, com `DeprecationWarning`.
* **`upsert_dataframe(df, table_name, primary_key_col, verbose=True)`**: upsert massivo via tabela
  temporária (removida ao final) e `COPY`.
* **`read_sql_to_df(sql, params=None, dtypes=None)`**: leitura massiva via `COPY ... TO STDOUT` para
  DataFrame. Use `dtypes` para preservar identificadores numéricos longos como texto.

Para regras de um domínio específico (tabelas, logs, consultas próprias), herde de `Database`
no seu projeto.

---

## 2. `Download` (`acs_toolbox.download`)

Espera e valida downloads feitos pelo navegador (arquivos `.crdownload`/`.tmp`, travas de I/O).

```python
dl = Download(path=None, wait_to_download=True, verbose=False, time_to_wait_download=120)
```

* `default_downloads_path()` (função do módulo): pasta Downloads do usuário (registro no Windows;
  `~/Downloads` nos demais sistemas ou se o registro falhar).
* `wait_the_download(start_time=None, wait_time=None)`: bloqueia até o download terminar e devolve
  o caminho; `TimeoutError` se o tempo acabar.
* `check_download()`: True se surgiu um arquivo novo e completo desde a última verificação.
* `check_chrome_temporary_files()`, `check_curr_files()`, `check_newer_file()` (None se não houver
  arquivos).
* `delete_all_temporary_files(start_time=None)`: apaga `.crdownload`; `.tmp` só se modificado depois
  de `start_time` (outros programas também usam `.tmp`).
* `rename_file(new_file_name, old_file_name=None, mantem_extensao=True, preserva_diretorio=False, preserva_nome=False)`.

---

## 3. `Progress` (`acs_toolbox.progress`, extra `notebook` opcional)

Acompanhamento de iterações com estimativa de término e pausas opcionais em horário comercial.

```python
prog = Progress(max=1000, if_clear=False, same_line=False, texto_inicial='', texto_final='',
                esperar_em_horario_comercial=False, tempo_pausa_fora_horario_comercial=0,
                tempo_pausa_horario_comercial=2, verbose=False)
```

* `max` deve ser um inteiro maior que zero (senão, `ValueError`).
* `next(...)` registra uma iteração e devolve o texto impresso (ou None); chamadas além de `max`
  são ignoradas. `next(prog)` também funciona.
* `start()`, `imprime(...)`, `pausa_se_horario_comercial(...)`, `stringify(segundos)`.
* `if_clear=True` limpa o terminal (códigos ANSI) e a saída de notebooks.

---

## 4. `WebDriver` (`acs_toolbox.webdriver`, extra `webdriver`)

Configura o Selenium Chrome (headless opcional, pasta de downloads, origens HTTP confiáveis).

```python
wd = WebDriver(roda_silencioso=True, verbose=False, num_tentativas=10,
               downloads_path=None, tempo_espera=30, dominios_seguros=None,
               ignora_erros_certificado=False, user_agent=None)
```

* **`dominios_seguros`**: lista de origens tratadas como seguras sem HTTPS, ex.
  `["http://intranet.exemplo.com", "http://outro.exemplo.com"]` (string separada por vírgulas também é aceita).
  Padrão: nenhuma.
* **`ignora_erros_certificado`**: aceita certificados inválidos e conteúdo misto. Desativa a proteção
  contra interceptação; use só em redes internas confiáveis. Padrão: False.
* **`user_agent`**: User-Agent enviado aos sites. Padrão: o do próprio Chrome.
* `get_download_path()`: igual a `acs_toolbox.download.default_downloads_path()`.
* `carrega_driver()`: abre o Chrome e cria `self.driver` e `self.wait` (`WebDriverWait`).
* `sair()`: encerra o driver. `with WebDriver() as wd:` abre e encerra automaticamente.

---

## 5. `segredos` (`acs_toolbox.segredos`, extra `gcp`)

Leitura de segredos de um único segredo JSON no Google Secret Manager.

* `get_secret(chave, default=...)` e `get_secrets(*chaves, default=...)`: variável de ambiente com o mesmo
  nome primeiro; depois o cofre (baixado uma vez por processo, em memória). Chave ausente sem `default`
  levanta `SecretNotFound` com os nomes (nunca valores); cofre não configurado levanta `SecretsNotConfigured`.
* `load_env(*chaves, override=False)`: copia valores de texto para `os.environ`.
* `load_payload(refresh=False)` (devolve uma cópia) / `clear_cache()`: acesso ao conteúdo completo e
  descarte do cache.
* Configuração: `ACS_TOOLBOX_GCP_PROJECT` (obrigatória) e `ACS_TOOLBOX_SECRET_NAME` (padrão `acs-toolbox-secrets`).
* Formato do segredo: `{"CHAVE": "valor", "postgresql": {"host": "...", "port": "...", "database": "...", "user": "...", "password": "..."}}`.
* Um segredo que não seja JSON válido gera `ValueError` sem expor o conteúdo.
