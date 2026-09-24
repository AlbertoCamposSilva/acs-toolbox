import pytest

from acs_toolbox.progress import Progress


@pytest.mark.parametrize("valor", [0, -5, True, 2.5, "3"])
def test_max_invalido(valor):
    with pytest.raises(ValueError):
        Progress(valor)


def test_next_devolve_texto_e_para_no_max(capsys):
    p = Progress(2)
    assert p.next().startswith("1/2, 50%")
    assert p.next().startswith("Fim.")
    assert p.next() is None
    assert p.curr_iter == 2
    assert "Fim." in capsys.readouterr().out


def test_next_builtin_continua_funcionando():
    p = Progress(1)
    assert next(p).startswith("Fim.")


def test_stringify():
    assert Progress.stringify(3725) == "1h 2m 5s"
    assert Progress.stringify(90061) == "1d 1h 1m 1s"
    assert Progress.stringify(-1) == "0.0s"


def test_if_clear_nao_chama_os_system(monkeypatch):
    import os

    monkeypatch.setattr(os, "system", lambda *_: pytest.fail("os.system chamado"))
    p = Progress(3, if_clear=True)
    p.next()
