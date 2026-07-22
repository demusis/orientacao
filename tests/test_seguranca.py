"""Lote 1: superfície de segurança e páginas de erro."""
from datetime import timedelta

from app.extensions import db
from app.models import LogAuditoria
from app.services.tempo import agora
from tests.conftest import login

# --- cabeçalhos ---


def test_cabecalhos_de_seguranca_presentes(client):
    r = client.get("/auth/login")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "script-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "same-origin"


def test_hsts_apenas_sob_https(client, app):
    # TestingConfig não marca SESSION_COOKIE_SECURE
    assert "Strict-Transport-Security" not in client.get("/auth/login").headers
    app.config["SESSION_COOKIE_SECURE"] = True
    assert "Strict-Transport-Security" in client.get("/auth/login").headers


def test_csp_nao_permite_inline(client):
    """A política só vale porque os templates não têm style= nem <script>; se
    alguém introduzir inline, esta garantia deixa de proteger — mas a política
    em si não pode afrouxar sozinha."""
    csp = client.get("/auth/login").headers["Content-Security-Policy"]
    assert "unsafe-inline" not in csp
    assert "unsafe-eval" not in csp


# --- páginas de erro ---


def test_404_na_identidade_do_sistema(client):
    r = client.get("/rota-que-nao-existe")
    assert r.status_code == 404
    corpo = r.data.decode()
    assert "ARIADNE" in corpo
    assert "não encontrada" in corpo
    # não vaza o traceback do Werkzeug
    assert "Traceback" not in corpo


def test_403_tem_pagina_propria(client, orientacao, intruso):
    login(client, "intruso@teste.br")
    r = client.get(f"/orientacoes/{orientacao.id}/documentos/")
    assert r.status_code == 403
    assert "Acesso negado" in r.data.decode()


def test_pagina_de_erro_funciona_sem_sessao(client):
    """403/500 podem ocorrer sem usuário; a página não pode depender do
    cabeçalho autenticado de base.html."""
    r = client.get("/inexistente")
    assert r.status_code == 404
    assert "Voltar ao início" in r.data.decode()


# --- limite de tentativas ---


def _semear_falhas(quantas, ip="127.0.0.1", acao="login_falho"):
    for _ in range(quantas):
        db.session.add(
            LogAuditoria(acao=acao, entidade="usuario", ip=ip, dados_json=None)
        )
    db.session.commit()


def test_login_bloqueia_apos_o_teto(client, app):
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    _semear_falhas(teto)

    r = client.post(
        "/auth/login",
        data={"email": "x@y.br", "senha": "qualquer"},
        follow_redirects=True,
    )
    assert r.status_code == 429
    assert "Muitas tentativas" in r.data.decode()
    assert LogAuditoria.query.filter_by(acao="login_bloqueado").count() == 1


def test_falhas_fora_da_janela_nao_contam(client, app):
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    janela = app.config["LOGIN_JANELA_MINUTOS"]
    _semear_falhas(teto)
    # empurra todas para além da janela
    antigo = agora() - timedelta(minutes=janela + 1)
    for log in LogAuditoria.query.filter_by(acao="login_falho"):
        log.timestamp = antigo
    db.session.commit()

    r = client.post(
        "/auth/login",
        data={"email": "x@y.br", "senha": "errada"},
        follow_redirects=True,
    )
    # não bloqueou: caiu no fluxo normal de credencial inválida
    assert r.status_code == 401


def test_falhas_de_outra_origem_nao_contam(client, app):
    teto = app.config["LOGIN_MAX_TENTATIVAS"]
    _semear_falhas(teto, ip="203.0.113.9")  # outro endereço

    r = client.post(
        "/auth/login",
        data={"email": "x@y.br", "senha": "errada"},
        follow_redirects=True,
    )
    assert r.status_code == 401  # a origem local ainda não estourou


# --- sessão ---


def test_login_marca_sessao_permanente(client, orientador):
    with client:
        client.post(
            "/auth/login",
            data={"email": "orientador@teste.br", "senha": "senha-teste-123"},
            follow_redirects=True,
        )
        from flask import session

        assert session.permanent is True
