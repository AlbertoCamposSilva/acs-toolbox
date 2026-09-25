import datetime
import os
import uuid
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from acs_toolbox.database import Database, _as_params

DSN = os.environ.get("ACS_TOOLBOX_TEST_DSN")


# --- Testes sem banco -------------------------------------------------------

def test_as_params_embrulha_parametro_unico():
    assert _as_params(None) is None
    assert _as_params("a") == ["a"]
    assert _as_params(1) == [1]
    data = datetime.date(2026, 1, 1)
    assert _as_params(data) == [data]
    assert _as_params(Decimal("1.5")) == [Decimal("1.5")]
    assert _as_params((1, 2)) == (1, 2)
    assert _as_params({"a": 1}) == {"a": 1}
    assert _as_params([]) is None


def test_db_engine_codifica_usuario_e_senha():
    url = Database.db_engine(dbparams={
        "user": "us@r", "password": "p@ss:w/rd", "host": "h", "port": "5432", "database": "d"})
    assert url == "postgresql+psycopg2://us%40r:p%40ss%3Aw%2Frd@h:5432/d"
    url = Database.engine(dbparams={"user": "u", "password": "p", "host": "h", "dbname": "d"})
    assert url == "postgresql+psycopg2://u:p@h:5432/d"


def test_config_db_connection_erros(tmp_path):
    with pytest.raises(TypeError):
        Database.config_db_connection(dbparams="host=x")
    ini = tmp_path / "db.ini"
    ini.write_text("[outra]\nhost=h\n")
    with pytest.raises(ValueError, match="postgresql"):
        Database.config_db_connection(config_file=str(ini))


def test_falha_de_conexao_propaga():
    import psycopg2

    with pytest.raises(psycopg2.OperationalError):
        Database(dbparams={"host": "127.0.0.1", "port": "1", "dbname": "x",
                           "user": "x", "password": "x", "connect_timeout": "2"})


# --- Testes de integração (PostgreSQL real) ---------------------------------

integracao = pytest.mark.skipif(not DSN, reason="defina ACS_TOOLBOX_TEST_DSN")


@pytest.fixture
def db():
    import psycopg2

    conn = psycopg2.connect(DSN)
    database = Database(connection=conn)
    schema = f"t_{uuid.uuid4().hex[:8]}"
    database.execute(f"CREATE SCHEMA {schema}")
    database.execute(f"SET search_path TO {schema}")
    database.schema = schema
    yield database
    database.rollback()
    database.execute(f"DROP SCHEMA {schema} CASCADE")
    conn.close()


@integracao
def test_insert_list_of_dicts(db):
    db.execute("CREATE TABLE t (id int PRIMARY KEY, nome text, valor int)")
    linhas = [{"id": 1, "nome": "a", "valor": 10},
              {"valor": 20, "nome": "b", "id": 2}]  # chaves fora de ordem
    rows, cols = db.insert_list_of_dicts("t", linhas, ["id"])
    assert sorted(rows) == [(1,), (2,)] and cols == ["id"]
    assert db.query("SELECT id, nome, valor FROM t ORDER BY id")[0] == [(1, "a", 10), (2, "b", 20)]

    db.insert_list_of_dicts("t", [{"id": 1, "nome": "novo", "valor": 11}], ["id"])
    assert db.query("SELECT nome FROM t WHERE id = 1", many=False)[0] == ("novo",)

    db.on_conflict_do_update = False
    rows, _ = db.insert_list_of_dicts("t", [{"id": 1, "nome": "x", "valor": 0}], ["id"])
    assert rows == []
    assert db.query("SELECT nome FROM t WHERE id = 1", many=False)[0] == ("novo",)

    assert db.insert_list_of_dicts("t", [{"id": 3, "nome": "c", "valor": 1}], []) == 1

    db.on_conflict_do_update = True  # todas as colunas na chave -> DO NOTHING
    db.execute("CREATE TABLE k (a int, b int, PRIMARY KEY (a, b))")
    db.insert_list_of_dicts("k", [{"a": 1, "b": 1}], ["a", "b"])
    db.insert_list_of_dicts("k", [{"a": 1, "b": 1}], ["a", "b"])

    with pytest.raises(ValueError):
        db.insert_list_of_dicts("t", [{"id": 4}, {"id": 5, "nome": "e"}], ["id"])


@integracao
def test_identificadores_sao_escapados(db):
    db.execute('CREATE TABLE "com espaco" ("minha coluna" text, id int PRIMARY KEY)')
    db.insert_list_of_dicts("com espaco", [{"id": 1, "minha coluna": "x"}], ["id"])
    db.insert_dict("com espaco", {"id": 2, "minha coluna": "y"}, on_conflict=["id"])
    assert db.query('SELECT count(*) FROM "com espaco"', many=False)[0] == (2,)
    with pytest.raises(Exception):
        db.insert_dict("t; DROP TABLE x", {"id": 1})


@integracao
def test_insert_dict_e_nomes_antigos(db):
    db.execute("CREATE TABLE t (id int PRIMARY KEY, nome text)")
    db.insert_dict("t", {"id": 1, "nome": "a"}, on_conflict=["id"])
    db.insert_dict("t", {"id": 1, "nome": "b"}, on_conflict=["id"])
    db.insert_dict("t", {"id": 1, "nome": "c"}, on_conflict=["id"], on_conflict_do_nothing=True)
    assert db.query("SELECT nome FROM t", many=False)[0] == ("b",)
    with pytest.deprecated_call():
        db.insert_dict(column_name="t", dict={"id": 2, "nome": "z"})


@integracao
def test_check_if_table_exists_nao_injeta(db):
    db.execute("CREATE TABLE t (id int)")
    assert db.check_if_table_exists("t", schema=db.schema)
    assert db.check_if_table_exists(f"{db.schema}.t")
    assert not db.check_if_table_exists("x'; DROP TABLE t; --", schema=db.schema)
    assert db.check_if_table_exists("t", schema=db.schema)


@integracao
def test_upsert_dataframe(db):
    db.execute('CREATE TABLE t (id int PRIMARY KEY, "Valor Total" numeric, obs text)')
    tabela = f"{db.schema}.t"
    df = pd.DataFrame({"id": [1, 2, 2], "Valor Total": [1.5, 2.5, 3.5], "obs": ["a", None, "c"]})
    out = db.upsert_dataframe(df, tabela, "id", verbose=False)
    assert len(out) == 2
    db.upsert_dataframe(pd.DataFrame({"id": [1], "Valor Total": [9.0], "obs": ["z"]}),
                        tabela, "id", verbose=False)
    rows = db.query('SELECT id, "Valor Total", obs FROM t ORDER BY id')[0]
    assert rows == [(1, Decimal("9.0"), "z"), (2, Decimal("3.5"), "c")]
    assert db.upsert_dataframe(df.iloc[0:0], tabela, "id", verbose=False).empty
    temps = db.query("SELECT count(*) FROM pg_tables WHERE tablename LIKE 'tmp_upsert_%%'",
                     many=False)[0][0]
    assert temps == 0


@integracao
def test_read_sql_to_df_com_ponto_e_virgula(db):
    df = db.read_sql_to_df("SELECT %s::text AS a;\n", ("x",))
    assert df.to_dict("records") == [{"a": "x"}]


@integracao
def test_read_sql_to_df_distingue_texto_vazio_de_nulo(db):
    df = db.read_sql_to_df(
        "SELECT * FROM (VALUES ('', 1), (NULL, 2), ('NA', 3)) AS v(t, n) ORDER BY n",
        dtypes={"t": str})
    assert df["t"].iloc[0] == ""
    assert pd.isna(df["t"].iloc[1])
    assert df["t"].iloc[2] == "NA"  # texto "NA" não vira nulo
    assert list(df["n"]) == [1, 2, 3]


@integracao
def test_adaptadores_numpy(db):
    row = db.query("SELECT %s, %s, %s, %s", (np.float64("nan"), np.int32(7), np.bool_(True),
                                             np.float32(1.5)), many=False)[0]
    assert np.isnan(row[0]) and row[1:] == (7, True, 1.5)
    assert db.query("SELECT 'a' IN %s", (np.array(["a", "b'); --"]),), many=False)[0] == (True,)


@integracao
def test_reabre_com_dbparams_e_fecha_no_with():
    import psycopg2.extensions

    params = psycopg2.extensions.parse_dsn(DSN)
    database = Database(dbparams=params)
    database.close()
    database.open()
    assert database.query("SELECT 1", many=False)[0] == (1,)
    database.close()

    with pytest.raises(RuntimeError):
        with Database(dbparams=params) as d:
            conn = d.connection
            raise RuntimeError
    assert conn.closed
