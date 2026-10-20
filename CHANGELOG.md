# Changelog

## 0.3.0

- `Zimbra`: Suporte completo ao provisionamento ActiveSync (`[MS-ASPROV]`, Code Page 14) com `device_id`
  fixo e estável (ex.: `device_id="MESAALBERTO01"` ou `ZIMBRA_DEVICE_ID`), persistência local de `PolicyKey`
  em `%LOCALAPPDATA%\acs_toolbox\zimbra_provision.json` e envio de `X-MS-PolicyKey` nas requisições.
- `Zimbra`: Auto-recuperação de provisionamento em chamadas subsequentes ao receber `HTTP 449` ou Status
  WBXML `142`, `143` ou `144`.
- `Zimbra`: Validação TLS estrita por padrão (`ignora_erros_certificado=False`) com conexões autenticadas
  pelo nome do host (SNI).
- `Zimbra`: Modo somente leitura (`somente_leitura=True`) que impede o envio de e-mails (`SendMail`).
- Documentação no README e CHANGELOG com instruções de como remover aparelhos móveis antigos acumulados no
  Webmail Zimbra (*Preferências -> Aplicativos e dispositivos móveis*).

## 0.2.0

- Novo módulo `acs_toolbox.zimbra` (`Zimbra`, `PastaZimbra`, `MensagemZimbra`): acesso ao webmail
  institucional do CNPq (`webmail.cnpq.br`) via protocolo Exchange ActiveSync (EAS 14.1 / WBXML) em
  Python puro (`autodiscover`, `verificar_conexao`, `listar_pastas`, `obter_id_pasta`,
  `listar_mensagens`, `buscar_mensagens`, `enviar_email`).
- Verificação automática de Split-DNS/rota interna (`10.0.5.42` vs. WAF Radware `66.22.29.31`) e
  acionamento integrado do `vpn-connect` (`garantir_vpn=True`).

## 0.1.1

- `Database.db_engine()` devolve `postgresql+psycopg2://...`: com SQLAlchemy 2.1+, `postgresql://`
  passou a exigir o driver `psycopg` (v3).
- `read_sql_to_df` distingue texto vazio (`''`) de nulo (`NaN`); antes, `''` virava `NaN`.

## 0.1.0 — primeira versão pública

- `Database` (PostgreSQL/psycopg2), `Download`, `Progress`, `WebDriver` (Selenium/Chrome) e
  `segredos` (Google Secret Manager).
- Extras opcionais: `database`, `webdriver`, `notebook`, `gcp`, `all`.
- Nomes de tabelas e colunas escapados; consultas de metadados parametrizadas.
- `WebDriver` não desativa mais a verificação de certificados por padrão
  (`ignora_erros_certificado=True` para o comportamento antigo).
