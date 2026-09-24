# Changelog

## 0.1.0 — primeira versão pública

- `Database` (PostgreSQL/psycopg2), `Download`, `Progress`, `WebDriver` (Selenium/Chrome) e
  `segredos` (Google Secret Manager).
- Extras opcionais: `database`, `webdriver`, `notebook`, `gcp`, `all`.
- Nomes de tabelas e colunas escapados; consultas de metadados parametrizadas.
- `WebDriver` não desativa mais a verificação de certificados por padrão
  (`ignora_erros_certificado=True` para o comportamento antigo).
