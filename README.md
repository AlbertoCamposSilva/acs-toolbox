# acs-toolbox

Utilitários de uso geral para automação, banco de dados PostgreSQL, downloads, progresso, segredos e e-mail institucional (Zimbra / Exchange ActiveSync).
Referência completa das classes: [docs/acs_toolbox.md](https://github.com/AlbertoCamposSilva/acs-toolbox/blob/main/docs/acs_toolbox.md).

## Instalação (uv)

Em outro projeto gerenciado por uv:

```bash
uv add acs-toolbox                    # núcleo (Download, Progress, Zimbra)
uv add "acs-toolbox[database]"        # + Database (psycopg2, pandas, numpy)
uv add "acs-toolbox[webdriver]"       # + WebDriver (selenium)
uv add "acs-toolbox[gcp]"             # + segredos (Google Secret Manager)
uv add "acs-toolbox[all]"             # tudo
```

Com pip: `pip install "acs-toolbox[all]"`.

Como dependência de um `pyproject.toml`:

```toml
dependencies = ["acs-toolbox[database,webdriver]>=0.2"]
```

## Extras

| Extra       | Habilita                | Dependências                        |
|-------------|-------------------------|-------------------------------------|
| (núcleo)    | `Download`, `Progress`, `Zimbra` | nenhuma (usa stdlib; `Zimbra` lê o cofre se `gcp` estiver configurado) |
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

## E-mail Institucional Zimbra / Exchange ActiveSync (`acs_toolbox.zimbra`)

A classe `Zimbra` acessa o servidor `webmail.cnpq.br` via protocolo **Exchange ActiveSync (EAS 14.1 / WBXML)**:

```python
from acs_toolbox.zimbra import Zimbra

# Uso com DeviceId fixo e modo somente leitura
with Zimbra(device_id="MESAALBERTO01", somente_leitura=True) as zm:
    pastas = zm.listar_pastas()
    mensagens = zm.listar_mensagens("Inbox", limite=5)
    for m in mensagens:
        print(m.data_recebimento, m.remetente, m.assunto)
```

- **DeviceId Fixo e Provisionamento ([MS-ASPROV]):** Por padrão, informe sempre um `device_id` estável (ex.: `device_id="MESAALBERTO01"` ou variável `ZIMBRA_DEVICE_ID`). O cliente executa o handshake de provisionamento em 2 fases (`Cmd=Provision`), armazena o `PolicyKey` em cache local (`%LOCALAPPDATA%\acs_toolbox\zimbra_provision.json`) e o envia no cabeçalho `X-MS-PolicyKey`, permitindo múltiplas chamadas consecutivas estáveis sem criar dezenas de aparelhos no Zimbra.
- **Como limpar aparelhos antigos acumulados no Webmail Zimbra:**
  1. Acesse o webmail institucional em `https://webmail.cnpq.br`.
  2. Vá em **Preferências** $\rightarrow$ **Aplicativos e dispositivos móveis**.
  3. Localize na tabela de dispositivos móveis os aparelhos antigos gerados anteriormente (com identificadores aleatórios como `AGY...`) e clique em **Remover** / **Excluir**.
  4. Mantenha apenas o aparelho fixo configurado na sua aplicação (ex.: `MESAALBERTO01`) e os seus dispositivos móveis pessoais (celular/tablet).
- **Modo Somente Leitura (`somente_leitura=True`):** Impede qualquer envio acidental de e-mails via `enviar_email()` / `Cmd=SendMail`, levantando `ZimbraError`.
- **Validação TLS por Padrão (`ignora_erros_certificado=False`):** As conexões HTTPS utilizam o hostname `webmail.cnpq.br` com SNI e verificação criptográfica estrita do certificado digital emitido para o CNPq.
- **Necessidade obrigatória de VPN (`vpn-connect`):** Fora da rede do CNPq, `webmail.cnpq.br` resolve por Split-DNS para o WAF da Radware (`66.22.29.31`), cujo *Bot Manager* intercepta requisições `POST /Microsoft-Server-ActiveSync` e redireciona (`302 Found`) para uma página de Captcha JavaScript (`validate.perfdrive.com`). Com a VPN conectada, `webmail.cnpq.br` resolve diretamente para o IP interno `10.0.5.42`. Por padrão (`garantir_vpn=True`), `Zimbra()` verifica a rota interna e aciona automaticamente o pacote `vpn-connect` (`C:\Projetos\CNPq\importantes\VPN Connect`) se necessário.
- **Senha de Aplicativo (`ZIMBRA_APP_PASSWORD`):** Contas com 2FA ativo no Zimbra exigem uma Senha de Aplicativo de 16 letras gerada no webmail (*Preferências $\rightarrow$ Contas $\rightarrow$ Códigos de Aplicativo*), lida de `ZIMBRA_APP_PASSWORD` no cofre `acs_toolbox.segredos`. O login deve usar domínio em branco (ex.: `alberto.silva@cnpq.br` ou `albertos`).

## Skill para o Claude Code

A pasta [skills/acs-toolbox](https://github.com/AlbertoCamposSilva/acs-toolbox/tree/main/skills/acs-toolbox)
contém uma skill que ensina o Claude Code a usar esta biblioteca. Para usá-la em todos os projetos,
copie a pasta para `~/.claude/skills/acs-toolbox/` (ou para `.claude/skills/acs-toolbox/` de um projeto).

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
