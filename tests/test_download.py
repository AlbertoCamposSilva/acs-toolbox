import os
import time

import pytest

from acs_toolbox import download
from acs_toolbox.download import Download, default_downloads_path


def _arquivo(pasta, nome, conteudo="x", mtime=None):
    caminho = pasta / nome
    caminho.write_text(conteudo)
    if mtime is not None:
        os.utime(caminho, (mtime, mtime))
    return str(caminho)


def test_pasta_inexistente_nao_quebra(tmp_path):
    dl = Download(path=str(tmp_path / "nao_existe"))
    assert dl.check_chrome_temporary_files() == 0
    assert dl.check_newer_file() is None
    assert dl.check_curr_files() == []


def test_check_download_detecta_arquivo_novo(tmp_path):
    _arquivo(tmp_path, "antigo.csv", mtime=time.time() - 100)
    dl = Download(path=str(tmp_path), time_to_wait_download=2)
    dl.check_curr_files()
    novo = _arquivo(tmp_path, "novo.csv")
    assert dl.check_download() is True
    assert dl.newer_file == novo
    assert dl.check_download() is False  # nada novo desde a última verificação


def test_wait_the_download_respeita_start_time(tmp_path):
    _arquivo(tmp_path, "velho.csv", mtime=time.time() - 100)
    dl = Download(path=str(tmp_path))
    with pytest.raises(TimeoutError):
        dl.wait_the_download(start_time=time.time(), wait_time=1)


def test_rename_file_sem_arquivos(tmp_path):
    with pytest.raises(FileNotFoundError):
        Download(path=str(tmp_path)).rename_file("x.csv")


def test_rename_file_mantem_extensao(tmp_path):
    _arquivo(tmp_path, "relatorio (1).xlsx")
    destino = Download(path=str(tmp_path)).rename_file("final.csv")
    assert destino == os.path.join(str(tmp_path), "final.xlsx")
    assert os.path.exists(destino)


def test_delete_temporarios_poupa_tmp_alheio(tmp_path):
    antes = time.time() - 10
    _arquivo(tmp_path, "baixando.crdownload")
    alheio = _arquivo(tmp_path, "outro_programa.tmp", mtime=antes - 100)
    dl = Download(path=str(tmp_path))
    assert dl.delete_all_temporary_files() == 1
    assert os.path.exists(alheio)
    assert dl.delete_all_temporary_files(start_time=antes - 200) == 0


def test_pasta_padrao(monkeypatch, tmp_path):
    monkeypatch.setattr(download.os, "name", "posix")
    monkeypatch.setattr(download.os.path, "expanduser", lambda p: str(tmp_path))
    assert default_downloads_path() == os.path.join(str(tmp_path), "Downloads")
