import importlib

import pytest

import acs_toolbox


def test_version():
    assert acs_toolbox.__version__


@pytest.mark.parametrize("name", ["database", "download", "progress", "segredos", "webdriver"])
def test_submodules_import(name):
    assert importlib.import_module(f"acs_toolbox.{name}")
    assert getattr(acs_toolbox, name)


def test_default_config_env(monkeypatch):
    from acs_toolbox.database import default_config_file

    monkeypatch.setenv("ACS_TOOLBOX_DB_CONFIG", "x.ini")
    assert default_config_file() == "x.ini"
