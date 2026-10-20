r"""
Cliente Zimbra / Exchange ActiveSync (EAS) para o webmail institucional do CNPq.

O servidor ``webmail.cnpq.br`` utiliza Zimbra Collaboration Suite com o módulo
ZeXtras Mobile, expondo os protocolos Exchange Autodiscover e Exchange ActiveSync
(versões 2.5 a 16.1) sobre HTTPS com codificação binária WBXML (``[MS-ASWBXML]``).

Requisitos importantes de rede, provisionamento e autenticação:

1. **VPN do CNPq obrigatória fora da rede física (`vpn-connect`)**:
   Na internet pública, ``webmail.cnpq.br`` resolve por Split-DNS para o WAF em nuvem
   da Radware (``66.22.29.31`` / ``radwarecloud.net``), cujo *Bot Manager* intercepta
   requisições ``POST /Microsoft-Server-ActiveSync`` e redireciona (``HTTP 302``) para
   uma página de Captcha em JavaScript (``validate.perfdrive.com``). Com a VPN ativa
   (ou dentro da rede física do CNPq), ``webmail.cnpq.br`` resolve diretamente para o
   IP interno ``10.0.5.42``, sem bloqueio do WAF.
2. **DeviceId Fixo e Provisionamento ([MS-ASPROV])**:
   Por padrão, recomenda-se definir um ``device_id`` estável (ex.: ``"MESAALBERTO01"``)
   para que a aplicação seja reconhecida como um único dispositivo móvel no Zimbra.
   O cliente executa o handshake de provisionamento (comandos Provision Fase 1 e Fase 2),
   persiste o ``PolicyKey`` em cache local e o envia no cabeçalho ``X-MS-PolicyKey``,
   evitando poluição em *Preferências -> Aplicativos e dispositivos móveis*.
3. **Senha de Aplicativo (16 letras)**:
   Contas com segundo fator (2FA) ativo no Zimbra exigem uma Senha de Aplicativo
   gerada em *Preferências -> Contas -> Códigos de Aplicativo*, armazenada no cofre
   ``acs_toolbox.segredos`` sob a chave ``ZIMBRA_APP_PASSWORD`` (e o login em
   ``ZIMBRA_USER``, ex.: ``"alberto.silva@cnpq.br"`` sem prefixo de domínio).
4. **Configuração de Clientes de E-mail Desktop no PC (Outlook Clássico vs. Thunderbird)**:
   - **Thunderbird**: Não suporta Exchange ActiveSync (EAS) para mensagens de e-mail
     (apenas EWS e IMAP), sendo incompatível com a caixa postal do CNPq.
   - **Outlook Clássico**: A Microsoft removeu a configuração manual de contas EAS do
     assistente moderno. Para configurar, feche o Outlook, pressione ``Win + R`` e execute:
     ``"C:\Program Files\Microsoft Office\root\Office16\MLCFG32.CPL"`` -> *Contas de Email* ->
     *Novo...* -> *Configuração manual* -> *Serviço compatível com Exchange ActiveSync (EAS)*,
     informando o servidor ``webmail.cnpq.br`` e a Senha de Aplicativo de 16 letras.
   - **Reverter Novo Outlook**: Caso o Windows force a abertura do New Outlook, defina
     ``HKCU:\\Software\\Microsoft\\Office\\16.0\\Outlook\\Preferences\\UseNewOutlook = 0``.
"""

from __future__ import annotations

import base64
import email.policy
import http.client
import ipaddress
import json
import logging
import os
import socket
import ssl
import sys
import urllib.parse
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

from .segredos import ENV_PROJECT, SecretNotFound, SecretsNotConfigured, get_secret

logger = logging.getLogger(__name__)

DEFAULT_HOST = "webmail.cnpq.br"
INTERNAL_ZIMBRA_IP = "10.0.5.42"
DEFAULT_USER = "alberto.silva@cnpq.br"
OUTLOOK_USER_AGENT = "Microsoft Office/16.0 (Windows NT 10.0; Microsoft Outlook 16.0.17928; Pro)"
DEFAULT_VPN_CONNECT_SRC = r"C:\Projetos\CNPq\importantes\VPN Connect\src"

# Tabelas de tokens WBXML ([MS-ASWBXML]) usadas pelo Exchange ActiveSync
_CODEPAGES: dict[int, dict[int, str]] = {
    0: {  # AirSync
        0x05: "Sync",
        0x06: "Responses",
        0x07: "Add",
        0x08: "Change",
        0x09: "Delete",
        0x0A: "Fetch",
        0x0B: "SyncKey",
        0x0C: "ClientId",
        0x0D: "ServerId",
        0x0E: "Status",
        0x0F: "Collection",
        0x10: "Class",
        0x11: "Version",
        0x12: "CollectionId",
        0x13: "GetChanges",
        0x14: "MoreAvailable",
        0x15: "WindowSize",
        0x16: "Commands",
        0x17: "Options",
        0x18: "FilterType",
        0x1C: "Collections",
        0x1D: "ApplicationData",
    },
    2: {  # Email
        0x05: "Attachment",
        0x06: "Attachments",
        0x07: "AttName",
        0x08: "AttSize",
        0x0C: "Body",
        0x0D: "BodySize",
        0x0E: "BodyTruncated",
        0x0F: "DateReceived",
        0x10: "DisplayName",
        0x11: "DisplayTo",
        0x12: "Importance",
        0x13: "MessageClass",
        0x14: "Subject",
        0x15: "Read",
        0x16: "To",
        0x17: "Cc",
        0x18: "From",
        0x19: "ReplyTo",
        0x1D: "ThreadTopic",
        0x22: "InternetCPID",
    },
    7: {  # FolderHierarchy
        0x05: "Folders",
        0x06: "Folder",
        0x07: "DisplayName",
        0x08: "ServerId",
        0x09: "ParentId",
        0x0A: "Type",
        0x0B: "Response",
        0x0C: "Status",
        0x0D: "ContentClass",
        0x0E: "Changes",
        0x0F: "Add",
        0x10: "Delete",
        0x11: "Update",
        0x12: "SyncKey",
        0x13: "FolderCreate",
        0x14: "FolderDelete",
        0x15: "FolderUpdate",
        0x16: "FolderSync",
        0x17: "Count",
    },
    14: {  # Provision ([MS-ASPROV])
        0x05: "Provision",
        0x06: "Policies",
        0x07: "Policy",
        0x08: "PolicyType",
        0x09: "PolicyKey",
        0x0A: "Data",
        0x0B: "Status",
        0x0C: "RemoteWipe",
        0x0D: "EASProvisionDoc",
    },
    15: {  # Search
        0x05: "Search",
        0x07: "Store",
        0x08: "Name",
        0x09: "Query",
        0x0A: "Options",
        0x0B: "Range",
        0x0C: "Status",
        0x0D: "Response",
        0x0E: "Result",
        0x0F: "Properties",
        0x10: "Total",
        0x11: "EqualTo",
        0x12: "Value",
        0x13: "And",
        0x14: "Or",
        0x15: "FreeText",
        0x17: "DeepTraversal",
        0x18: "LongId",
        0x19: "RebuildResults",
        0x1A: "LessThan",
        0x1B: "GreaterThan",
    },
    17: {  # AirSyncBase
        0x05: "BodyPreference",
        0x06: "Type",
        0x07: "TruncationSize",
        0x08: "AllOrNone",
        0x0A: "Body",
        0x0B: "Data",
        0x0C: "EstimatedDataSize",
        0x0D: "Truncated",
        0x0E: "Attachments",
        0x0F: "Attachment",
        0x10: "DisplayName",
        0x11: "FileReference",
        0x12: "Method",
        0x13: "EstimatedDataSizeExt",
        0x14: "ContentId",
        0x16: "IsInline",
        0x17: "NativeBodyType",
        0x18: "ContentType",
    },
    18: {  # Settings
        0x05: "Settings",
        0x06: "Status",
        0x07: "Get",
        0x08: "Set",
        0x09: "Group",
        0x0A: "Min",
        0x0B: "Max",
        0x0C: "FilterType",
        0x0D: "HeartbeatInterval",
        0x0E: "Header",
        0x16: "DeviceInformation",
        0x17: "Model",
        0x18: "IMEI",
        0x19: "FriendlyName",
        0x1A: "OS",
        0x1B: "OSLanguage",
        0x1C: "PhoneNumber",
        0x1D: "UserAgent",
        0x1E: "MobileOperator",
        0x1F: "EnableOutboundSMS",
        0x20: "MobilePhoneNumber",
    },
    21: {  # ComposeMail
        0x05: "SendMail",
        0x06: "SmartForward",
        0x07: "SmartReply",
        0x08: "SaveInSentItems",
        0x09: "ReplaceMime",
        0x0B: "Source",
        0x0C: "FolderId",
        0x0D: "ItemId",
        0x0E: "LongId",
        0x0F: "InstanceId",
        0x10: "Mime",
        0x11: "ClientId",
        0x12: "Status",
        0x13: "AccountId",
    },
}


class ZimbraError(RuntimeError):
    """Erro base de comunicação ou protocolo no cliente Zimbra/ActiveSync."""


class ZimbraVPNRequiredError(ZimbraError):
    """
    Acesso bloqueado pelo WAF externo (Radware Bot Manager) porque a VPN do CNPq
    não está conectada.
    """


class ZimbraAuthError(ZimbraError):
    """Credenciais recusadas pelo servidor Zimbra / ZeXtras Mobile (HTTP 401/403)."""


@dataclass(frozen=True)
class PastaZimbra:
    """Representa uma pasta da caixa postal retornada pelo ``FolderSync``."""

    id: str
    parent_id: str
    nome: str
    tipo: int


@dataclass(frozen=True)
class MensagemZimbra:
    """Representa uma mensagem de e-mail retornada pelo ``Search`` ActiveSync."""

    id: str
    pasta_id: str
    assunto: str
    remetente: str
    para: str
    cc: str
    data_recebimento: str
    lida: bool
    corpo: str
    tamanho: int


def _is_private_ip(ip_str: str) -> bool:
    """Retorna True se o endereço IPv4 pertencer à rede privada/interna."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private
    except ValueError:
        return False


def _normalizar_usuario(user: str) -> str:
    """
    Remove prefixo de domínio ``cnpq.lan\\`` quando o login não contém ``@``,
    pois o ZeXtras Mobile rejeita ``cnpq.lan\\usuario`` sem sufixo ``@cnpq.br``.
    """
    limpo = user.strip()
    if "\\" in limpo:
        _, usuario_sem_dom = limpo.split("\\", 1)
        return usuario_sem_dom.strip()
    return limpo


def decode_wbxml(data: bytes) -> list[tuple[str, str, str | None]]:
    """
    Decodifica um documento binário WBXML 1.3 ActiveSync em uma lista de eventos
    ``(tipo_evento, nome_tag, texto)``, onde ``tipo_evento`` é ``'START'``,
    ``'TEXT'`` ou ``'END'``.
    """
    if len(data) < 4:
        return []

    # Cabeçalho WBXML: version (1B), publicid (1B), charset (1B), string_table_len (mb_u_int32)
    pos = 3
    strtbl_len = 0
    while pos < len(data):
        b = data[pos]
        pos += 1
        strtbl_len = (strtbl_len << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    pos += strtbl_len

    cp = 0
    stack: list[str] = []
    events: list[tuple[str, str, str | None]] = []

    while pos < len(data):
        token_byte = data[pos]
        pos += 1
        if token_byte == 0x00:  # SWITCH_PAGE
            if pos < len(data):
                cp = data[pos]
                pos += 1
        elif token_byte == 0x01:  # END
            tag = stack.pop() if stack else "?"
            events.append(("END", tag, None))
        elif token_byte == 0x03:  # STR_I (inline null-terminated UTF-8 string)
            end = data.find(0x00, pos)
            if end == -1:
                end = len(data)
            texto = data[pos:end].decode("utf-8", errors="replace")
            pos = end + 1
            events.append(("TEXT", stack[-1] if stack else "?", texto))
        elif token_byte == 0xC3:  # OPAQUE (usado em MIME / binários)
            opaque_len = 0
            while pos < len(data):
                b = data[pos]
                pos += 1
                opaque_len = (opaque_len << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
            opaque_bytes = data[pos : pos + opaque_len]
            pos += opaque_len
            texto = opaque_bytes.decode("utf-8", errors="replace")
            events.append(("TEXT", stack[-1] if stack else "?", texto))
        else:
            has_content = bool(token_byte & 0x40)
            tag_id = token_byte & 0x3F
            tag = _CODEPAGES.get(cp, {}).get(tag_id, f"CP{cp}:0x{tag_id:02x}")
            events.append(("START", tag, None))
            if has_content:
                stack.append(tag)
            else:
                events.append(("END", tag, None))
    return events


def _encode_opaque(raw: bytes) -> bytes:
    """Codifica um bloco ``OPAQUE`` (``0xC3`` + tamanho ``mb_u_int32`` + bytes)."""
    length = len(raw)
    chunks: list[int] = [length & 0x7F]
    length >>= 7
    while length > 0:
        chunks.append((length & 0x7F) | 0x80)
        length >>= 7
    chunks.reverse()
    return bytes([0xC3, *chunks]) + raw


def build_foldersync_wbxml(sync_key: str = "0") -> bytes:
    """Constrói payload WBXML para ``<FolderSync><SyncKey>0</SyncKey></FolderSync>``."""
    sk_bytes = sync_key.encode("utf-8")
    return (
        bytes([0x03, 0x01, 0x6A, 0x00, 0x00, 0x07, 0x56, 0x52, 0x03])
        + sk_bytes
        + bytes([0x00, 0x01, 0x01])
    )


def build_search_wbxml(
    pasta_id: str = "2",
    limite: int = 10,
    desde: str = "2020-01-01T00:00:00.000Z",
    texto_busca: str | None = None,
    truncation_size: int = 50000,
) -> bytes:
    """
    Constrói payload WBXML para ``Cmd=Search`` no store ``Mailbox``, filtrando
    por ``CollectionId``, ``DateReceived >= desde`` e opcionalmente ``FreeText``,
    solicitando o corpo em texto puro (``BodyPreference Type=1``).
    """
    if limite < 1:
        raise ValueError("O parâmetro limite deve ser maior ou igual a 1.")
    range_str = f"0-{limite - 1}".encode("ascii")
    folder_bytes = str(pasta_id).encode("utf-8")
    desde_bytes = desde.encode("utf-8")
    trunc_bytes = str(truncation_size).encode("ascii")

    # <Search xmlns="Search"><Store><Name>Mailbox</Name><Query><And>
    buf = bytearray([0x03, 0x01, 0x6A, 0x00, 0x00, 0x0F, 0x45, 0x47, 0x48, 0x03])
    buf.extend(b"Mailbox")
    buf.extend([0x00, 0x01, 0x49, 0x53])

    # <Class xmlns="AirSync">Email</Class><CollectionId xmlns="AirSync">{pasta_id}</CollectionId>
    buf.extend([0x00, 0x00, 0x50, 0x03])
    buf.extend(b"Email")
    buf.extend([0x00, 0x01, 0x52, 0x03])
    buf.extend(folder_bytes)
    buf.extend([0x00, 0x01])

    # <GreaterThan xmlns="Search"><DateReceived xmlns="Email"/><Value>{desde}</Value></GreaterThan>
    buf.extend([0x00, 0x0F, 0x5B, 0x00, 0x02, 0x0F, 0x00, 0x0F, 0x52, 0x03])
    buf.extend(desde_bytes)
    buf.extend([0x00, 0x01, 0x01])

    # <FreeText xmlns="Search">{texto_busca}</FreeText> (opcional)
    if texto_busca:
        buf.extend([0x55, 0x03])
        buf.extend(texto_busca.encode("utf-8"))
        buf.extend([0x00, 0x01])

    # </And></Query><Options><Range>0-(limite-1)</Range>
    buf.extend([0x01, 0x01, 0x4A, 0x4B, 0x03])
    buf.extend(range_str)
    buf.extend([0x00, 0x01])

    # <BodyPreference xmlns="AirSyncBase"><Type>1</Type><TruncationSize>...</TruncationSize>
    buf.extend([0x00, 0x11, 0x45, 0x46, 0x03, 0x31, 0x00, 0x01, 0x47, 0x03])
    buf.extend(trunc_bytes)
    buf.extend([0x00, 0x01, 0x01])

    # </Options></Store></Search>
    buf.extend([0x01, 0x01, 0x01])
    return bytes(buf)


def build_sendmail_wbxml(
    mime_bytes: bytes,
    client_id: str | None = None,
    salvar_itens_enviados: bool = True,
) -> bytes:
    """
    Constrói payload WBXML para ``Cmd=SendMail`` (CodePage 21 ``ComposeMail``).
    """
    cid = (client_id or uuid.uuid4().hex).encode("ascii")
    buf = bytearray([0x03, 0x01, 0x6A, 0x00, 0x00, 0x15, 0x45])  # <SendMail>
    buf.extend([0x51, 0x03])  # <ClientId>
    buf.extend(cid)
    buf.extend([0x00, 0x01])  # </ClientId>
    if salvar_itens_enviados:
        buf.append(0x08)  # <SaveInSentItems/> (empty tag)
    buf.append(0x50)  # <Mime>
    buf.extend(_encode_opaque(mime_bytes))
    buf.append(0x01)  # </Mime>
    buf.append(0x01)  # </SendMail>
    return bytes(buf)


def build_provision_request_wbxml(
    policy_type: str = "MS-EAS-Provisioning-WBXML",
) -> bytes:
    """
    Constrói payload WBXML para a Fase 1 do Provision ([MS-ASPROV]).
    ``<Provision><Policies><Policy><PolicyType>{policy_type}</PolicyType></Policy></Policies></Provision>``
    """
    pt_bytes = policy_type.encode("ascii")
    return (
        bytes([0x03, 0x01, 0x6A, 0x00, 0x00, 0x0E, 0x45, 0x46, 0x47, 0x48, 0x03])
        + pt_bytes
        + bytes([0x00, 0x01, 0x01, 0x01, 0x01])
    )


def build_provision_ack_wbxml(
    policy_key: str,
    status: str = "1",
    policy_type: str = "MS-EAS-Provisioning-WBXML",
) -> bytes:
    """
    Constrói payload WBXML para a Fase 2 (Acknowledge) do Provision ([MS-ASPROV]).
    ``<Provision><Policies><Policy><PolicyType>...</PolicyType><PolicyKey>...</PolicyKey><Status>1</Status></Policy></Policies></Provision>``
    """
    pt_bytes = policy_type.encode("ascii")
    pk_bytes = policy_key.encode("ascii")
    st_bytes = status.encode("ascii")
    buf = bytearray([0x03, 0x01, 0x6A, 0x00, 0x00, 0x0E, 0x45, 0x46, 0x47])
    # <PolicyType>
    buf.extend([0x48, 0x03])
    buf.extend(pt_bytes)
    buf.extend([0x00, 0x01])
    # <PolicyKey>
    buf.extend([0x49, 0x03])
    buf.extend(pk_bytes)
    buf.extend([0x00, 0x01])
    # <Status>
    buf.extend([0x4B, 0x03])
    buf.extend(st_bytes)
    buf.extend([0x00, 0x01])
    # </Policy></Policies></Provision>
    buf.extend([0x01, 0x01, 0x01])
    return bytes(buf)


def parse_provision_response(data: bytes) -> tuple[str, str | None]:
    """
    Decodifica a resposta WBXML de Provision retornando ``(status, policy_key)``.
    Status '1' indica sucesso; Status '2' indica sem política obrigatória;
    policy_key é retornado se presente.
    """
    events = decode_wbxml(data)
    status_provision = "1"
    status_policy = None
    policy_key = None
    in_policy = False
    for ev_type, tag, text in events:
        if ev_type == "START" and tag == "Policy":
            in_policy = True
        elif ev_type == "END" and tag == "Policy":
            in_policy = False
        elif ev_type == "TEXT" and text is not None:
            if tag == "Status":
                if in_policy:
                    status_policy = text
                else:
                    status_provision = text
            elif tag == "PolicyKey":
                policy_key = text
    status_final = status_policy or status_provision
    return status_final, policy_key


def parse_foldersync_response(data: bytes) -> list[PastaZimbra]:
    """Extrai a lista de ``PastaZimbra`` de uma resposta WBXML de ``FolderSync``."""
    events = decode_wbxml(data)
    pastas: list[PastaZimbra] = []
    in_add = False
    atual: dict[str, str] = {}

    for ev_type, tag, text in events:
        if ev_type == "START" and tag == "Add":
            in_add = True
            atual = {}
        elif ev_type == "TEXT" and in_add and text is not None:
            atual[tag] = text
        elif ev_type == "END" and tag == "Add" and in_add:
            in_add = False
            if "ServerId" in atual and "DisplayName" in atual:
                try:
                    tipo_int = int(atual.get("Type", "1"))
                except ValueError:
                    tipo_int = 1
                pastas.append(
                    PastaZimbra(
                        id=atual["ServerId"],
                        parent_id=atual.get("ParentId", "0"),
                        nome=atual["DisplayName"],
                        tipo=tipo_int,
                    )
                )
    return pastas


def parse_search_response(data: bytes) -> list[MensagemZimbra]:
    """Extrai a lista de ``MensagemZimbra`` de uma resposta WBXML de ``Search``."""
    events = decode_wbxml(data)
    mensagens: list[MensagemZimbra] = []
    in_result = False
    in_props = False
    in_body = False
    atual: dict[str, str] = {}

    for ev_type, tag, text in events:
        if ev_type == "START" and tag == "Result":
            in_result = True
            atual = {}
        elif ev_type == "START" and tag == "Properties" and in_result:
            in_props = True
        elif ev_type == "START" and tag == "Body" and in_props:
            in_body = True
        elif ev_type == "END" and tag == "Body" and in_props:
            in_body = False
        elif ev_type == "END" and tag == "Properties" and in_result:
            in_props = False
        elif ev_type == "TEXT" and in_result and text is not None:
            if in_body and tag in ("Data", "Body"):
                atual["BodyData"] = text
            elif in_body and tag == "EstimatedDataSize":
                atual["EstimatedDataSize"] = text
            elif not in_body:
                atual[tag] = text
        elif ev_type == "END" and tag == "Result" and in_result:
            in_result = False
            if not atual:
                continue
            try:
                tamanho = int(atual.get("EstimatedDataSize", atual.get("BodySize", "0")))
            except ValueError:
                tamanho = 0
            mensagens.append(
                MensagemZimbra(
                    id=atual.get("LongId", atual.get("ServerId", "")),
                    pasta_id=atual.get("CollectionId", "2"),
                    assunto=atual.get("Subject", ""),
                    remetente=atual.get("From", ""),
                    para=atual.get("To", atual.get("DisplayTo", "")),
                    cc=atual.get("Cc", ""),
                    data_recebimento=atual.get("DateReceived", ""),
                    lida=atual.get("Read", "0") == "1",
                    corpo=atual.get("BodyData", atual.get("Body", "")),
                    tamanho=tamanho,
                )
            )
    return mensagens


class Zimbra:
    """
    Cliente para leitura, busca e envio de e-mails no Zimbra do CNPq
    (``webmail.cnpq.br``) via protocolo Exchange ActiveSync (EAS).

    Por padrão (``garantir_vpn=True``), verifica antes de conectar se o domínio
    ``webmail.cnpq.br`` está resolvendo para a rede interna do CNPq (``10.0.5.42``).
    Caso esteja resolvendo para o IP público do WAF Radware (``66.22.29.31``),
    aciona automaticamente o ``vpn_connect`` (ou levanta ``ZimbraVPNRequiredError``).
    """

    def __init__(
        self,
        user: str | None = None,
        password: str | None = None,
        host: str = DEFAULT_HOST,
        garantir_vpn: bool = True,
        timeout: int = 15,
        ignora_erros_certificado: bool = False,
        device_id: str | None = None,
        device_type: str = "ACSToolbox",
        user_agent: str | None = None,
        caminho_cache_provision: str | Path | None = None,
        somente_leitura: bool = False,
    ) -> None:
        self.host = host
        self.timeout = timeout
        self.garantir_vpn = garantir_vpn
        self.ignora_erros_certificado = ignora_erros_certificado
        self.device_type = device_type
        self.user_agent = user_agent or f"{device_type}/0.3.0"
        self.somente_leitura = somente_leitura

        raw_user, raw_pass = self._resolver_credenciais(user, password)
        self.user = _normalizar_usuario(raw_user)
        self._password = raw_pass
        self._target_ip: str | None = None

        env_dev_id = os.environ.get("ZIMBRA_DEVICE_ID", "").strip() or None
        self.device_id = device_id or env_dev_id
        if not self.device_id:
            logger.warning(
                'Nenhum "device_id" informado para o cliente Zimbra. Usando DeviceId '
                "efêmero por requisição. Para reaproveitar o mesmo aparelho e evitar "
                'acúmulo em "Aplicativos e dispositivos móveis", informe '
                'device_id="MESAALBERTO01" ou configure a variável ZIMBRA_DEVICE_ID.'
            )

        if caminho_cache_provision is not None:
            self._caminho_cache = Path(caminho_cache_provision)
        else:
            base_dir = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
            self._caminho_cache = Path(base_dir) / "acs_toolbox" / "zimbra_provision.json"

        self.policy_key: str | None = None
        if self.device_id:
            self.policy_key = self._carregar_cache_provision()

        if self.garantir_vpn:
            self.assegurar_vpn()

    def __enter__(self) -> Zimbra:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    @staticmethod
    def _resolver_credenciais(
        user: str | None,
        password: str | None,
    ) -> tuple[str, str]:
        """
        Obtém ``(user, password)`` dos argumentos, variáveis de ambiente ou cofre
        ``acs_toolbox.segredos``.
        """
        if user and password:
            return user, password

        if ENV_PROJECT not in os.environ:
            os.environ[ENV_PROJECT] = "acs-toolbox"

        cfg_dict: dict[str, Any] = {}
        try:
            zimbra_secret = get_secret("zimbra", default=None)
            if isinstance(zimbra_secret, dict):
                cfg_dict = zimbra_secret
        except (SecretsNotConfigured, SecretNotFound):
            pass

        resolved_user = (
            user
            or get_secret("ZIMBRA_USER", default=None)
            or get_secret("CNPQ_EMAIL", default=None)
            or cfg_dict.get("user")
            or get_secret("CNPQ_USER", default=None)
            or DEFAULT_USER
        )

        resolved_pass = (
            password
            or get_secret("ZIMBRA_APP_PASSWORD", default=None)
            or get_secret("ZIMBRA_PASSWORD", default=None)
            or cfg_dict.get("password")
        )

        if not resolved_pass:
            raise SecretNotFound(["ZIMBRA_APP_PASSWORD"])

        return str(resolved_user), str(resolved_pass)

    def _ssl_context(self) -> ssl.SSLContext:
        ctx = ssl.create_default_context()
        if self.ignora_erros_certificado:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.user}:{self._password}".encode()).decode("ascii")
        return f"Basic {token}"

    @staticmethod
    def _novo_device_id() -> str:
        """
        Gera um ``DeviceId`` efêmero para operações ActiveSync stateless.
        Evita o bloqueio de segunda requisição sem provisionamento no ZeXtras Mobile.
        """
        return "AGY" + uuid.uuid4().hex[:12].upper()

    def _chave_cache_provision(self) -> str:
        dev_id = self.device_id or "anonymous"
        return f"{self.host}:{self.user}:{dev_id}"

    def _carregar_cache_provision(self) -> str | None:
        """Lê o PolicyKey armazenado em arquivo de cache JSON."""
        if not self._caminho_cache.is_file():
            return None
        try:
            data = json.loads(self._caminho_cache.read_text(encoding="utf-8"))
            entry = data.get(self._chave_cache_provision())
            if isinstance(entry, dict) and "policy_key" in entry:
                return str(entry["policy_key"])
        except Exception as exc:
            logger.debug("Não foi possível carregar cache de provisionamento: %s", exc)
        return None

    def _salvar_cache_provision(self, policy_key: str) -> None:
        """Salva o PolicyKey no arquivo de cache JSON."""
        try:
            self._caminho_cache.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {}
            if self._caminho_cache.is_file():
                try:
                    data = json.loads(self._caminho_cache.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data[self._chave_cache_provision()] = {
                "policy_key": policy_key,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._caminho_cache.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Falha ao salvar cache de provisionamento: %s", exc)

    def provisionar(self, forcar: bool = False) -> str | None:
        """
        Executa o handshake de provisionamento ([MS-ASPROV]) com o servidor.
        Fase 1: Envia solicitação de política MS-EAS-Provisioning-WBXML.
        Fase 2: Envia confirmação (ACK) com o PolicyKey temporário recebido.
        Armazena o PolicyKey definitivo em cache e retorna a chave.
        """
        if not self.device_id:
            raise ZimbraError('Não é possível provisionar sem um "device_id" estável definido.')

        if not forcar and self.policy_key:
            return self.policy_key

        dev_id = self.device_id
        query = urllib.parse.urlencode(
            {
                "Cmd": "Provision",
                "User": self.user,
                "DeviceId": dev_id,
                "DeviceType": self.device_type,
            }
        )
        req1 = build_provision_request_wbxml()
        _, _, body1 = self._request(
            "POST",
            f"/Microsoft-Server-ActiveSync?{query}",
            body=req1,
        )
        if not body1:
            self.policy_key = "0"
            self._salvar_cache_provision("0")
            return "0"

        st_prov, temp_pk = parse_provision_response(body1)
        if st_prov == "2":
            # Sem política obrigatória no servidor
            self.policy_key = "0"
            self._salvar_cache_provision("0")
            return "0"

        if st_prov != "1" or not temp_pk:
            raise ZimbraError(
                f"Falha na Fase 1 do provisionamento ActiveSync: Status={st_prov}, "
                f"PolicyKey={temp_pk}"
            )

        # Fase 2: ACK
        req2 = build_provision_ack_wbxml(policy_key=temp_pk, status="1")
        _, _, body2 = self._request(
            "POST",
            f"/Microsoft-Server-ActiveSync?{query}",
            body=req2,
        )
        st_prov2, final_pk = parse_provision_response(body2)
        if st_prov2 != "1":
            raise ZimbraError(f"Falha na Fase 2 (ACK) do provisionamento: Status={st_prov2}")

        chave_final = final_pk or temp_pk
        self.policy_key = chave_final
        self._salvar_cache_provision(chave_final)
        logger.info("Provisionamento concluído com sucesso. PolicyKey: %s", chave_final)
        return chave_final

    def verificar_vpn_ativa(self) -> bool:
        """
        Verifica se ``self.host`` resolve para a rede interna do CNPq (IP privado,
        ex.: ``10.0.5.42``) ou se a rota direta para ``10.0.5.42:443`` está acessível.
        """
        try:
            ip_resolvido = socket.gethostbyname(self.host)
            if _is_private_ip(ip_resolvido):
                self._target_ip = ip_resolvido
                return True
        except OSError:
            pass

        # Caso o cache de DNS do Windows ainda aponte para o IP externo da Radware logo
        # após conectar a VPN, testa o socket TCP direto no IP interno 10.0.5.42:443.
        if self.host.lower() == DEFAULT_HOST:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.5)
            try:
                sock.connect((INTERNAL_ZIMBRA_IP, 443))
                self._target_ip = INTERNAL_ZIMBRA_IP
                return True
            except OSError:
                return False
            finally:
                sock.close()
        return False

    def assegurar_vpn(self) -> None:
        """
        Garante que a VPN do CNPq está conectada antes de enviar requisições ``POST``
        ao Exchange ActiveSync. Se desconectada, tenta acionar ``vpn_connect``
        automaticamente; se indisponível ou falhar, levanta ``ZimbraVPNRequiredError``.
        """
        if self.verificar_vpn_ativa():
            return

        logger.info(
            "Rota interna para %s indisponível (WAF Radware detectado). "
            "Tentando conectar a VPN do CNPq via vpn_connect...",
            self.host,
        )
        conectou = self._tentar_conectar_vpn()
        if conectou and self.verificar_vpn_ativa():
            return

        raise ZimbraVPNRequiredError(
            f'Acesso ao Exchange ActiveSync em "{self.host}" requer a VPN do CNPq ativa '
            f"(fora da VPN, o WAF Radware redireciona requisições POST para página de "
            f"Captcha em validate.perfdrive.com). Conecte antes executando:\n"
            f'  uv run --project "C:\\Projetos\\CNPq\\importantes\\VPN Connect" '
            f"python -m vpn_connect.cli"
        )

    @staticmethod
    def _tentar_conectar_vpn() -> bool:
        """Importa ``vpn_connect`` (adicionando o caminho padrão se necessário) e conecta."""
        try:
            import vpn_connect  # type: ignore[import-not-found]
        except ImportError:
            if os.path.isdir(DEFAULT_VPN_CONNECT_SRC) and DEFAULT_VPN_CONNECT_SRC not in sys.path:
                sys.path.insert(0, DEFAULT_VPN_CONNECT_SRC)
            try:
                import vpn_connect  # type: ignore[import-not-found]
            except ImportError:
                return False

        try:
            st = vpn_connect.verificar_status_vpn()
            if not st.get("conectado"):
                vpn_connect.desconectar_vpn()
                return bool(vpn_connect.conectar_vpn_completo())
            return True
        except Exception as exc:
            logger.warning("Falha ao tentar conectar a VPN via vpn_connect: %s", exc)
            return False

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        content_type: str = "application/vnd.ms-sync.wbxml",
        extra_headers: dict[str, str] | None = None,
        esperar_449: bool = False,
    ) -> tuple[int, dict[str, str], bytes]:
        """Executa uma requisição HTTPS ao Zimbra tratando redirecionamentos do WAF e erros."""
        if self.garantir_vpn and self._target_ip is None:
            self.assegurar_vpn()

        conn = http.client.HTTPSConnection(
            self.host,
            443,
            context=self._ssl_context(),
            timeout=self.timeout,
        )

        headers: dict[str, str] = {
            "Host": self.host,
            "User-Agent": self.user_agent,
            "Authorization": self._auth_header(),
            "MS-ASProtocolVersion": "14.1",
        }
        if body is not None:
            headers["Content-Type"] = content_type
        if extra_headers:
            headers.update(extra_headers)

        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            resp_body = resp.read()
            resp_headers = {k.lower(): v for k, v in resp.getheaders()}
            status = resp.status
        except OSError as exc:
            raise ZimbraError(
                f"Falha de conexão com o servidor Zimbra ({self.host}:443): {exc}"
            ) from exc
        finally:
            conn.close()

        location = resp_headers.get("location", "")
        server_hdr = resp_headers.get("server", "")
        if (
            (
                status in (301, 302, 303, 307)
                and ("perfdrive.com" in location or server_hdr.lower() == "rdwr")
            )
            or b"Radware Captcha Page" in resp_body
            or b"Unauthorized Request Blocked" in resp_body
        ):
            raise ZimbraVPNRequiredError(
                f'Requisição "{method} {path}" interceptada pelo WAF externo da Radware '
                f"(Location: {location or 'Captcha/Block'}). Conecte a VPN do CNPq "
                f"(vpn_connect) antes de acessar o Zimbra."
            )

        if status in (401, 403):
            raise ZimbraAuthError(
                f'Autenticação recusada (HTTP {status}) para o usuário "{self.user}". '
                f"Verifique se está usando uma Senha de Aplicativo de 16 letras gerada "
                f"no Zimbra (ZIMBRA_APP_PASSWORD) e domínio em branco."
            )

        if status == 449 and esperar_449:
            return status, resp_headers, resp_body

        if status >= 400:
            trecho = resp_body[:200].decode("utf-8", errors="replace")
            raise ZimbraError(f'Erro HTTP {status} em "{method} {path}": {trecho}')

        return status, resp_headers, resp_body

    def _post_activesync(
        self,
        cmd: str,
        body: bytes,
        tentativa_reprov: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        """
        Executa requisição ActiveSync POST enviando DeviceId e PolicyKey apropriados,
        e tratando auto-recuperação de provisionamento (HTTP 449 ou WBXML Status 142/143/144).
        """
        if cmd == "SendMail" and self.somente_leitura:
            raise ZimbraError(
                "Cliente Zimbra inicializado em modo somente leitura (somente_leitura=True); "
                "envio de e-mail bloqueado."
            )

        if self.device_id and self.policy_key is None and cmd != "Provision":
            try:
                self.provisionar()
            except Exception as exc:
                logger.debug("Tentativa inicial de provisionamento em %s: %s", cmd, exc)

        dev_id = self.device_id or self._novo_device_id()
        query = urllib.parse.urlencode(
            {
                "Cmd": cmd,
                "User": self.user,
                "DeviceId": dev_id,
                "DeviceType": self.device_type,
            }
        )
        extra_headers: dict[str, str] = {}
        if self.policy_key:
            extra_headers["X-MS-PolicyKey"] = self.policy_key

        status, headers, resp_body = self._request(
            "POST",
            f"/Microsoft-Server-ActiveSync?{query}",
            body=body,
            extra_headers=extra_headers,
            esperar_449=True,
        )

        precisa_reprov = False
        if status == 449:
            precisa_reprov = True
        elif resp_body:
            events = decode_wbxml(resp_body)
            for ev_type, tag, text in events:
                if ev_type == "TEXT" and tag == "Status" and text in ("142", "143", "144"):
                    precisa_reprov = True
                    break

        if precisa_reprov and tentativa_reprov and self.device_id:
            logger.info(
                "Servidor exigiu provisionamento ActiveSync (Status/HTTP=%s). "
                'Executando auto-recuperação com Provision para DeviceId="%s"...',
                status,
                self.device_id,
            )
            self.provisionar(forcar=True)
            return self._post_activesync(cmd, body, tentativa_reprov=False)

        return status, headers, resp_body

    def autodiscover(self) -> dict[str, str]:
        """
        Consulta ``POST /Autodiscover/Autodiscover.xml`` (schema MobileSync) e
        devolve os metadados da conta (``display_name``, ``email``, ``activesync_url``).
        """
        email_addr = self.user if "@" in self.user else f"{self.user}@cnpq.br"
        xml_payload = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<Autodiscover xmlns="http://schemas.microsoft.com/exchange/'
            'autodiscover/mobilesync/requestschema/2006">'
            "<Request>"
            f"<EMailAddress>{email_addr}</EMailAddress>"
            "<AcceptableResponseSchema>"
            "http://schemas.microsoft.com/exchange/autodiscover/mobilesync/responseschema/2006"
            "</AcceptableResponseSchema>"
            "</Request>"
            "</Autodiscover>"
        ).encode()

        _, _, body = self._request(
            "POST",
            "/Autodiscover/Autodiscover.xml",
            body=xml_payload,
            content_type="text/xml; charset=utf-8",
        )

        try:
            root = ET.fromstring(body.decode("utf-8", errors="replace"))
        except ET.ParseError as exc:
            raise ZimbraError("Resposta XML inválida no Autodiscover.") from exc

        info: dict[str, str] = {}
        for elem in root.iter():
            tag_local = elem.tag.split("}")[-1]
            if elem.text and elem.text.strip():
                if tag_local == "DisplayName":
                    info["display_name"] = elem.text.strip()
                elif tag_local in ("EMailAddress", "EmailAddress"):
                    info["email"] = elem.text.strip()
                elif tag_local == "Url":
                    info["activesync_url"] = elem.text.strip()
        return info

    def verificar_conexao(self) -> dict[str, Any]:
        """
        Executa ``OPTIONS /Microsoft-Server-ActiveSync`` e retorna um dicionário
        com as versões e comandos ActiveSync suportados pelo servidor.
        """
        status, headers, _ = self._request("OPTIONS", "/Microsoft-Server-ActiveSync")
        versoes = [
            v.strip() for v in headers.get("ms-asprotocolversions", "").split(",") if v.strip()
        ]
        comandos = [
            c.strip() for c in headers.get("ms-asprotocolcommands", "").split(",") if c.strip()
        ]
        return {
            "conectado": status == 200,
            "servidor_activesync": headers.get("ms-server-activesync", ""),
            "versoes": versoes,
            "comandos": comandos,
        }

    def listar_pastas(self) -> list[PastaZimbra]:
        """
        Lista todas as pastas da caixa postal no Zimbra via ``Cmd=FolderSync``.
        """
        wbxml = build_foldersync_wbxml("0")
        _, _, body = self._post_activesync("FolderSync", wbxml)
        return parse_foldersync_response(body)

    def obter_id_pasta(self, nome: str) -> str:
        """
        Retorna o ``ServerId`` correspondente ao nome de uma pasta (sem diferenciar
        maiúsculas/minúsculas). Para ``Inbox``/``Caixa de Entrada`` e ``Sent``/``Enviados``,
        resolve diretamente caso corresponda aos nomes padrão.
        """
        alvo = nome.strip().lower()
        atalhos = {
            "inbox": "2",
            "caixa de entrada": "2",
            "trash": "3",
            "lixeira": "3",
            "junk": "4",
            "spam": "4",
            "sent": "5",
            "enviados": "5",
            "drafts": "6",
            "rascunhos": "6",
        }
        if alvo in atalhos:
            return atalhos[alvo]

        pastas = self.listar_pastas()
        for p in pastas:
            if p.nome.strip().lower() == alvo or p.id == nome.strip():
                return p.id
        nomes_disp = ", ".join(sorted(p.nome for p in pastas))
        raise ValueError(f'Pasta "{nome}" não encontrada. Pastas disponíveis: {nomes_disp}')

    def listar_mensagens(
        self,
        pasta: str = "Inbox",
        limite: int = 10,
        desde: str = "2020-01-01T00:00:00.000Z",
        texto_busca: str | None = None,
        truncation_size: int = 50000,
    ) -> list[MensagemZimbra]:
        """
        Lista as mensagens mais recentes de uma pasta (nome ou ID numérico) via
        ``Cmd=Search`` do Exchange ActiveSync.

        * ``pasta``: nome da pasta (ex.: ``"Inbox"``, ``"Sent"``, ``"GT CAs"``) ou ID
          numérico (ex.: ``"2"``).
        * ``limite``: quantidade máxima de mensagens retornadas (padrão 10).
        * ``desde``: filtro ISO-8601 UTC mínimo de recebimento.
        * ``texto_busca``: termo opcional para filtrar por assunto/corpo/remetente.
        """
        pasta_id = pasta if pasta.isdigit() else self.obter_id_pasta(pasta)
        wbxml = build_search_wbxml(
            pasta_id=pasta_id,
            limite=limite,
            desde=desde,
            texto_busca=texto_busca,
            truncation_size=truncation_size,
        )
        _, _, body = self._post_activesync("Search", wbxml)
        return parse_search_response(body)

    def buscar_mensagens(
        self,
        texto_busca: str,
        pasta: str = "Inbox",
        limite: int = 10,
        desde: str = "2020-01-01T00:00:00.000Z",
    ) -> list[MensagemZimbra]:
        """Busca mensagens contendo ``texto_busca`` na pasta informada."""
        return self.listar_mensagens(
            pasta=pasta,
            limite=limite,
            desde=desde,
            texto_busca=texto_busca,
        )

    def enviar_email(
        self,
        para: str | Sequence[str],
        assunto: str,
        corpo: str,
        cc: str | Sequence[str] | None = None,
        cco: str | Sequence[str] | None = None,
        html: bool = False,
        salvar_itens_enviados: bool = True,
    ) -> bool:
        """
        Envia um e-mail através do comando ``Cmd=SendMail`` do Exchange ActiveSync.
        Retorna ``True`` se o servidor aceitar o envio (HTTP 200 sem erro WBXML).
        """
        if self.somente_leitura:
            raise ZimbraError(
                "Cliente Zimbra inicializado em modo somente leitura (somente_leitura=True); "
                "envio de e-mail bloqueado."
            )

        remetente = self.user if "@" in self.user else f"{self.user}@cnpq.br"
        msg = EmailMessage(policy=email.policy.SMTP)
        msg["From"] = remetente
        msg["To"] = ", ".join([para] if isinstance(para, str) else list(para))
        if cc:
            msg["Cc"] = ", ".join([cc] if isinstance(cc, str) else list(cc))
        if cco:
            msg["Bcc"] = ", ".join([cco] if isinstance(cco, str) else list(cco))
        msg["Subject"] = assunto
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="cnpq.br")
        msg.set_content(corpo, subtype="html" if html else "plain", charset="utf-8")

        mime_bytes = msg.as_bytes()
        wbxml = build_sendmail_wbxml(
            mime_bytes=mime_bytes,
            salvar_itens_enviados=salvar_itens_enviados,
        )
        status, _, resp_body = self._post_activesync("SendMail", wbxml)
        # No EAS 14.1, SendMail com sucesso retorna HTTP 200 com corpo vazio (0 bytes).
        if status == 200 and not resp_body:
            return True
        events = decode_wbxml(resp_body)
        for ev_type, tag, text in events:
            if ev_type == "TEXT" and tag == "Status" and text != "1":
                raise ZimbraError(f"Falha ao enviar e-mail via ActiveSync (Status WBXML={text}).")
        return True
