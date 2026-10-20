from __future__ import annotations

import socket

import pytest

from acs_toolbox import segredos, zimbra
from acs_toolbox.zimbra import (
    MensagemZimbra,
    PastaZimbra,
    Zimbra,
    ZimbraAuthError,
    ZimbraError,
    ZimbraVPNRequiredError,
    _normalizar_usuario,
    build_foldersync_wbxml,
    build_provision_ack_wbxml,
    build_provision_request_wbxml,
    build_search_wbxml,
    build_sendmail_wbxml,
    decode_wbxml,
    parse_foldersync_response,
    parse_provision_response,
    parse_search_response,
)


def _sample_foldersync_wbxml() -> bytes:
    """
    Constrói uma resposta WBXML sintética de FolderSync contendo duas pastas:
    Inbox (ID '2', Type '2') e GT CAs (ID '125890', ParentId '2', Type '12').
    """
    # Header WBXML 1.3 UTF-8 + CodePage 7 (FolderHierarchy)
    buf = bytearray([0x03, 0x01, 0x6A, 0x00, 0x00, 0x07])
    buf.append(0x56)  # <FolderSync>
    buf.extend([0x4C, 0x03, 0x31, 0x00, 0x01])  # <Status>1</Status>
    buf.extend([0x52, 0x03, 0x31, 0x00, 0x01])  # <SyncKey>1</SyncKey>
    buf.append(0x4E)  # <Changes>
    buf.extend([0x57, 0x03, 0x32, 0x00, 0x01])  # <Count>2</Count>

    # <Add> Inbox (ServerId=2, ParentId=0, Type=2)
    buf.append(0x4F)
    buf.extend(b"\x48\x032\x00\x01")
    buf.extend(b"\x49\x030\x00\x01")
    buf.extend(b"\x47\x03Inbox\x00\x01")
    buf.extend(b"\x4a\x032\x00\x01")
    buf.append(0x01)

    # <Add> GT CAs (ServerId=125890, ParentId=2, Type=12)
    buf.append(0x4F)
    buf.extend(b"\x48\x03125890\x00\x01")
    buf.extend(b"\x49\x032\x00\x01")
    buf.extend(b"\x47\x03GT CAs\x00\x01")
    buf.extend(b"\x4a\x0312\x00\x01")
    buf.append(0x01)

    buf.extend([0x01, 0x01])  # </Changes></FolderSync>
    return bytes(buf)


def _sample_search_wbxml() -> bytes:
    """Constrói uma resposta WBXML sintética de Search com 1 e-mail."""
    buf = bytearray([0x03, 0x01, 0x6A, 0x00, 0x00, 0x0F])
    buf.append(0x45)  # <Search>
    buf.extend([0x4C, 0x03, 0x31, 0x00, 0x01])  # <Status>1</Status>
    buf.append(0x4D)  # <Response>
    buf.append(0x47)  # <Store>
    buf.extend([0x4C, 0x03, 0x31, 0x00, 0x01])  # <Status>1</Status>
    buf.append(0x4E)  # <Result>
    buf.extend(b"\x58\x03141700\x00\x01")  # <LongId>
    buf.extend(b"\x00\x00\x52\x032\x00\x01")  # <CollectionId>2</CollectionId>
    buf.extend([0x00, 0x0F, 0x4F])  # <Properties>
    buf.extend([0x00, 0x02])  # CodePage 2 (Email)
    buf.extend(b"\x54\x03Assunto de Teste\x00\x01")
    buf.extend(b"\x58\x03remetente@cnpq.br\x00\x01")
    buf.extend(b"\x56\x03alberto.silva@cnpq.br\x00\x01")
    buf.extend(b"\x4f\x032026-10-18T14:05:17.000Z\x00\x01")
    buf.extend(b"\x55\x031\x00\x01")  # <Read>1</Read>
    buf.extend([0x00, 0x11, 0x4A])  # <Body xmlns="AirSyncBase">
    buf.extend(b"\x4c\x0342\x00\x01")  # <EstimatedDataSize>
    buf.extend(b"\x4b\x03Corpo da mensagem\x00\x01")  # <Data>
    buf.append(0x01)  # </Body>
    buf.extend([0x01, 0x01, 0x01, 0x01, 0x01])  # </Properties></Result></Store></Response></Search>
    return bytes(buf)


def _sample_provision_response_wbxml(status: str, policy_key: str | None = None) -> bytes:
    """Constrói uma resposta WBXML sintética de Provision ([MS-ASPROV])."""
    buf = bytearray([0x03, 0x01, 0x6A, 0x00, 0x00, 0x0E])
    buf.append(0x45)  # <Provision>
    buf.extend([0x4B, 0x03, 0x31, 0x00, 0x01])  # <Status>1</Status>
    buf.append(0x46)  # <Policies>
    buf.append(0x47)  # <Policy>
    buf.extend([0x48, 0x03])  # <PolicyType>
    buf.extend(b"MS-EAS-Provisioning-WBXML\x00\x01")
    buf.extend([0x4B, 0x03])  # <Status>
    buf.extend(status.encode("ascii") + b"\x00\x01")
    if policy_key is not None:
        buf.extend([0x49, 0x03])  # <PolicyKey>
        buf.extend(policy_key.encode("ascii") + b"\x00\x01")
    buf.extend([0x01, 0x01, 0x01])  # </Policy></Policies></Provision>
    return bytes(buf)


def test_normalizar_usuario():
    assert _normalizar_usuario("albertos") == "albertos"
    assert _normalizar_usuario("cnpq.lan\\albertos") == "albertos"
    assert _normalizar_usuario("cnpq.lan\\alberto.silva@cnpq.br") == "alberto.silva@cnpq.br"


def test_wbxml_builders_and_parsers():
    fs_req = build_foldersync_wbxml("0")
    ev_fs = decode_wbxml(fs_req)
    assert ("START", "FolderSync", None) in ev_fs
    assert ("TEXT", "SyncKey", "0") in ev_fs

    s_req = build_search_wbxml(pasta_id="2", limite=5, texto_busca="CNPq")
    ev_s = decode_wbxml(s_req)
    assert ("TEXT", "Name", "Mailbox") in ev_s
    assert ("TEXT", "FreeText", "CNPq") in ev_s
    assert ("TEXT", "Range", "0-4") in ev_s

    sm_req = build_sendmail_wbxml(b"Subject: Oi\r\n\r\nTeste", client_id="123")
    ev_sm = decode_wbxml(sm_req)
    assert ("START", "SendMail", None) in ev_sm
    assert ("TEXT", "ClientId", "123") in ev_sm
    assert ("TEXT", "Mime", "Subject: Oi\r\n\r\nTeste") in ev_sm

    pastas = parse_foldersync_response(_sample_foldersync_wbxml())
    assert pastas == [
        PastaZimbra(id="2", parent_id="0", nome="Inbox", tipo=2),
        PastaZimbra(id="125890", parent_id="2", nome="GT CAs", tipo=12),
    ]

    msgs = parse_search_response(_sample_search_wbxml())
    assert len(msgs) == 1
    assert msgs[0] == MensagemZimbra(
        id="141700",
        pasta_id="2",
        assunto="Assunto de Teste",
        remetente="remetente@cnpq.br",
        para="alberto.silva@cnpq.br",
        cc="",
        data_recebimento="2026-10-18T14:05:17.000Z",
        lida=True,
        corpo="Corpo da mensagem",
        tamanho=42,
    )


def test_provision_builders_and_parsers():
    req1 = build_provision_request_wbxml()
    ev1 = decode_wbxml(req1)
    assert ("START", "Provision", None) in ev1
    assert ("TEXT", "PolicyType", "MS-EAS-Provisioning-WBXML") in ev1

    ack = build_provision_ack_wbxml("TEMPPK123", status="1")
    ev_ack = decode_wbxml(ack)
    assert ("TEXT", "PolicyKey", "TEMPPK123") in ev_ack
    assert ("TEXT", "Status", "1") in ev_ack

    st1, pk1 = parse_provision_response(_sample_provision_response_wbxml("1", "KEY789"))
    assert st1 == "1"
    assert pk1 == "KEY789"

    st2, pk2 = parse_provision_response(_sample_provision_response_wbxml("2", None))
    assert st2 == "2"
    assert pk2 is None


def test_resolucao_credenciais_cofre(monkeypatch):
    monkeypatch.setenv("ACS_TOOLBOX_GCP_PROJECT", "proj")
    for k in ("ZIMBRA_USER", "ZIMBRA_APP_PASSWORD", "ZIMBRA_PASSWORD", "CNPQ_EMAIL"):
        monkeypatch.delenv(k, raising=False)
    segredos.clear_cache()
    monkeypatch.setattr(
        segredos,
        "_fetch_payload",
        lambda p, n: {"ZIMBRA_USER": "cnpq.lan\\albertos", "ZIMBRA_APP_PASSWORD": "ABCD"},
    )
    zm = Zimbra(garantir_vpn=False)
    assert zm.user == "albertos"
    assert zm._password == "ABCD"
    segredos.clear_cache()


def test_somente_leitura_bloqueia_sendmail():
    zm = Zimbra(user="albertos", password="XYZ", garantir_vpn=False, somente_leitura=True)
    with pytest.raises(ZimbraError) as exc:
        zm.enviar_email(para="teste@cnpq.br", assunto="Assunto", corpo="Corpo")
    assert "somente leitura" in str(exc.value)


def test_provision_com_policy_key_e_cache(tmp_path, monkeypatch):
    cache_file = tmp_path / "zimbra_provision.json"
    zm = Zimbra(
        user="albertos",
        password="XYZ",
        garantir_vpn=False,
        device_id="MESAALBERTO01",
        caminho_cache_provision=cache_file,
    )
    assert zm.policy_key is None

    # Simula handshake de provisionamento em 2 etapas
    step = 0

    def fake_request(
        self, method, path, body=None, content_type=None, extra_headers=None, esperar_449=False
    ):
        nonlocal step
        step += 1
        if "Cmd=Provision" in path:
            if step == 1:
                return 200, {}, _sample_provision_response_wbxml("1", "TEMP123")
            return 200, {}, _sample_provision_response_wbxml("1", "FINAL456")
        if "Cmd=FolderSync" in path:
            assert extra_headers is not None
            assert extra_headers.get("X-MS-PolicyKey") == "FINAL456"
            return 200, {}, _sample_foldersync_wbxml()
        return 200, {}, b""

    monkeypatch.setattr(Zimbra, "_request", fake_request)

    pk = zm.provisionar()
    assert pk == "FINAL456"
    assert zm.policy_key == "FINAL456"
    assert cache_file.is_file()

    # Nova instância reaproveita a chave em cache
    zm2 = Zimbra(
        user="albertos",
        password="XYZ",
        garantir_vpn=False,
        device_id="MESAALBERTO01",
        caminho_cache_provision=cache_file,
    )
    assert zm2.policy_key == "FINAL456"
    pastas = zm2.listar_pastas()
    assert len(pastas) == 2


def test_reprovisionamento_automatico_status_142(tmp_path, monkeypatch):
    cache_file = tmp_path / "zimbra_provision.json"
    zm = Zimbra(
        user="albertos",
        password="XYZ",
        garantir_vpn=False,
        device_id="MESAALBERTO01",
        caminho_cache_provision=cache_file,
    )
    zm.policy_key = "EXPIRADA123"

    chamadas = []

    def fake_request(
        method, path, body=None, content_type=None, extra_headers=None, esperar_449=False
    ):
        chamadas.append(path)
        if "Cmd=FolderSync" in path and len(chamadas) == 1:
            # Responde WBXML com Status 142 (DeviceNotProvisioned)
            buf = bytearray([0x03, 0x01, 0x6A, 0x00, 0x00, 0x00])
            buf.extend([0x4E, 0x03, 0x31, 0x34, 0x32, 0x00, 0x01])  # <Status>142</Status>
            return 200, {}, bytes(buf)
        if "Cmd=Provision" in path:
            return 200, {}, _sample_provision_response_wbxml("2", None)
        if "Cmd=FolderSync" in path and len(chamadas) >= 3:
            return 200, {}, _sample_foldersync_wbxml()
        return 200, {}, b""

    monkeypatch.setattr(zm, "_request", fake_request)
    pastas = zm.listar_pastas()
    assert len(pastas) == 2
    assert any("Cmd=Provision" in c for c in chamadas)


def test_bloqueio_radware_levanta_erro_vpn(monkeypatch):
    zm = Zimbra(user="albertos", password="XYZ", garantir_vpn=False)
    zm._target_ip = "66.22.29.31"

    class FakeResp:
        status = 302

        def read(self):
            return b"<html>302 Found</html>"

        def getheaders(self):
            return [
                ("Server", "rdwr"),
                ("Location", "https://validate.perfdrive.com/?ssa=123"),
            ]

    class FakeConn:
        def __init__(self, *a, **kw):
            pass

        def request(self, *a, **kw):
            pass

        def getresponse(self):
            return FakeResp()

        def close(self):
            pass

    monkeypatch.setattr(zimbra.http.client, "HTTPSConnection", FakeConn)
    with pytest.raises(ZimbraVPNRequiredError) as exc:
        zm.listar_pastas()
    assert "vpn_connect" in str(exc.value)


def test_erro_autenticacao_401(monkeypatch):
    zm = Zimbra(user="albertos", password="ERR", garantir_vpn=False)
    zm._target_ip = "10.0.5.42"

    class FakeResp:
        status = 401

        def read(self):
            return b"Unauthorized"

        def getheaders(self):
            return [("WWW-Authenticate", 'Basic realm="ZeXtras Mobile"')]

    class FakeConn:
        def __init__(self, *a, **kw):
            pass

        def request(self, *a, **kw):
            pass

        def getresponse(self):
            return FakeResp()

        def close(self):
            pass

    monkeypatch.setattr(zimbra.http.client, "HTTPSConnection", FakeConn)
    with pytest.raises(ZimbraAuthError):
        zm.verificar_conexao()


def test_assegurar_vpn_aciona_vpn_connect(monkeypatch):
    estados = [False, True]
    monkeypatch.setattr(Zimbra, "verificar_vpn_ativa", lambda self: estados.pop(0))
    monkeypatch.setattr(Zimbra, "_tentar_conectar_vpn", staticmethod(lambda: True))
    zm = Zimbra(user="albertos", password="OK", garantir_vpn=True)
    assert zm.user == "albertos"


def _vpn_cnpq_ativa() -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.5)
    try:
        s.connect(("10.0.5.42", 443))
        return True
    except OSError:
        return False
    finally:
        s.close()


@pytest.mark.skipif(not _vpn_cnpq_ativa(), reason="Requer VPN do CNPq ativa (10.0.5.42:443)")
def test_integracao_zimbra_cnpq():
    with Zimbra(device_id="MESAALBERTO01") as zm:
        info = zm.autodiscover()
        assert info.get("email") == "alberto.silva@cnpq.br"

        conn_info = zm.verificar_conexao()
        assert conn_info["conectado"] is True
        assert "14.1" in conn_info["versoes"]

        pastas = zm.listar_pastas()
        nomes = {p.nome for p in pastas}
        assert "Inbox" in nomes
        assert zm.obter_id_pasta("Inbox") == "2"

        # Duas buscas consecutivas com o MESMO DeviceId fixo para validar estabilidade
        msgs1 = zm.listar_mensagens("Inbox", limite=2)
        assert isinstance(msgs1, list)
        assert len(msgs1) >= 1

        msgs2 = zm.listar_mensagens("Inbox", limite=2)
        assert isinstance(msgs2, list)
        assert len(msgs2) >= 1
        assert msgs1[0].id == msgs2[0].id
