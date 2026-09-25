# Referência técnica do acs-toolbox

Classes e funções de uso geral: `Database`, `Download`, `Progress`, `WebDriver` e o módulo `segredos`.
Todos ficam em submódulos (`acs_toolbox.database`, etc.), carregados sob demanda. Importar um
submódulo sem o extra correspondente gera `ImportError` com o comando de instalação.

| Módulo | Extra | Para quê |
|---|---|---|
| `acs_toolbox.database` | `database` | PostgreSQL: consultas, inserções em lote, upsert de DataFrame, leitura massiva |
| `acs_toolbox.download` | (núcleo) | Esperar/validar/renomear arquivos baixados pelo navegador |
| `acs_toolbox.progress` | (núcleo; `notebook` opcional) | Progresso com estimativa de término e pausas em horário comercial |
| `acs_toolbox.webdriver` | `webdriver` | Chrome via Selenium já configurado para downloads |
| `acs_toolbox.segredos` | `gcp` | Segredos no Google Secret Manager (um único JSON) |

Instalação: `uv add "acs-toolbox[all]"` (ou `pip install "acs-toolbox[all]"`); escolha só os extras
necessários, ex. `acs-toolbox[database,webdriver]`.

---

## 1. `Database` (`acs_toolbox.database`, extra `database`)

Gerencia conexões e operações PostgreSQL com `psycopg2`. Ao ser importado, registra adaptadores
para os tipos do `numpy` (inteiros, floats, `bool_` e `ndarray`): os valores são convertidos para
o tipo Python equivalente e escapados pelo `psycopg2` (`NaN` vira `'NaN'::float`; um `ndarray`
vira uma tupla, útil em `WHERE id IN %s`). Não configura o `logging` da aplicação: emite erros no
logger `acs_toolbox.database` (só a mensagem; o SQL com valores vai para o nível `DEBUG`).

### 1.1. Exemplo rápido

```python
from acs_toolbox.database import Database

with Database() as db:                       # usa .ini, $ACS_TOOLBOX_DB_CONFIG ou o cofre
    linhas, colunas = db.query("SELECT id, nome FROM clientes WHERE uf = %s", "SP")
    db.execute("UPDATE clientes SET ativo = %s WHERE id = %s", (True, 42))
    db.insert_list_of_dicts("clientes", [{"id": 1, "nome": "Ana"}], id_columns=["id"])
```

### 1.2. Inicialização

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
* **`autocommit`** (bool): commit automático após cada comando e consulta. Com `False`, chame
  `commit()` você mesmo (dentro de `with`, o que não foi confirmado é descartado ao sair).

A conexão é aberta no construtor; erros de configuração e de conexão são propagados
(ex.: `psycopg2.OperationalError`).

Arquivo `.ini` (não versione; o `.gitignore` do projeto deve ignorar `*.ini`):

```ini
[postgresql]
host = localhost
port = 5432
database = minha_base
user = meu_usuario
password = minha_senha
```

### 1.3. Métodos estáticos

* **`db_engine(config_file, dbparams)` / `engine(config_file, dbparams)`**: URL de conexão
  SQLAlchemy `postgresql+psycopg2://...`, com usuário e senha codificados para URL (use com
  `create_engine(Database.db_engine())`, sem instanciar `Database`). Aceita `database` ou `dbname`.
* **`config_db_connection(config_file, section, dbparams)`**: devolve os parâmetros como dicionário.
  `FileNotFoundError` se o `.ini` não existir ou nenhuma fonte estiver configurada, `ValueError`
  se faltar a seção, `TypeError` se `dbparams` não for dicionário.

### 1.4. Conexão e transações

* Suporta `with Database() as db:` (commit se `autocommit`; `rollback` em exceções; sempre fecha a
  conexão própria).
* **`open()`**, **`commit()`**, **`rollback()`**, **`close(commit=True)`**.

### 1.5. Operações SQL

* **`execute(sql, params=None)`**: DML/DDL; retorna `rowcount`. Em erro, faz rollback, loga e relança.
* **`query(sql, params=None, many=True)`**: retorna `(linhas, nomes_colunas)`; com `many=False`,
  `linhas` é uma única tupla (ou None).
* Parâmetros usam `%s` (ou `%(nome)s` com dicionário). Um parâmetro único (`str`, `int`, `date`,
  `Decimal`...) pode ser passado sem lista. Com parâmetros, um `%` literal no SQL deve ser `%%`
  (ex.: `LIKE 'abc%%'`).
* `sql` também aceita objetos `psycopg2.sql.Composed`.
* **`fetchall()` / `fetchone()`**.
* **`check_if_table_exists(table_name, schema='public')`**: consulta `information_schema`
  (aceita também `schema.tabela`).

### 1.6. Inserções e upserts

Nomes de tabelas e colunas são escapados. Nomes simples (letras, dígitos, `_`) seguem sem aspas,
como o PostgreSQL faz (`Nome` equivale a `nome`); os demais vão entre aspas (`"minha coluna"`).
Tabelas aceitam `schema.tabela`. O `ON CONFLICT` exige uma restrição `PRIMARY KEY` ou `UNIQUE`
nas colunas de conflito.

* **`insert_list_of_dicts(table_name, list_of_dicts, id_columns)`**: insere uma lista de dicionários
  (todos com as mesmas chaves, em qualquer ordem; senão, `ValueError`). Com `id_columns`, faz
  `ON CONFLICT` (atualiza ou ignora, conforme `on_conflict_do_update`) e devolve
  `(linhas_com_as_chaves, nomes)`; linhas ignoradas não aparecem. Com `[]`, devolve o número de
  linhas inseridas. Lista vazia devolve `[]`.
* **`insert_dict(table_name, data, on_conflict=None, on_conflict_do_nothing=False)`**: um registro.
  Os nomes antigos `column_name=` e `dict=` ainda funcionam, com `DeprecationWarning`.
* **`insert_many(sql, params_list, params=None)`**: substitui `{params_list}` no SQL pelas tuplas,
  para SQL escrito à mão:

  ```python
  db.insert_many("INSERT INTO t (a, b) VALUES {params_list} ON CONFLICT DO NOTHING",
                 [(1, "x"), (2, "y")])
  ```

* **`upsert_dataframe(df, table_name, primary_key_col, verbose=True)`**: upsert massivo via tabela
  temporária (removida ao final) e `COPY`. A tabela deve existir, as colunas do DataFrame devem ter
  exatamente os nomes das colunas da tabela (aqui sempre entre aspas: maiúsculas contam) e
  `primary_key_col` deve ter restrição `PRIMARY KEY`/`UNIQUE`. Linhas duplicadas na chave são
  reduzidas à última. Devolve o DataFrame efetivamente enviado.
* **`read_sql_to_df(sql, params=None, dtypes=None)`**: leitura massiva via `COPY ... TO STDOUT` para
  DataFrame (texto vazio e nulo são preservados como `''` e `NaN`). Os tipos são inferidos pelo
  `pandas` a partir de CSV: datas chegam como texto (use
  `pd.to_datetime` depois) e códigos numéricos perdem zeros à esquerda, a menos que se passe
  `dtypes={"codigo": str}`.

Para regras de um domínio específico (tabelas, logs, consultas próprias), herde de `Database`
no seu projeto.

---

## 2. `Download` (`acs_toolbox.download`)

Espera e valida downloads feitos pelo navegador (arquivos `.crdownload`/`.tmp`, travas de I/O).

```python
dl = Download(path=None, wait_to_download=True, verbose=False, time_to_wait_download=120)
```

* `path`: pasta monitorada (padrão: `default_downloads_path()`). Use a mesma pasta configurada no
  navegador.
* `default_downloads_path()` (função do módulo): pasta Downloads do usuário (registro no Windows;
  `~/Downloads` nos demais sistemas ou se o registro falhar).
* `wait_the_download(start_time=None, wait_time=None)`: bloqueia até não haver downloads parciais e
  existir um arquivo modificado depois de `start_time`; devolve o caminho. `TimeoutError` se o tempo
  acabar. Guarde `start_time = time.time()` **antes** de disparar o download, para não aceitar um
  arquivo antigo da pasta.
* `check_download()`: True se surgiu um arquivo novo e completo desde a última verificação
  (`check_curr_files()` ou `check_download()` anterior).
* `check_chrome_temporary_files()`, `check_curr_files()`, `check_newer_file()` (None se não houver
  arquivos).
* `delete_all_temporary_files(start_time=None)`: apaga `.crdownload`; `.tmp` só se modificado depois
  de `start_time` (outros programas também usam `.tmp`).
* `rename_file(new_file_name, old_file_name=None, mantem_extensao=True, preserva_diretorio=False, preserva_nome=False)`:
  move/renomeia (padrão: o arquivo mais recente da pasta) e devolve o novo caminho. Por padrão mantém
  a extensão original; um `new_file_name` sem pasta fica em `path`.

---

## 3. `Progress` (`acs_toolbox.progress`, extra `notebook` opcional)

Acompanhamento de iterações com estimativa de término e pausas opcionais em horário comercial.

```python
from acs_toolbox.progress import Progress

itens = carregar_itens()
prog = Progress(len(itens), same_line=True, texto_inicial="Processando: ")
for item in itens:
    processar(item)
    prog.next()
```

```python
prog = Progress(max=1000, if_clear=False, same_line=False, texto_inicial='', texto_final='',
                esperar_em_horario_comercial=False, tempo_pausa_fora_horario_comercial=0,
                tempo_pausa_horario_comercial=2, verbose=False)
```

* `max` deve ser um inteiro maior que zero (senão, `ValueError`). A criação imprime o horário de início.
* `next(texto_inicial=None, texto_final=None)` registra uma iteração e devolve o texto impresso
  (ou None, quando a porcentagem inteira não mudou); a última chamada imprime o tempo total.
  Chamadas além de `max` são ignoradas. `next(prog)` também funciona, mas `Progress` não é
  iterável: chame `next()` dentro do seu próprio laço.
* `esperar_em_horario_comercial=True` pausa a cada iteração (padrão: 2 s em dias úteis das 8h às
  20h, 0 s fora disso), útil para não sobrecarregar sistemas de terceiros no expediente.
* `start()` reinicia a contagem de tempo (após etapas iniciais lentas); `imprime(...)`,
  `pausa_se_horario_comercial(...)`, `stringify(segundos)` (ex.: `"1h 2m 5s"`).
* `if_clear=True` limpa o terminal (códigos ANSI) e a saída de notebooks; `same_line=True` reescreve
  a mesma linha (no Jupyter, substitui a saída).

---

## 4. `WebDriver` (`acs_toolbox.webdriver`, extra `webdriver`)

Configura o Selenium Chrome (headless opcional, pasta de downloads, origens HTTP confiáveis).

```python
wd = WebDriver(roda_silencioso=True, verbose=False, num_tentativas=10,
               downloads_path=None, tempo_espera=30, dominios_seguros=None,
               ignora_erros_certificado=False, user_agent=None)
```

* **`roda_silencioso`**: headless (sem janela). Use `False` para depurar.
* **`downloads_path`**: pasta onde o Chrome salva os downloads (padrão: pasta Downloads do usuário).
* **`tempo_espera`**: timeout de carregamento de página e do `self.wait`.
* **`dominios_seguros`**: lista de origens tratadas como seguras sem HTTPS, ex.
  `["http://intranet.exemplo.com", "http://outro.exemplo.com"]` (string separada por vírgulas também é aceita).
  Padrão: nenhuma.
* **`ignora_erros_certificado`**: aceita certificados inválidos e conteúdo misto. Desativa a proteção
  contra interceptação; use só em redes internas confiáveis. Padrão: False.
* **`user_agent`**: User-Agent enviado aos sites. Padrão: o do próprio Chrome.
* `verbose`, `num_tentativas`: guardados como atributos para uso em subclasses.
* `get_download_path()`: igual a `acs_toolbox.download.default_downloads_path()`.
* `carrega_driver()`: abre o Chrome e cria `self.driver` e `self.wait` (`WebDriverWait`).
* `sair()`: encerra o driver. `with WebDriver() as wd:` abre e encerra automaticamente.

Fluxo típico com `Download` (baixar um arquivo e renomeá-lo):

```python
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from acs_toolbox.download import Download
from acs_toolbox.webdriver import WebDriver

pasta = r"C:\dados\baixados"
with WebDriver(downloads_path=pasta) as wd:
    wd.driver.get("https://exemplo.com/relatorios")
    inicio = time.time()
    wd.wait.until(EC.element_to_be_clickable((By.ID, "exportar"))).click()
    arquivo = Download(path=pasta).wait_the_download(start_time=inicio)
    final = Download(path=pasta).rename_file("relatorio_2026_09", old_file_name=arquivo)
```

Para regras de um site específico (login, navegação), herde de `WebDriver` no seu projeto.

---

## 5. `segredos` (`acs_toolbox.segredos`, extra `gcp`)

Leitura de segredos de um único segredo JSON no Google Secret Manager.

```python
from acs_toolbox.segredos import get_secret, get_secrets, load_env

token = get_secret("API_TOKEN")
cfg = get_secrets("SMTP_HOST", "SMTP_USER")      # {"SMTP_HOST": ..., "SMTP_USER": ...}
opcional = get_secret("FEATURE_X", default=None)
load_env("API_TOKEN")                            # para código legado que usa os.getenv
```

* `get_secret(chave, default=...)` e `get_secrets(*chaves, default=...)`: variável de ambiente com o mesmo
  nome primeiro; depois o cofre (baixado uma vez por processo, em memória). Chave ausente sem `default`
  levanta `SecretNotFound` com os nomes (nunca valores); cofre não configurado levanta `SecretsNotConfigured`.
* `load_env(*chaves, override=False)`: copia valores de texto para `os.environ`.
* `load_payload(refresh=False)` (devolve uma cópia) / `clear_cache()`: acesso ao conteúdo completo e
  descarte do cache.
* Configuração: `ACS_TOOLBOX_GCP_PROJECT` (obrigatória) e `ACS_TOOLBOX_SECRET_NAME` (padrão `acs-toolbox-secrets`).
  Credenciais: `gcloud auth application-default login` (local) ou a conta de serviço do ambiente.
* Formato do segredo: `{"CHAVE": "valor", "postgresql": {"host": "...", "port": "...", "database": "...", "user": "...", "password": "..."}}`.
  A chave `postgresql` é usada automaticamente por `Database()` quando não há `dbparams` nem `.ini`.
* Um segredo que não seja JSON válido gera `ValueError` sem expor o conteúdo.
* Em testes/CI, defina variáveis de ambiente com os nomes das chaves: o cofre nem é consultado.
