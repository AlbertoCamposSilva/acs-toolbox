from acs_toolbox.webdriver import WebDriver


def test_sem_flags_inseguras_por_padrao():
    wd = WebDriver(downloads_path=".")
    assert "--ignore-certificate-errors" not in wd.options.arguments
    assert "--allow-running-insecure-content" not in wd.options.arguments
    assert not any(a.startswith("--user-agent") for a in wd.options.arguments)


def test_flags_opcionais():
    wd = WebDriver(downloads_path=".", ignora_erros_certificado=True, user_agent="Teste/1.0",
                   roda_silencioso=False)
    assert "--ignore-certificate-errors" in wd.options.arguments
    assert "--allow-running-insecure-content" in wd.options.arguments
    assert "--user-agent=Teste/1.0" in wd.options.arguments
    assert "--headless=new" not in wd.options.arguments


def test_pasta_de_downloads_padrao():
    from acs_toolbox.download import default_downloads_path

    assert WebDriver.get_download_path() == default_downloads_path()
    assert WebDriver().downloads_path == default_downloads_path()
