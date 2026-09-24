from __future__ import annotations

import os
import shutil
import sys
import time

#: Extensões de arquivos parciais de download (Chrome/Edge e navegadores em geral).
TEMPORARY_EXTENSIONS = ('.crdownload', '.tmp')


def default_downloads_path() -> str:
    """
    Pasta Downloads do usuário.

    No Windows lê a pasta configurada no registro (que pode ter sido movida
    pelo usuário); nos demais sistemas, e se a leitura falhar, usa ``~/Downloads``.
    """
    if sys.platform == 'win32':
        try:
            import winreg

            sub_key = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders'
            downloads_guid = '{374DE290-123F-4565-9164-39C4925E467B}'
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub_key) as key:
                location = winreg.QueryValueEx(key, downloads_guid)[0]
            return os.path.expandvars(location)
        except OSError:
            pass
    return os.path.join(os.path.expanduser('~'), 'Downloads')


class Download:
    def __init__(self,
                 path: str | None = None,
                 wait_to_download: bool = True,
                 verbose: bool = False,
                 time_to_wait_download: float = 120) -> None:
        self.verbose = verbose
        self.curr_files: list[str] = []
        self.newer_file: str | None = None
        self.temporary_files: list[str] = []
        self.wait_download = wait_to_download
        self.time_to_wait_download = time_to_wait_download
        self.path = default_downloads_path() if path is None else path

    def _list_files(self) -> list[str]:
        """Arquivos da pasta (sem ``desktop.ini``); lista vazia se a pasta não existe."""
        try:
            names = os.listdir(self.path)
        except FileNotFoundError:
            return []
        files = []
        for filename in names:
            filepath = os.path.join(self.path, filename)
            if os.path.isfile(filepath) and filename.lower() != 'desktop.ini':
                files.append(filepath)
        return files

    @staticmethod
    def _newest(files: list[str]) -> str | None:
        newest = None
        newest_mtime = float('-inf')
        for filepath in files:
            try:
                mtime = os.path.getmtime(filepath)
            except OSError:  # removido entre a listagem e a leitura
                continue
            if mtime > newest_mtime:
                newest, newest_mtime = filepath, mtime
        return newest

    def _wait_for_file_lock(self, filepath: str, timeout: float = 10) -> bool:
        """
        Garante que o arquivo foi totalmente liberado pelo SO e Antivírus
        tentando abri-lo em modo de acréscimo (append).
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Verifica se o arquivo não está vazio
                if os.path.getsize(filepath) > 0:
                    # Tenta obter o lock do arquivo. Falhará se estiver em uso.
                    with open(filepath, 'a'):
                        pass
                    return True
            except OSError:
                # Arquivo ainda bloqueado pelo sistema, aguarda
                pass
            time.sleep(0.5)
        return False

    def wait_the_download(self, start_time: float | None = None,
                          wait_time: float | None = None) -> str:
        """
        Bloqueia até surgir um arquivo completo na pasta e devolve o seu caminho.

        Com ``start_time`` (``time.time()`` de antes do clique), só aceita arquivos
        modificados depois dele. Levanta ``TimeoutError`` se o tempo acabar.
        """
        if wait_time is None:
            wait_time = self.time_to_wait_download

        seconds = 0.0
        arquivo_baixado = None

        while seconds < wait_time:
            temp_count = self.check_chrome_temporary_files()
            novo_arquivo = self.check_newer_file()

            # Lógica de validação do arquivo:
            # 1. Deve existir.
            # 2. Se start_time foi fornecido, deve ser mais recente que ele.
            valido = False
            if novo_arquivo:
                try:
                    valido = start_time is None or os.path.getmtime(novo_arquivo) >= start_time
                except OSError:
                    valido = False

            # Se não há temporários e já validamos o arquivo novo
            if temp_count == 0 and valido:
                arquivo_baixado = novo_arquivo
                break

            # Download em curso ou servidor processando, aguarda
            time.sleep(0.5)
            seconds += 0.5

        # Validação Crítica: Aguarda a liberação de I/O do Windows
        if arquivo_baixado:
            self._wait_for_file_lock(arquivo_baixado)
            self.newer_file = arquivo_baixado  # Atualiza o atributo para o arquivo baixado
            return arquivo_baixado
        raise TimeoutError("Download não concluído dentro do tempo esperado.")

    def check_chrome_temporary_files(self) -> int:
        """Atualiza ``temporary_files`` e devolve quantos downloads parciais existem."""
        self.temporary_files = [
            f for f in self._list_files() if f.lower().endswith(TEMPORARY_EXTENSIONS)]
        return len(self.temporary_files)

    def delete_all_temporary_files(self, start_time: float | None = None) -> int:
        """
        Apaga os downloads parciais ``.crdownload``.

        Arquivos ``.tmp`` também são criados por outros programas; só são
        apagados se modificados depois de ``start_time`` (``time.time()``).
        Arquivos bloqueados são ignorados. Devolve quantos parciais restaram.
        """
        self.check_chrome_temporary_files()
        for file in self.temporary_files:
            try:
                if not file.lower().endswith('.crdownload'):
                    if start_time is None or os.path.getmtime(file) < start_time:
                        continue
                os.remove(file)
            except OSError:  # em uso, sem permissão ou já removido
                pass
        return self.check_chrome_temporary_files()

    def check_curr_files(self) -> list[str]:
        self.curr_files = self._list_files()
        self.newer_file = self._newest(self.curr_files)
        return self.curr_files

    def check_newer_file(self) -> str | None:
        """Arquivo mais recente da pasta, ou None se ela estiver vazia/inexistente."""
        return self._newest(self._list_files())

    def check_download(self) -> bool:
        """
        True se surgiu um arquivo novo e completo desde a última verificação
        (``check_curr_files`` ou ``check_download``).
        """
        previous = self.newer_file
        if self.wait_download:
            try:
                self.wait_the_download()
            except TimeoutError:
                return False
        local_newer_file = self.check_newer_file()
        if not local_newer_file or self.check_chrome_temporary_files() > 0 \
                or local_newer_file == previous:
            return False
        self.newer_file = local_newer_file
        return True

    def rename_file(self, new_file_name: str,
                    old_file_name: str | None = None,
                    mantem_extensao: bool = True,
                    preserva_diretorio: bool = False,
                    preserva_nome: bool = False) -> str:
        if old_file_name is None:
            old_file_name = self.check_newer_file()
            if old_file_name is None:
                raise FileNotFoundError(f'Nenhum arquivo encontrado em {self.path}.')

        old_path = os.path.dirname(old_file_name)
        old_name, old_extension = os.path.splitext(os.path.basename(old_file_name))

        new_path = os.path.dirname(new_file_name)
        if new_path == '':
            new_path = self.path
        new_name, new_extension = os.path.splitext(os.path.basename(new_file_name))

        extensao = old_extension if mantem_extensao else new_extension
        new_file_name = (old_name if preserva_nome else new_name) + extensao
        diretorio = old_path if preserva_diretorio else new_path

        complete_new_filename = os.path.join(diretorio, new_file_name)
        if self.verbose:
            print(f'            Movendo de '
                  f'{old_file_name} para {complete_new_filename}.')
        shutil.move(old_file_name, complete_new_filename)
        return complete_new_filename
