"""Modelos de documento: acervo global gerido pelo admin, baixável na criação.

Cobre o envio (válido e inválido), a exclusão, a autorização (só admin gere), o
download por qualquer autenticado, a listagem na tela de novo documento e a
sobrevivência ao ciclo de backup."""
import os

from app.extensions import db
from app.models import LogAuditoria, ModeloDocumento

from tests.conftest import login, pdf_falso, texto_com_extensao_pdf


def _enviar_modelo(client, arquivo=None, titulo="Modelo de projeto", descricao="Estrutura básica"):
    return client.post(
        "/admin/modelos",
        data={"titulo": titulo, "descricao": descricao, "arquivo": arquivo or pdf_falso("modelo.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


# --- envio ---


def test_admin_envia_modelo(client, admin, app):
    login(client, "admin@teste.br")
    _enviar_modelo(client)
    modelo = ModeloDocumento.query.one()
    assert modelo.titulo == "Modelo de projeto"
    assert modelo.nome_original == "modelo.pdf"
    assert modelo.nome_fisico != "modelo.pdf"  # guardado sob UUID
    # arquivo em disco
    caminho = os.path.join(app.config["UPLOAD_FOLDER"], modelo.nome_fisico)
    assert os.path.isfile(caminho)
    assert LogAuditoria.query.filter_by(acao="criacao_modelo").count() == 1


def test_modelo_com_conteudo_invalido_e_recusado(client, admin):
    login(client, "admin@teste.br")
    _enviar_modelo(client, arquivo=texto_com_extensao_pdf())
    assert ModeloDocumento.query.count() == 0
    assert LogAuditoria.query.filter_by(acao="criacao_modelo").count() == 0


# --- exclusão ---


def test_admin_exclui_modelo(client, admin, app):
    login(client, "admin@teste.br")
    _enviar_modelo(client)
    modelo = ModeloDocumento.query.one()
    caminho = os.path.join(app.config["UPLOAD_FOLDER"], modelo.nome_fisico)

    client.post(f"/admin/modelos/{modelo.id}/excluir", follow_redirects=True)
    assert ModeloDocumento.query.count() == 0
    assert not os.path.isfile(caminho)  # arquivo físico também removido
    assert LogAuditoria.query.filter_by(acao="exclusao_modelo").count() == 1


# --- autorização ---


def test_gestao_de_modelos_restrita_ao_admin(client, orientador, orientando):
    login(client, "orientador@teste.br")
    assert client.get("/admin/modelos").status_code == 403
    assert client.post("/admin/modelos/1/excluir").status_code == 403


# --- download ---


def test_qualquer_autenticado_baixa_o_modelo(client, admin, orientando):
    login(client, "admin@teste.br")
    _enviar_modelo(client)
    modelo = ModeloDocumento.query.one()
    client.get("/auth/logout")

    login(client, "orientando@teste.br")
    resp = client.get(f"/modelos/{modelo.id}/download")
    assert resp.status_code == 200
    assert "modelo.pdf" in resp.headers.get("Content-Disposition", "")


# --- integração na criação de documento ---


def test_novo_documento_lista_os_modelos(client, admin, orientacao, orientando):
    login(client, "admin@teste.br")
    _enviar_modelo(client, titulo="Modelo de Qualificação")
    modelo = ModeloDocumento.query.one()
    client.get("/auth/logout")

    login(client, "orientando@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/documentos/novo").data.decode()
    assert "Modelos disponíveis" in pagina
    assert "Modelo de Qualificação" in pagina
    assert f"/modelos/{modelo.id}/download" in pagina


def test_sem_modelos_a_secao_nao_aparece(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    pagina = client.get(f"/orientacoes/{orientacao.id}/documentos/novo").data.decode()
    assert "Modelos disponíveis" not in pagina


# --- backup ---


def test_modelo_sobrevive_ao_backup(client, admin, app):
    """O registro e o arquivo do modelo devem voltar após apagar e restaurar,
    pelo mesmo caminho das rotas de backup."""
    import io

    login(client, "admin@teste.br")
    _enviar_modelo(client, titulo="Perene")
    nome_fisico = ModeloDocumento.query.one().nome_fisico

    pacote = client.post("/admin/backup/gerar").data
    client.post("/admin/backup/expurgar", data={"confirmacao": "APAGAR"})
    assert ModeloDocumento.query.count() == 0

    client.post(
        "/admin/backup/restaurar",
        data={"arquivo": (io.BytesIO(pacote), "b.zip"), "confirmacao": "RESTAURAR"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    restaurado = ModeloDocumento.query.filter_by(titulo="Perene").one()
    assert restaurado.nome_fisico == nome_fisico
    assert os.path.isfile(os.path.join(app.config["UPLOAD_FOLDER"], nome_fisico))
