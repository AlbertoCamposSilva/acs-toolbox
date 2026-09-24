import os

import pytest

from acs_toolbox import segredos

_fetch_payload_real = segredos._fetch_payload  # antes do monkeypatch da fixture


@pytest.fixture(autouse=True)
def cofre(monkeypatch):
    monkeypatch.setenv("ACS_TOOLBOX_GCP_PROJECT", "proj")
    monkeypatch.delenv("ACS_TOOLBOX_SECRET_NAME", raising=False)
    for k in ("A", "B", "C", "X"):
        monkeypatch.delenv(k, raising=False)
    segredos.clear_cache()
    chamadas = []

    def fake(project, name):
        chamadas.append((project, name))
        return {"A": "1", "B": "2", "db": {"host": "h"}}

    monkeypatch.setattr(segredos, "_fetch_payload", fake)
    yield chamadas
    segredos.clear_cache()


def test_busca_so_as_chaves_pedidas_e_faz_cache(cofre):
    assert segredos.get_secrets("A") == {"A": "1"}
    assert segredos.get_secret("B") == "2"
    assert segredos.get_secret("db") == {"host": "h"}
    assert cofre == [("proj", "acs-toolbox-secrets")]  # uma única chamada


def test_env_tem_precedencia_e_evita_rede(monkeypatch, cofre):
    monkeypatch.setenv("A", "local")
    assert segredos.get_secret("A") == "local"
    assert cofre == []


def test_chave_ausente_lista_nomes(cofre):
    with pytest.raises(segredos.SecretNotFound) as exc:
        segredos.get_secrets("A", "X", "C")
    assert exc.value.keys == ["X", "C"]
    assert "X, C" in str(exc.value)


def test_default(cofre):
    assert segredos.get_secret("X", default=None) is None


def test_nome_do_segredo_configuravel(monkeypatch, cofre):
    monkeypatch.setenv("ACS_TOOLBOX_SECRET_NAME", "outro")
    segredos.get_secret("A")
    assert cofre == [("proj", "outro")]


def test_nao_configurado(monkeypatch):
    monkeypatch.delenv("ACS_TOOLBOX_GCP_PROJECT")
    with pytest.raises(segredos.SecretsNotConfigured):
        segredos.get_secret("A")
    assert segredos.get_secret("A", default="x") == "x"


def test_load_env(monkeypatch, cofre):
    monkeypatch.setenv("B", "ja_definido")
    segredos.load_env("A", "B")

    assert os.environ["A"] == "1" and os.environ["B"] == "ja_definido"
    monkeypatch.delenv("A")
    with pytest.raises(TypeError):
        segredos.load_env("db")


def test_load_payload_devolve_copia(cofre):
    segredos.load_payload()["db"]["host"] = "alterado"
    assert segredos.get_secret("db") == {"host": "h"}


def test_json_invalido_nao_expoe_conteudo(monkeypatch):
    from types import SimpleNamespace

    from google.cloud import secretmanager

    valor = b'{"SENHA": "super-secreta"'  # JSON truncado

    class FakeClient:
        def access_secret_version(self, request):
            return SimpleNamespace(payload=SimpleNamespace(data=valor))

    monkeypatch.setattr(secretmanager, "SecretManagerServiceClient", FakeClient)
    with pytest.raises(ValueError) as exc:
        _fetch_payload_real("proj", "nome")
    assert "super-secreta" not in repr(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_nome_antigo_nao_existe():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("acs_toolbox.secrets")
