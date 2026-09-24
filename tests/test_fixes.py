from acs_toolbox.progress import Progress


def test_progress_com_pausa_em_horario_comercial():
    p = Progress(3, esperar_em_horario_comercial=True,
                 tempo_pausa_fora_horario_comercial=0,
                 tempo_pausa_horario_comercial=0)
    for _ in range(3):
        p.next()


def test_webdriver_dominios_seguros():
    from acs_toolbox.webdriver import WebDriver

    n = WebDriver._normaliza_dominios
    assert n(None) == []
    assert n(["http://a.com", " http://b.com "]) == ["http://a.com", "http://b.com"]
    assert n("http://a.com, http://b.com") == ["http://a.com", "http://b.com"]

    wd = WebDriver(downloads_path=".", dominios_seguros=["http://a.com", "http://b.com"])
    flag = "--unsafely-treat-insecure-origin-as-secure=http://a.com,http://b.com"
    assert flag in wd.options.arguments
    wd = WebDriver(downloads_path=".")
    assert not any("unsafely" in a for a in wd.options.arguments)


def test_config_padrao(monkeypatch, tmp_path):
    import pytest

    from acs_toolbox import segredos
    from acs_toolbox.database import Database

    monkeypatch.delenv("ACS_TOOLBOX_DB_CONFIG", raising=False)
    monkeypatch.delenv("ACS_TOOLBOX_GCP_PROJECT", raising=False)
    with pytest.raises(FileNotFoundError, match="ACS_TOOLBOX_DB_CONFIG"):
        Database.config_db_connection()

    ini = tmp_path / "database.ini"
    ini.write_text("\n".join(["[postgresql]", "host=h", "user=u", ""]))
    monkeypatch.setenv("ACS_TOOLBOX_DB_CONFIG", str(ini))
    assert Database.config_db_connection() == {"host": "h", "user": "u"}

    monkeypatch.setenv("ACS_TOOLBOX_DB_CONFIG", str(tmp_path / "nao_existe.ini"))
    with pytest.raises(FileNotFoundError):
        Database.config_db_connection()

    monkeypatch.delenv("ACS_TOOLBOX_DB_CONFIG")
    monkeypatch.setenv("ACS_TOOLBOX_GCP_PROJECT", "proj")
    segredos.clear_cache()
    monkeypatch.setattr(segredos, "_fetch_payload",
                        lambda p, n: {"postgresql": {"host": "h2", "port": 5432}})
    assert Database.config_db_connection() == {"host": "h2", "port": "5432"}
    segredos.clear_cache()


def test_sem_logging_basicconfig():
    import logging

    import acs_toolbox.database  # noqa: F401

    assert any(isinstance(h, logging.NullHandler)
               for h in logging.getLogger("acs_toolbox.database").handlers)
