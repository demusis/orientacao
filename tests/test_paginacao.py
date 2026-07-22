"""Lote 4: paginação das listagens administrativas.

A macro `paginacao_nav` foi extraída de admin/auditoria.html, que já paginava;
que a auditoria siga passando é meia prova. Aqui verifica-se que usuários e
orientações de fato paginam e que a navegação aponta para as páginas certas.
"""
from datetime import date

from app.extensions import db
from app.models import Orientacao, Usuario
from tests.conftest import _criar_usuario, login


def _muitos_usuarios(n):
    for i in range(n):
        u = Usuario(nome=f"Fulano {i:03d}", email=f"f{i}@x.br", papel="orientando")
        u.set_senha("senha-teste-123")
        db.session.add(u)
    db.session.commit()


def test_usuarios_paginam(client, admin, app):
    por_pagina = app.config["ITENS_POR_PAGINA"]
    _muitos_usuarios(por_pagina + 5)  # garante segunda página
    login(client, "admin@teste.br")

    p1 = client.get("/admin/usuarios").data.decode()
    assert "Próxima ›" in p1  # há navegação
    # a primeira página não lista todos
    assert p1.count("@x.br") <= por_pagina

    p2 = client.get("/admin/usuarios?pagina=2").data.decode()
    assert "‹ Anterior" in p2
    # páginas diferentes trazem conteúdos diferentes
    assert p1 != p2


def test_pagina_fora_do_intervalo_nao_quebra(client, admin):
    login(client, "admin@teste.br")
    # error_out=False: página inexistente devolve vazio, não 404
    assert client.get("/admin/usuarios?pagina=999").status_code == 200


def test_lista_curta_nao_mostra_navegacao(client, admin):
    login(client, "admin@teste.br")
    # só o admin cadastrado: uma página, sem navegação
    assert "Próxima ›" not in client.get("/admin/usuarios").data.decode()


def test_orientacoes_paginam(client, admin, orientador, app):
    por_pagina = app.config["ITENS_POR_PAGINA"]
    alunos = [_criar_usuario(f"Al {i}", f"al{i}@x.br", "orientando")
              for i in range(por_pagina + 3)]
    for a in alunos:
        db.session.add(Orientacao(
            orientador_id=orientador.id, orientando_id=a.id,
            modalidade="mestrado", titulo_projeto=f"Proj {a.id}",
            data_inicio=date(2026, 3, 1),
        ))
    db.session.commit()
    login(client, "admin@teste.br")

    assert "Próxima ›" in client.get("/admin/orientacoes").data.decode()
    assert client.get("/admin/orientacoes?pagina=2").status_code == 200
