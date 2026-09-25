# Changelog

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
