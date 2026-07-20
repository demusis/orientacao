import io
import os
import sys
import tempfile
from datetime import date

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models import Orientacao, Usuario


@pytest.fixture
def app():
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = tempfile.mkdtemp(prefix="ariadne-test-uploads-")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def app_com_proxy(monkeypatch):
    """Aplicação configurada como em produção: um proxy reverso confiável à
    frente, de modo que X-Forwarded-For passe a valer como origem."""
    from config import TestingConfig

    monkeypatch.setattr(TestingConfig, "TRUSTED_PROXY_COUNT", 1, raising=False)
    app = create_app("testing")
    app.config["UPLOAD_FOLDER"] = tempfile.mkdtemp(prefix="ariadne-test-uploads-")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _criar_usuario(nome, email, papel, senha="senha-teste-123"):
    u = Usuario(nome=nome, email=email, papel=papel)
    u.set_senha(senha)
    db.session.add(u)
    db.session.commit()
    return u


@pytest.fixture
def admin(app):
    return _criar_usuario("Admin", "admin@teste.br", "admin")


@pytest.fixture
def orientador(app):
    return _criar_usuario("Orientador A", "orientador@teste.br", "orientador")


@pytest.fixture
def orientando(app):
    return _criar_usuario("Orientando B", "orientando@teste.br", "orientando")


@pytest.fixture
def intruso(app):
    """Orientando sem vínculo com a orientação de teste."""
    return _criar_usuario("Intruso C", "intruso@teste.br", "orientando")


@pytest.fixture
def orientacao(app, orientador, orientando):
    o = Orientacao(
        orientador_id=orientador.id,
        orientando_id=orientando.id,
        modalidade="mestrado",
        titulo_projeto="Projeto de Teste",
        data_inicio=date(2026, 1, 5),
    )
    db.session.add(o)
    db.session.commit()
    return o


@pytest.fixture
def orientando2(app):
    return _criar_usuario("Orientando D", "orientando2@teste.br", "orientando")


@pytest.fixture
def orientacao2(app, orientador, orientando2):
    """Segundo vínculo do mesmo orientador (cenários de reunião em grupo)."""
    o = Orientacao(
        orientador_id=orientador.id,
        orientando_id=orientando2.id,
        modalidade="doutorado",
        titulo_projeto="Segundo Projeto",
        data_inicio=date(2026, 2, 2),
    )
    db.session.add(o)
    db.session.commit()
    return o


def login(client, email, senha="senha-teste-123"):
    return client.post(
        "/auth/login", data={"email": email, "senha": senha}, follow_redirects=True
    )


def pdf_falso(nome="arquivo.pdf"):
    return (io.BytesIO(b"%PDF-1.4 conteudo de teste"), nome)


def texto_com_extensao_pdf(nome="malicioso.pdf"):
    """Extensão .pdf, conteúdo sem assinatura PDF."""
    return (io.BytesIO(b"MZ este nao e um pdf"), nome)
