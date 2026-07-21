"""Configuração de envio de e-mail e cifragem do segredo.

O que estes testes guardam, sobretudo, é o alcance da proteção: a senha não pode
aparecer em claro no banco, nem voltar para a tela, nem entrar no pacote de
backup. O que eles **não** afirmam é que o segredo resista ao comprometimento do
servidor — não resiste, e o docstring de `services/cripto.py` explica por quê.
"""
import json
import smtplib
import zipfile
from io import BytesIO

import pytest

from app.extensions import db
from app.models import ConfiguracaoEmail
from app.services import backup, cripto
from app.services import email as email_service
from app.services.cripto import SegredoIlegivel

from tests.conftest import login

SENHA_APP = "abcd efgh ijkl mnop"


def _configurar(ativo=True, usuario="ariadne.sistema@gmail.com"):
    config = ConfiguracaoEmail.vigente()
    config.ativo = ativo
    config.usuario = usuario
    config.senha_cifrada = cripto.cifrar(SENHA_APP)
    db.session.commit()
    return config


# --- cifragem ---


def test_ida_e_volta(app):
    assert cripto.decifrar(cripto.cifrar(SENHA_APP)) == SENHA_APP


def test_cifrado_nao_contem_o_texto_claro(app):
    cifrado = cripto.cifrar(SENHA_APP)
    assert SENHA_APP not in cifrado
    assert "abcd" not in cifrado


def test_cifragens_sucessivas_diferem(app):
    """Fernet inclui vetor de inicialização: dois cifrados do mesmo texto não
    coincidem, de modo que a igualdade de dois campos não denuncia senhas iguais."""
    assert cripto.cifrar(SENHA_APP) != cripto.cifrar(SENHA_APP)


def test_chave_trocada_nao_decifra_e_nao_estoura(app):
    """Trocar SECRET_KEY torna o guardado ilegível. Precisa virar mensagem ao
    administrador, nunca erro 500."""
    cifrado = cripto.cifrar(SENHA_APP)
    app.config["SECRET_KEY"] = "outra-chave-completamente-diferente"
    with pytest.raises(SegredoIlegivel):
        cripto.decifrar(cifrado)


def test_adulteracao_e_detectada(app):
    """Fernet é autenticado: byte trocado no cifrado é recusado, não devolve
    texto corrompido."""
    cifrado = cripto.cifrar(SENHA_APP)
    adulterado = cifrado[:-6] + ("A" if cifrado[-6] != "A" else "B") + cifrado[-5:]
    with pytest.raises(SegredoIlegivel):
        cripto.decifrar(adulterado)


# --- o segredo não escapa ---


def test_senha_nao_fica_em_claro_no_banco(client, admin):
    _configurar()
    linha = db.session.execute(
        db.text("SELECT senha_cifrada FROM configuracao_email WHERE id = 1")
    ).scalar()
    assert SENHA_APP not in linha


def test_senha_nao_volta_para_a_tela(client, admin):
    _configurar()
    login(client, "admin@teste.br")
    pagina = client.get("/admin/email").data.decode()
    assert SENHA_APP not in pagina
    assert "abcd" not in pagina
    # a conta, essa sim, aparece — é o que o administrador precisa conferir
    assert "ariadne.sistema@gmail.com" in pagina


def test_senha_nao_entra_no_pacote_de_backup(client, admin):
    """A via de vazamento mais provável do sistema é o pacote levado para fora,
    não a invasão. Por isso `configuracao_email` está fora de ORDEM_TABELAS."""
    _configurar()
    login(client, "admin@teste.br")
    _nome, pacote = backup.gerar()

    assert "configuracao_email" not in backup.ORDEM_TABELAS
    with zipfile.ZipFile(BytesIO(pacote)) as z:
        for nome in z.namelist():
            bruto = z.read(nome)
            assert SENHA_APP.encode() not in bruto
            assert b"configuracao_email" not in bruto


def test_trilha_registra_a_mudanca_e_nao_o_segredo(client, admin):
    from app.models import LogAuditoria

    login(client, "admin@teste.br")
    client.post(
        "/admin/email",
        data={
            "ativo": "y",
            "servidor": "smtp.gmail.com",
            "porta": "587",
            "usuario": "ariadne.sistema@gmail.com",
            "senha": SENHA_APP,
            "remetente_nome": "ARIADNE",
        },
        follow_redirects=True,
    )
    registro = LogAuditoria.query.filter_by(acao="configuracao_email").one()
    dados = json.loads(registro.dados_json)
    assert dados["senha_alterada"] is True
    assert SENHA_APP not in registro.dados_json


# --- comportamento do formulário ---


def test_senha_em_branco_preserva_a_guardada(client, admin):
    _configurar()
    anterior = ConfiguracaoEmail.vigente().senha_cifrada
    login(client, "admin@teste.br")
    client.post(
        "/admin/email",
        data={
            "ativo": "y",
            "servidor": "smtp.gmail.com",
            "porta": "465",
            "usuario": "ariadne.sistema@gmail.com",
            "senha": "",  # em branco: mantém
            "remetente_nome": "ARIADNE",
        },
        follow_redirects=True,
    )
    config = ConfiguracaoEmail.vigente()
    assert config.porta == 465  # o resto mudou
    assert config.senha_cifrada == anterior  # a senha, não
    assert cripto.decifrar(config.senha_cifrada) == SENHA_APP


def test_configuracao_restrita_ao_admin(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    assert client.get("/admin/email").status_code == 403


# --- envio ---


def test_envio_sem_configuracao_nao_estoura(client, admin):
    """Falha de e-mail não pode derrubar a operação que o disparou."""
    assert email_service.enviar("x@y.br", "assunto", "corpo") is False


def test_envio_desabilitado_nao_tenta_conectar(client, admin, monkeypatch):
    _configurar(ativo=False)

    def nao_deveria(*a, **k):
        raise AssertionError("não deveria abrir conexão com o envio desabilitado")

    monkeypatch.setattr(smtplib, "SMTP", nao_deveria)
    monkeypatch.setattr(smtplib, "SMTP_SSL", nao_deveria)
    assert email_service.enviar("x@y.br", "assunto", "corpo") is False


def test_falha_de_rede_e_engolida_pelo_envio(client, admin, monkeypatch):
    _configurar()
    monkeypatch.setattr(
        email_service, "_entregar",
        lambda *a, **k: (_ for _ in ()).throw(OSError("rede fora")),
    )
    assert email_service.enviar("x@y.br", "assunto", "corpo") is False


def test_teste_explica_credencial_recusada(client, admin, monkeypatch):
    """Ao contrário de `enviar`, o teste precisa dizer o motivo — o
    administrador está justamente descobrindo se funciona."""
    _configurar()
    monkeypatch.setattr(
        email_service, "_entregar",
        lambda *a, **k: (_ for _ in ()).throw(
            smtplib.SMTPAuthenticationError(535, b"denied")
        ),
    )
    mensagem = email_service.testar("x@y.br")
    assert "senha de app" in mensagem


def test_teste_explica_chave_trocada(client, admin, monkeypatch):
    _configurar()
    monkeypatch.setattr(
        email_service, "_entregar",
        lambda *a, **k: (_ for _ in ()).throw(SegredoIlegivel("x")),
    )
    assert "SECRET_KEY" in email_service.testar("x@y.br")


def test_remetente_usa_nome_e_conta_configurados(client, admin, monkeypatch):
    config = _configurar()
    config.remetente_nome = "ARIADNE — Orientação"
    db.session.commit()

    capturadas = {}

    class FalsoSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, **k):
            pass

        def login(self, u, s):
            capturadas["login"] = (u, s)

        def send_message(self, m):
            capturadas["from"] = m["From"]

    monkeypatch.setattr(smtplib, "SMTP", FalsoSMTP)
    assert email_service.enviar("destino@x.br", "assunto", "corpo") is True
    assert capturadas["from"] == "ARIADNE — Orientação <ariadne.sistema@gmail.com>"
    assert capturadas["login"] == ("ariadne.sistema@gmail.com", SENHA_APP)
