# Referência técnica do acs-toolbox

Classes e funções de uso geral: `Database`, `Download`, `Progress`, `WebDriver`, `Zimbra` e o módulo `segredos`.
Todos ficam em submódulos (`acs_toolbox.database`, etc.), carregados sob demanda. Importar um
submódulo sem o extra correspondente gera `ImportError` com o comando de instalação.

| Módulo | Extra | Para quê |
|---|---|---|
| `acs_toolbox.database` | `database` | PostgreSQL: consultas, inserções em lote, upsert de DataFrame, leitura massiva |
| `acs_toolbox.download` | (núcleo) | Esperar/validar/renomear arquivos baixados pelo navegador |
| `acs_toolbox.progress` | (núcleo; `notebook` opcional) | Progresso com estimativa de término e pausas em horário comercial |
| `acs_toolbox.webdriver` | `webdriver` | Chrome via Selenium já configurado para downloads |
| `acs_toolbox.segredos` | `gcp` | Segredos no Google Secret Manager (um único JSON) |
| `acs_toolbox.zimbra` | (núcleo; `gcp` para cofre) | E-mail institucional Zimbra/CNPq via Exchange ActiveSync (WBXML) |

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

---

## 6. `Zimbra` (`acs_toolbox.zimbra`)

Cliente para leitura, busca e envio de e-mails no Zimbra institucional do CNPq (`webmail.cnpq.br`)
utilizando o protocolo **Exchange ActiveSync (EAS 14.1)** sobre HTTPS/WBXML (100% biblioteca padrão do Python).

### 6.1. Pré-requisitos obrigatórios: VPN do CNPq (`vpn-connect`) e Senha de Aplicativo

1. **Conexão com a VPN (`vpn-connect`) antes do acesso:**
   * O CNPq utiliza **Split-DNS** em `webmail.cnpq.br`:
     * **Fora da VPN (Internet Pública):** resolve para `66.22.29.31` (`radwarecloud.net`). Embora o WAF da Radware permita `POST /Autodiscover/Autodiscover.xml` e `OPTIONS /Microsoft-Server-ActiveSync`, o *Radware Bot Manager* **intercepta qualquer requisição `POST /Microsoft-Server-ActiveSync`** com redirecionamento `HTTP 302 Found` para uma página de Captcha JavaScript (`https://validate.perfdrive.com/...`), impedindo a sincronização de pastas e leitura/envio de mensagens.
     * **Dentro da VPN (ou rede física do CNPq):** resolve diretamente para o IP interno `10.0.5.42` (servidor Zimbra/Nginx em Brasília), sem passar pelo WAF da Radware.
   * Por padrão (`garantir_vpn=True`), `Zimbra()` verifica automaticamente se `webmail.cnpq.br` resolve para a rede interna (`10.0.5.42`) e, caso contrário, tenta acionar o pacote `vpn_connect` (`C:\Projetos\CNPq\importantes\VPN Connect`) automaticamente. Se a VPN não puder ser estabelecida, levanta `ZimbraVPNRequiredError`.
   * Para conectar a VPN manualmente via terminal antes de rodar scripts:
     ```powershell
     uv run --project "C:\Projetos\CNPq\importantes\VPN Connect" python -m vpn_connect.cli
     ```
2. **Senha de Aplicativo do Zimbra (`ZIMBRA_APP_PASSWORD`) e Formato do Login:**
   * Contas com 2FA ativo no Zimbra recusam a senha normal de rede (`SENHA_WINDOWS`) em protocolos não interativos (`401 Unauthorized`). É obrigatório gerar uma **Senha de Aplicativo de 16 letras** no webmail (*Preferências $\rightarrow$ Contas $\rightarrow$ Códigos de Aplicativo / Application Passcodes*) e salvá-la no cofre `acs_toolbox.segredos` na chave `ZIMBRA_APP_PASSWORD`.
   * **Domínio e Login:** O domínio deve ficar **em branco**. São aceitos `alberto.silva@cnpq.br` (recomendado), `albertos@cnpq.br`, `alberto.silva` ou `albertos`. Prefixar `cnpq.lan\` sem `@cnpq.br` (ex.: `cnpq.lan\albertos`) é rejeitado pelo ZeXtras Mobile; `Zimbra()` remove prefixos `dominio\` automaticamente.

### 6.2. Exemplo rápido

```python
from acs_toolbox.zimbra import Zimbra

with Zimbra() as zm:  # garante a VPN ativa e lê ZIMBRA_USER e ZIMBRA_APP_PASSWORD do cofre
    conta = zm.autodiscover()
    print(conta["display_name"], conta["email"])

    # Listar pastas da caixa postal
    for pasta in zm.listar_pastas():
        print(f"[{pasta.id}] {pasta.nome} (pai={pasta.parent_id}, tipo={pasta.tipo})")

    # Ler as 5 mensagens mais recentes da Inbox
    for msg in zm.listar_mensagens(pasta="Inbox", limite=5):
        print(msg.data_recebimento, msg.remetente, "->", msg.assunto)
        print(msg.corpo[:200])

    # Buscar mensagens por termo em pasta específica
    resultados = zm.buscar_mensagens("Chamada", pasta="GT CAs", limite=10)

    # Enviar e-mail via Exchange ActiveSync
    zm.enviar_email(
        para="destinatario@cnpq.br",
        assunto="Relatório automatizado",
        corpo="Segue o resumo processado.",
    )
```

### 6.3. Inicialização e Métodos

```python
zm = Zimbra(
    user=None,
    password=None,
    host="webmail.cnpq.br",
    garantir_vpn=True,
    timeout=15,
    ignora_erros_certificado=True,
)
```

* **Resolução de credenciais:**
  * `user`: argumento `user` $\rightarrow$ `ZIMBRA_USER` $\rightarrow$ `CNPQ_EMAIL` $\rightarrow$ `zimbra["user"]` $\rightarrow$ `CNPQ_USER` $\rightarrow$ `"alberto.silva@cnpq.br"`.
  * `password`: argumento `password` $\rightarrow$ `ZIMBRA_APP_PASSWORD` $\rightarrow$ `ZIMBRA_PASSWORD` $\rightarrow$ `zimbra["password"]` (se ausente, levanta `SecretNotFound(["ZIMBRA_APP_PASSWORD"])`).
* **`verificar_vpn_ativa() -> bool`**: retorna `True` se `webmail.cnpq.br` estiver resolvendo para IP interno ou se `10.0.5.42:443` responder diretamente.
* **`assegurar_vpn() -> None`**: garante a rota interna ativa (acionando `vpn_connect` se necessário) ou levanta `ZimbraVPNRequiredError`.
* **`autodiscover() -> dict[str, str]`**: consulta `POST /Autodiscover/Autodiscover.xml` e devolve `display_name`, `email` e `activesync_url`.
* **`verificar_conexao() -> dict[str, Any]`**: consulta `OPTIONS /Microsoft-Server-ActiveSync` e devolve `conectado`, `servidor_activesync`, `versoes` e `comandos`.
* **`listar_pastas() -> list[PastaZimbra]`**: executa `Cmd=FolderSync` e devolve objetos `PastaZimbra(id, parent_id, nome, tipo)`.
* **`obter_id_pasta(nome: str) -> str`**: resolve o nome da pasta (ex.: `"Inbox"` $\rightarrow$ `"2"`, `"Sent"` $\rightarrow$ `"5"`, `"GT CAs"` $\rightarrow$ `"125890"`) para seu `ServerId`.
* **`listar_mensagens(pasta="Inbox", limite=10, desde="2020-01-01T00:00:00.000Z", texto_busca=None, truncation_size=50000) -> list[MensagemZimbra]`**: executa `Cmd=Search` no store `Mailbox` e devolve objetos `MensagemZimbra(id, pasta_id, assunto, remetente, para, cc, data_recebimento, lida, corpo, tamanho)`.
* **`buscar_mensagens(texto_busca, pasta="Inbox", limite=10, desde="2020-01-01T00:00:00.000Z") -> list[MensagemZimbra]`**: atalho para busca textual.
* **`enviar_email(para, assunto, corpo, cc=None, cco=None, html=False, salvar_itens_enviados=True) -> bool`**: envia e-mail via `Cmd=SendMail` (CodePage 21 `ComposeMail`).
* **Exceções:** `ZimbraError` (base), `ZimbraVPNRequiredError` (bloqueio pelo WAF Radware / VPN desligada) e `ZimbraAuthError` (`HTTP 401/403`).

### 6.4. Configuração de Clientes de E-mail Desktop no PC (Outlook Clássico vs. Thunderbird)

O servidor de correio institucional do CNPq (`webmail.cnpq.br`) utiliza **Zimbra Collaboration Suite com ZeXtras Mobile**, disponibilizando o protocolo **Exchange ActiveSync (EAS)** sobre HTTPS (porta 443). As portas padrão IMAP (143/993) e SMTP (25/465/587) encontram-se bloqueadas na rede interna.

#### 1. Incompatibilidade com o Mozilla Thunderbird
* O Thunderbird possui suporte a IMAP, POP3 e, nas versões recentes, adicionou suporte nativo ao **EWS (Exchange Web Services)**.
* **O CNPq não possui EWS**, apenas **EAS**. Como o Thunderbird não suporta o protocolo EAS para sincronização de mensagens de e-mail (extensões como TbSync sincronizam apenas contatos e calendários), **não é possível configurar a caixa postal do CNPq diretamente no Thunderbird**. A tentativa de conexão como "Microsoft Exchange" falhará com erro de autenticação / 404.

#### 2. Configuração no Outlook Clássico (Procedimento Obrigatório com `MLCFG32.CPL`)
A Microsoft removeu o applet clássico do Painel de Controle e substituiu o assistente de contas do Outlook por uma interface moderna simplificada que **não suporta a configuração manual de contas EAS**, gerando o erro *"Algo deu errado e o Outlook não pôde configurar a sua conta"*.

Para configurar a conta corporativa do CNPq com sucesso no Outlook Clássico:

1. **Abrir o painel clássico de configuração de e-mail**:
   Pressione `Win + R` e execute exatamente:
   ```cmd
   "C:\Program Files\Microsoft Office\root\Office16\MLCFG32.CPL"
   ```
   *(Ou abra `Painel de Controle` $\rightarrow$ exibir por `Ícones grandes` $\rightarrow$ `Email (Microsoft Outlook)`).*

2. **Adicionar a conta pelo assistente clássico**:
   * Clique em **Contas de Email...** e depois em **Novo...**.
   * Selecione **Configuração manual ou tipos de servidor adicionais** e avance.
   * Selecione **Serviço compatível com Exchange ActiveSync** (EAS) e avance.
   * Preencha os campos exatamente como abaixo:
     * **Seu Nome**: `Alberto de Campos e Silva`
     * **Endereço de Email**: `alberto.silva@cnpq.br`
     * **Servidor de Email**: `webmail.cnpq.br`
     * **Nome de Usuário**: `alberto.silva@cnpq.br`
     * **Senha**: sua **Senha de Aplicativo** de 16 caracteres (`ZIMBRA_APP_PASSWORD` gerada no Webmail em *Preferências $\rightarrow$ Contas $\rightarrow$ Códigos de Aplicativo* — a senha normal de rede será recusada devido ao 2FA).
   * Clique em **Avançar** para concluir o teste e fechar o assistente.

3. **Reverter o "Novo Outlook" para o "Outlook Clássico" (se necessário)**:
   Se o Windows estiver redirecionando e abrindo o Novo Outlook compulsoriamente (ou se o link "Voltar para o Outlook clássico" não responder), desative o redirecionamento via PowerShell:
   ```powershell
   Set-ItemProperty -Path "HKCU:\Software\Microsoft\Office\16.0\Outlook\Preferences" -Name "UseNewOutlook" -Value 0
   ```

