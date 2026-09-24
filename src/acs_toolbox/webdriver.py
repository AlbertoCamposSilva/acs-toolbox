from __future__ import annotations

from collections.abc import Iterable
from typing import Any

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.wait import WebDriverWait
except ImportError as e:  # pragma: no cover - depende do extra
    raise ImportError(
        'Instale o extra "webdriver": uv add "acs-toolbox[webdriver]"') from e

from acs_toolbox.download import default_downloads_path


class WebDriver:
    def __init__(
        self,
        roda_silencioso: bool = True,
        verbose: bool = False,
        num_tentativas: int = 10,
        downloads_path: str | None = None,
        tempo_espera: float = 30,
        dominios_seguros: str | Iterable[str] | None = None,
        ignora_erros_certificado: bool = False,
        user_agent: str | None = None,
    ) -> None:
        """
        Args:
            roda_silencioso: executa o Chrome em modo headless.
            verbose, num_tentativas: guardados como atributos, para uso de subclasses.
            downloads_path: pasta de downloads (padrão: pasta Downloads do usuário).
            tempo_espera: timeout, em segundos, de carregamento e de espera explícita.
            dominios_seguros: lista de origens (ex.: ``["http://intranet.exemplo.com"]``)
                tratadas como seguras mesmo sem HTTPS. Também aceita uma string
                separada por vírgulas. Padrão: nenhuma.
            ignora_erros_certificado: aceita certificados inválidos e conteúdo misto
                (HTTP em página HTTPS). Desativa a proteção contra interceptação;
                use só em redes internas confiáveis. Padrão: False.
            user_agent: User-Agent a informar aos sites. Padrão: o do próprio Chrome.
        """
        self.num_tentativas = num_tentativas
        self.downloads_path = downloads_path or self.get_download_path()
        self.tempo_espera = tempo_espera
        self.verbose = verbose
        self.dominios_seguros = self._normaliza_dominios(dominios_seguros)
        self.driver: Any = None
        self.wait: Any = None

        self.options = Options()
        if roda_silencioso:
            self.options.add_argument("--headless=new")
        if user_agent:
            self.options.add_argument(f"--user-agent={user_agent}")
        if ignora_erros_certificado:
            self.options.add_argument("--ignore-certificate-errors")
            self.options.add_argument("--allow-running-insecure-content")

        # Origens HTTP tratadas como seguras (parâmetro dominios_seguros)
        if self.dominios_seguros:
            self.options.add_argument(
                "--unsafely-treat-insecure-origin-as-secure="
                + ",".join(self.dominios_seguros)
            )
        self.options.add_experimental_option(
            "prefs",
            {
                "download.default_directory": self.downloads_path,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True,
            },
        )

    @staticmethod
    def _normaliza_dominios(dominios: str | Iterable[str] | None) -> list[str]:
        """Converte None / str separada por vírgulas / iterável em lista limpa."""
        if not dominios:
            return []
        if isinstance(dominios, str):
            dominios = dominios.split(",")
        return [d.strip() for d in dominios if d and d.strip()]

    @staticmethod
    def get_download_path() -> str:
        """Pasta Downloads do usuário (ver ``acs_toolbox.download.default_downloads_path``)."""
        return default_downloads_path()

    def carrega_driver(self) -> None:
        """
        Abre um Driver Selenium Chrome
        """
        self.driver = webdriver.Chrome(options=self.options)
        self.driver.set_page_load_timeout(self.tempo_espera)
        self.driver.implicitly_wait(0)
        self.wait = WebDriverWait(self.driver, self.tempo_espera)

    def sair(self) -> None:
        if self.driver is not None:
            self.driver.quit()
            self.driver = None

    def __enter__(self) -> WebDriver:
        if self.driver is None:
            self.carrega_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.sair()
