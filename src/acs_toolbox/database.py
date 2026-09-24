"""
Conexão e operações PostgreSQL com ``psycopg2`` (extra ``database``).

Ao ser importado, registra adaptadores para os tipos escalares e arrays do
``numpy``, para que possam ser passados diretamente como parâmetros SQL.
"""
from __future__ import annotations

import io
import logging
import os
import re
import uuid
import warnings
from collections.abc import Mapping, Sequence
from configparser import ConfigParser
from typing import Any
from urllib.parse import quote

try:
    import numpy as np
    import pandas as pd
    import psycopg2
    from psycopg2 import sql as pgsql
    from psycopg2.extensions import adapt, register_adapter
except ImportError as e:  # pragma: no cover - depende do extra
    raise ImportError(
        'Instale o extra "database": uv add "acs-toolbox[database]"') from e

# Biblioteca: não configura o logging da aplicação (isso cabe a quem a usa).
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# Adaptadores numpy -> psycopg2. Convertem para o tipo Python equivalente e
# delegam a ``adapt``, que faz o escape correto (strings entre aspas, NaN etc.).
def _adapt_numpy_float(value):
    return adapt(float(value))


def _adapt_numpy_int(value):
    return adapt(int(value))


def _adapt_numpy_bool(value):
    return adapt(bool(value))


def _adapt_numpy_array(value):
    # Tupla, como antes: permite ``WHERE id IN %s`` com um ndarray.
    return adapt(tuple(value.tolist()))


for _float_type in (np.float16, np.float32, np.float64):
    register_adapter(_float_type, _adapt_numpy_float)
for _int_type in (np.int8, np.int16, np.int32, np.int64,
                  np.uint8, np.uint16, np.uint32, np.uint64):
    register_adapter(_int_type, _adapt_numpy_int)
register_adapter(np.bool_, _adapt_numpy_bool)
register_adapter(np.ndarray, _adapt_numpy_array)


#: Variável de ambiente que aponta para o arquivo .ini de conexão.
CONFIG_ENV_VAR = 'ACS_TOOLBOX_DB_CONFIG'

_SIMPLE_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')


def default_config_file() -> str | None:
    """Arquivo .ini indicado por ``$ACS_TOOLBOX_DB_CONFIG`` (ou None)."""
    return os.environ.get(CONFIG_ENV_VAR) or None


def _params_from_secret(section: str) -> dict[str, str]:
    """Parâmetros de conexão do segredo ``section`` (ver ``acs_toolbox.segredos``)."""
    from acs_toolbox.segredos import get_secret

    params = get_secret(section, default=None)
    if not isinstance(params, dict):
        raise FileNotFoundError(
            'Configuração do banco não encontrada. Passe dbparams=... ou '
            f'config_file=..., defina {CONFIG_ENV_VAR} (arquivo .ini) ou '
            f'configure o cofre de segredos (chave "{section}", ver acs_toolbox.segredos).')
    return {k: str(v) for k, v in params.items()}


def _name(name: str) -> pgsql.Composable:
    """
    Identificador SQL (coluna ou parte de um nome de tabela).

    Nomes simples (letras, dígitos e ``_``) seguem sem aspas, como o PostgreSQL
    os trata normalmente (``Nome`` vira ``nome``). Os demais vão entre aspas, o
    que impede injeção de SQL pelo nome.
    """
    if _SIMPLE_IDENTIFIER.match(name):
        return pgsql.SQL(name)
    return pgsql.Identifier(name)


def _table(name: str) -> pgsql.Composable:
    """Nome de tabela, aceitando ``schema.tabela``."""
    return pgsql.SQL('.').join(_name(part) for part in name.split('.'))


def _as_params(params: Any) -> Any:
    """Embrulha um parâmetro único (str, int, date, Decimal...) numa lista."""
    if params is None:
        return None
    if isinstance(params, (str, bytes)) or not isinstance(params, (Sequence, Mapping)):
        return [params]
    return params or None


class Database:
    def __init__(self,
                 show_sql: bool = False,
                 on_conflict_do_update: bool = True,
                 config_file: str | None = None,
                 dbparams: Mapping[str, Any] | None = None,
                 connection: Any = None,
                 autocommit: bool = True) -> None:
        """
        Abre a conexão com o banco (ou adota ``connection``, já existente).

        Erros de configuração ou de conexão são propagados ao chamador.
        """
        self.conn: Any = None
        self.cur: Any = None
        self.connected = False
        self.config_file = config_file or default_config_file()
        self.dbparams = dbparams
        self.on_conflict_do_update = on_conflict_do_update
        self.show_sql = show_sql
        self.autocommit = autocommit
        self.is_external_connection = connection is not None

        if connection is not None:
            self.conn = connection
            self.cur = self.conn.cursor()
        else:
            self.params = self.__class__.config_db_connection(
                config_file=self.config_file, dbparams=dbparams)
            self.conn = psycopg2.connect(**self.params)
            self.cur = self.conn.cursor()
            self.conn.rollback()  # Limpa estado inicial
        self.connected = True

    @staticmethod
    def db_engine(config_file: str | None = None,
                  dbparams: Mapping[str, Any] | None = None) -> str:
        """
        Cria a string de conexão para o SQLAlchemy engine.

        Args:
            config_file (str): Caminho do arquivo de configuração.
            dbparams (dict, optional): Dicionário com parâmetros de conexão.

        Returns:
            str: String de conexão PostgreSQL (usuário e senha já codificados para URL).
        """
        params = Database.config_db_connection(config_file=config_file, dbparams=dbparams)
        username = quote(str(params['user']), safe='')
        password = quote(str(params.get('password', '')), safe='')
        host = params['host']
        port = int(params.get('port', 5432))
        dbname = params.get('database') or params['dbname']
        return f'postgresql://{username}:{password}@{host}:{port}/{dbname}'

    @staticmethod
    def engine(config_file: str | None = None,
               dbparams: Mapping[str, Any] | None = None) -> str:
        """
        Retorna a string de conexão SQLAlchemy (alias para db_engine).
        """
        return Database.db_engine(config_file=config_file, dbparams=dbparams)

    @staticmethod
    def config_db_connection(config_file: str | None = None,
                             section: str = 'postgresql',
                             dbparams: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """
        Obtém os parâmetros de conexão, nesta ordem: dicionário ``dbparams``,
        arquivo INI (``config_file`` ou ``$ACS_TOOLBOX_DB_CONFIG``) e, por fim,
        o segredo ``section`` do cofre (``acs_toolbox.segredos``).
        """
        if dbparams is not None:
            if not isinstance(dbparams, Mapping):
                raise TypeError('dbparams deve ser um dicionário ou None.')
            return dict(dbparams)
        config_file = config_file or default_config_file()
        if not config_file:
            return _params_from_secret(section)
        if not os.path.isfile(config_file):
            raise FileNotFoundError(
                f'Arquivo de configuração do banco não encontrado: {config_file}.')
        parser = ConfigParser()
        parser.read(config_file, 'UTF-8')
        if not parser.has_section(section):
            raise ValueError(
                f'Seção [{section}] não encontrada no arquivo {config_file}.')
        return dict(parser.items(section))

    def __enter__(self) -> Database:
        self.open()  # Certifica-se de que a conexão foi estabelecida
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is not None:
                self.rollback()
            elif self.autocommit:
                self.commit()
        finally:
            # Se a conexão veio de fora (pool), não fechamos aqui.
            if not self.is_external_connection:
                self.close(commit=False)

    @property
    def connection(self) -> Any:
        return self.conn

    @property
    def cursor(self) -> Any:
        return self.cur

    def open(self) -> tuple[Any, Any]:
        """
        Abre a conexão com o banco de dados se estiver fechada.
        """
        if not self.connected:
            if self.conn is None or self.conn.closed:
                if self.is_external_connection:
                    raise psycopg2.InterfaceError(
                        'A conexão externa foi liberada; crie um Database com uma nova conexão.')
                self.params = self.__class__.config_db_connection(
                    config_file=self.config_file, dbparams=self.dbparams)
                self.conn = psycopg2.connect(**self.params)
            self.cur = self.conn.cursor()
            self.connected = True
        return self.connection, self.cursor

    def commit(self) -> None:
        """
        Realiza commit na transação atual.
        """
        self.connection.commit()

    def rollback(self) -> None:
        """
        Realiza rollback na transação atual.
        """
        if self.conn is not None and not self.conn.closed:
            self.conn.rollback()

    def close(self, commit: bool = True) -> None:
        # Se é conexão externa, apenas limpamos a referência interna
        if self.is_external_connection:
            self.connected = False
            self.conn = None
            self.cur = None
            return

        if self.conn is not None and not self.conn.closed:
            try:
                if commit:
                    self.conn.commit()
            finally:
                if self.cur is not None and not self.cur.closed:
                    self.cur.close()
                self.conn.close()
        self.connected = False

    def _log_error(self, context: str, error: Exception, sql_text: bytes | str | None) -> None:
        # Só a primeira linha da mensagem vai para o nível ERROR; o SQL (que pode
        # conter dados pessoais já interpolados) só em DEBUG.
        first_line = (str(error).splitlines() or [''])[0]
        logger.error('%s: %s: %s', context, type(error).__name__, first_line)
        if sql_text is not None:
            if isinstance(sql_text, bytes):
                sql_text = sql_text.decode('utf-8', 'replace')
            logger.debug('SQL com erro: %s', sql_text[:500])

    def _mogrify(self, query: Any, params: Any = None) -> bytes:
        sql_to_execute = self.cursor.mogrify(query, _as_params(params))
        if self.show_sql:
            print(sql_to_execute.decode())
        return sql_to_execute

    def execute(self, sql: Any, params: Any = None) -> int:
        """Executa um comando (DML/DDL) e devolve ``rowcount``."""
        if not self.connected:
            raise psycopg2.InterfaceError("A conexão com o banco de dados não está aberta.")
        sql_to_execute = self._mogrify(sql, params)
        try:
            self.cursor.execute(sql_to_execute)
            resultado = self.cursor.rowcount
            if self.autocommit:
                self.commit()
            return resultado
        except Exception as error:
            self.rollback()
            self._log_error('Erro na execução do SQL', error, sql_to_execute)
            raise

    def fetchall(self) -> list[tuple]:
        """
        Retorna todas as linhas do último resultado.
        """
        return self.cursor.fetchall()

    def fetchone(self) -> tuple | None:
        """
        Retorna a próxima linha do último resultado.
        """
        return self.cursor.fetchone()

    def query(self, sql: Any, params: Any = None, many: bool = True) -> tuple[Any, list[str]]:
        """
        Executa uma consulta SQL e retorna os resultados.

        Args:
            sql (str): Consulta SQL.
            params (list/tuple, optional): Parâmetros.
            many (bool): Se True, retorna fetchall(), senão fetchone().

        Returns:
            tuple: (linhas, nomes_colunas).
        """
        if not self.connected:
            raise psycopg2.InterfaceError("A conexão com o banco de dados não está aberta.")
        sql_to_execute = self._mogrify(sql, params)
        try:
            self.cursor.execute(sql_to_execute)
            rows = self.fetchall() if many else self.fetchone()
            description = self.cursor.description or []
            colnames = [desc[0] for desc in description]
            if self.autocommit:
                self.commit()
            return rows, colnames
        except Exception as error:
            self.rollback()
            self._log_error('Erro na consulta SQL', error, sql_to_execute)
            raise

    def _values(self, rows: Sequence[Sequence[Any]]) -> pgsql.Composable:
        """``(v1, v2), (v3, v4)...`` com os valores já escapados."""
        row_template = '(' + ','.join(['%s'] * len(rows[0])) + ')'
        return pgsql.SQL(','.join(
            self.cursor.mogrify(row_template, row).decode('utf-8') for row in rows))

    def insert_many(self, sql: str, params_list: Sequence[Sequence[Any]] | None = None,
                    params: Any = None) -> int:
        """
        Insere múltiplos registros de uma vez.

        ``{params_list}`` em ``sql`` é substituído pelas tuplas de ``params_list``
        (já escapadas). Não combine com ``params`` se os valores contiverem ``%``.
        """
        if params_list is not None and len(params_list) > 0:
            args_str = self._values(params_list).string
            sql = sql.replace('{params_list}', args_str)
        return self.execute(sql, params)

    def insert_list_of_dicts(self, table_name: str, list_of_dicts: Sequence[Mapping[str, Any]],
                             id_columns: Sequence[str] | None) -> Any:
        """
        Insere uma lista de dicionários na tabela (upsert opcional).

        Exemplo:
            db.insert_list_of_dicts(table_name='indicadores',
                                    list_of_dicts=lista,
                                    id_columns=['id', 'ano', 'tipo'])

        Args:
            table_name: nome da tabela no banco de dados (aceita ``schema.tabela``).
            list_of_dicts: lista de dicionários, todos com as mesmas chaves
                (os nomes das colunas), em qualquer ordem.
            id_columns: colunas que formam a chave de conflito (sempre uma lista,
                mesmo com uma só coluna; ``[]`` para não tratar conflitos).

        O comportamento em conflito depende de ``self.on_conflict_do_update``
        (padrão True: atualiza; False: ignora), e ``self.show_sql`` imprime o SQL.

        Retorno: com ``id_columns``, o resultado de ``query`` (linhas e nomes
        de colunas com as chaves inseridas ou atualizadas; com "ignora", as
        linhas em conflito não aparecem); sem ele, o número de linhas afetadas.
        """
        if not list_of_dicts:
            return []

        id_columns = list(id_columns or [])
        keys = list(list_of_dicts[0].keys())
        key_set = set(keys)
        for i, row in enumerate(list_of_dicts):
            if set(row.keys()) != key_set:
                raise ValueError(
                    f'O dicionário na posição {i} tem chaves diferentes das do primeiro.')
        not_keys = [key for key in keys if key not in id_columns]

        data = [tuple(row[key] for key in keys) for row in list_of_dicts]
        statement = pgsql.SQL('INSERT INTO {} ({}) VALUES {}').format(
            _table(table_name),
            pgsql.SQL(', ').join(_name(key) for key in keys),
            self._values(data),
        )

        if not id_columns:
            return self.execute(statement)

        conflict_cols = pgsql.SQL(', ').join(_name(col) for col in id_columns)
        if self.on_conflict_do_update and not_keys:
            statement += pgsql.SQL(' ON CONFLICT ({}) DO UPDATE SET {}').format(
                conflict_cols,
                pgsql.SQL(', ').join(
                    pgsql.SQL('{0} = EXCLUDED.{0}').format(_name(key)) for key in not_keys),
            )
        else:
            statement += pgsql.SQL(' ON CONFLICT ({}) DO NOTHING').format(conflict_cols)
        statement += pgsql.SQL(' RETURNING {}').format(conflict_cols)
        return self.query(statement, many=True)

    def insert_dict(self, table_name: str | None = None, data: Mapping[str, Any] | None = None,
                    on_conflict: Sequence[str] | None = None,
                    on_conflict_do_nothing: bool = False, **legacy: Any) -> int:
        """
        Insere um dicionário (chaves = colunas), com opção de upsert.

        Args:
            table_name: nome da tabela (aceita ``schema.tabela``).
            data: o dicionário; os nomes das chaves devem coincidir com os das colunas.
            on_conflict: lista com as colunas da chave de conflito.
            on_conflict_do_nothing: False (padrão) atualiza a linha em conflito;
                True a mantém como está (DO NOTHING).

        Os nomes antigos ``column_name=`` e ``dict=`` ainda são aceitos, com aviso.
        """
        if 'column_name' in legacy:
            warnings.warn('insert_dict(column_name=...) foi renomeado para table_name=.',
                          DeprecationWarning, stacklevel=2)
            table_name = legacy.pop('column_name')
        if 'dict' in legacy:
            warnings.warn('insert_dict(dict=...) foi renomeado para data=.',
                          DeprecationWarning, stacklevel=2)
            data = legacy.pop('dict')
        if legacy:
            raise TypeError(f'Argumento(s) inesperado(s): {", ".join(legacy)}')
        if table_name is None or data is None:
            raise TypeError('insert_dict exige table_name e data.')

        columns = list(data.keys())
        statement = pgsql.SQL('INSERT INTO {} ({}) VALUES {}').format(
            _table(table_name),
            pgsql.SQL(', ').join(_name(col) for col in columns),
            self._values([tuple(data[col] for col in columns)]),
        )
        if on_conflict:
            conflict_cols = pgsql.SQL(', ').join(_name(col) for col in on_conflict)
            if on_conflict_do_nothing:
                statement += pgsql.SQL(' ON CONFLICT ({}) DO NOTHING').format(conflict_cols)
            else:
                statement += pgsql.SQL(' ON CONFLICT ({}) DO UPDATE SET {}').format(
                    conflict_cols,
                    pgsql.SQL(', ').join(
                        pgsql.SQL('{0} = EXCLUDED.{0}').format(_name(col)) for col in columns),
                )
        return self.execute(statement)

    def check_if_table_exists(self, table_name: str, schema: str = 'public') -> bool:
        """
        Verifica se uma tabela existe (esquema ``public`` por padrão;
        ``schema.tabela`` também é aceito).
        """
        if '.' in table_name:
            schema, table_name = table_name.split('.', 1)
        statement = '''
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = %s
                AND   table_name   = %s
            );
        '''
        return bool(self.query(statement, (schema, table_name), many=False)[0][0])

    def upsert_dataframe(self, df: pd.DataFrame, table_name: str, primary_key_col: str,
                         verbose: bool = True) -> pd.DataFrame:
        """
        Realiza um 'upsert' (insert/update) de um DataFrame via tabela temporária e COPY.
        """
        if not isinstance(df, pd.DataFrame):
            raise TypeError("O argumento 'df' deve ser um DataFrame do pandas.")

        if primary_key_col not in df.columns:
            raise ValueError(
                f"A coluna de chave primária '{primary_key_col}' não foi encontrada no DataFrame.")

        # Remoção de duplicatas no DataFrame
        df_cleaned = df.drop_duplicates(subset=[primary_key_col], keep='last')
        if verbose and len(df_cleaned) < len(df):
            print(f"Aviso: {len(df) - len(df_cleaned)} linhas duplicadas foram "
                  "removidas do DataFrame de entrada.")
        if df_cleaned.empty:
            if verbose:
                print('Nada a fazer: DataFrame vazio.')
            return df_cleaned

        cols = pgsql.SQL(', ').join(pgsql.Identifier(str(c)) for c in df_cleaned.columns)
        update_cols = [c for c in df_cleaned.columns if c != primary_key_col]
        target = _table(table_name)
        temp = pgsql.Identifier(f'tmp_upsert_{uuid.uuid4().hex}')

        if not self.connected:
            self.open()

        try:
            # 1. Criar tabela temporária
            self.execute(pgsql.SQL('CREATE TEMP TABLE {} (LIKE {} INCLUDING DEFAULTS)').format(
                temp, target))
            if verbose:
                print("Tabela temporária criada.")

            # 2. Usar COPY EXPERT para carga em massa
            buffer = io.StringIO()
            df_cleaned.to_csv(buffer, index=False, header=False, sep='\t', na_rep='\\N')
            buffer.seek(0)
            sql_copy = pgsql.SQL(
                "COPY {} ({}) FROM STDIN WITH (FORMAT CSV, DELIMITER E'\\t', NULL '\\N')"
            ).format(temp, cols)
            self.cur.copy_expert(sql_copy.as_string(self.conn), buffer)
            if verbose:
                print(f"{len(df_cleaned)} linhas carregadas na tabela temporária.")

            # 3. Mesclar dados (Upsert)
            merge_sql = pgsql.SQL('INSERT INTO {} ({}) SELECT {} FROM {} ON CONFLICT ({}) ').format(
                target, cols, cols, temp, pgsql.Identifier(primary_key_col))
            if update_cols:
                merge_sql += pgsql.SQL('DO UPDATE SET {}').format(pgsql.SQL(', ').join(
                    pgsql.SQL('{0} = EXCLUDED.{0}').format(pgsql.Identifier(str(c)))
                    for c in update_cols))
            else:
                merge_sql += pgsql.SQL('DO NOTHING')
            self.execute(merge_sql)

            if verbose:
                print(f"Sucesso: {len(df_cleaned)} linhas processadas na tabela '{table_name}'.")
            return df_cleaned

        except Exception as error:
            self.rollback()
            self._log_error('Erro durante o upsert', error, None)
            raise
        finally:
            try:
                self.execute(pgsql.SQL('DROP TABLE IF EXISTS {}').format(temp))
            except Exception:  # não mascara o erro original
                logger.warning('Não foi possível remover a tabela temporária do upsert.')

    def read_sql_to_df(self, sql: Any, params: Any = None,
                       dtypes: Any = None) -> pd.DataFrame:
        """
        Lê grandes volumes de dados do banco de dados diretamente para um DataFrame Pandas.
        Utiliza o comando COPY TO STDOUT para máxima performance.
        """
        if not self.connected:
            self.open()

        # Prepara a query com os parâmetros
        sql_formatado = self._mogrify(sql, params).decode('utf-8').strip().rstrip(';')

        # Cria o comando COPY envolvendo a query original
        copy_query = f"COPY ({sql_formatado}) TO STDOUT WITH (FORMAT CSV, HEADER, DELIMITER ',')"

        # Buffer de memória para receber os dados
        buffer = io.StringIO()

        try:
            # Executa o streaming do banco para o buffer
            self.cursor.copy_expert(copy_query, buffer)
            if self.autocommit:
                self.commit()
            buffer.seek(0)

            # ``dtypes`` evita que identificadores numéricos longos percam
            # zeros à esquerda ou precisão (ex.: {'codigo': str}).
            return pd.read_csv(buffer, dtype=dtypes)
        except Exception as error:
            self.rollback()
            self._log_error('Erro na leitura massiva', error, copy_query)
            raise
