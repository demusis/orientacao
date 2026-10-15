"""Exclusão de versão enviada por engano — e as travas que a impedem de virar
edição do histórico."""
import io
import os

from app.extensions import db
from app.models import Documento, LogAuditoria, Parecer, VersaoDocumento
from tests.conftest import login, pdf_falso
from tests.test_ciclo_revisao import _marco


def _enviar(client, orientacao, titulo="Dissertação", anexos=(), marco_id=0):
    dados = {"titulo": titulo, "marco_id": marco_id, "comentario": "",
             "arquivo": pdf_falso("texto.pdf")}
    if anexos:
        dados["anexos"] = list(anexos)
    client.post(f"/orientacoes/{orientacao.id}/documentos/novo", data=dados,
                content_type="multipart/form-data")
    return Documento.query.filter_by(titulo=titulo).one()


def _nova_versao(client, orientacao, doc):
    client.post(f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
                data={"arquivo": pdf_falso("v2.pdf"), "comentario": ""},
                content_type="multipart/form-data")
    return doc.versao_atual


def _url(orientacao, doc, versao):
    return f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{versao.id}/excluir"


def _disco(app):
    return set(os.listdir(app.config["UPLOAD_FOLDER"]))


def test_unica_versao_leva_o_documento_e_os_arquivos(client, app, orientacao, orientador):
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao, anexos=[(io.BytesIO(b"a;b"), "dados.csv")])
    versao = doc.versao_atual
    assert len(_disco(app)) == 2

    pagina = client.get(_url(orientacao, doc, versao)).data.decode()
    assert "única versão" in pagina and "dados.csv" in pagina  # mostra antes

    resp = client.post(_url(orientacao, doc, versao), follow_redirects=True)
    assert "excluído (era a única versão)" in resp.data.decode()
    assert Documento.query.count() == 0
    assert VersaoDocumento.query.count() == 0
    assert _disco(app) == set()
    registro = LogAuditoria.query.filter_by(acao="exclusao_versao_documento").one()
    assert '"documento_apagado": true' in registro.dados_json


def test_ultima_versao_volta_a_anterior(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao)
    v2 = _nova_versao(client, orientacao, doc)
    client.post(_url(orientacao, doc, v2))
    assert doc.versao_atual.numero_versao == 1
    assert Documento.query.count() == 1


def test_link_so_na_versao_mais_recente_e_para_quem_enviou(
    client, orientacao, orientador, orientando
):
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao)
    v2 = _nova_versao(client, orientacao, doc)
    pagina = client.get(f"/orientacoes/{orientacao.id}/documentos/{doc.id}").data.decode()
    assert _url(orientacao, doc, v2) in pagina
    assert pagina.count("Excluir esta versão") == 1

    client.post("/auth/logout")
    login(client, "orientando@teste.br")  # não enviou: sem link, e a rota recusa
    pagina = client.get(f"/orientacoes/{orientacao.id}/documentos/{doc.id}").data.decode()
    assert "Excluir esta versão" not in pagina
    resp = client.post(_url(orientacao, doc, v2), follow_redirects=True)
    assert "Só quem enviou" in resp.data.decode()
    assert doc.versoes.count() == 2
    assert LogAuditoria.query.filter_by(acao="exclusao_versao_recusada").count() == 1


def test_versao_antiga_recusada(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao)
    v1 = doc.versao_atual
    _nova_versao(client, orientacao, doc)
    resp = client.post(_url(orientacao, doc, v1), follow_redirects=True)
    assert "mais recente" in resp.data.decode()
    assert doc.versoes.count() == 2


def test_versao_com_parecer_recusada(client, orientacao, orientador, orientando):
    login(client, "orientando@teste.br")
    doc = _enviar(client, orientacao)
    versao = doc.versao_atual
    db.session.add(Parecer(orientacao_id=orientacao.id, versao_documento_id=versao.id,
                           tipo="documento", conteudo="ok", resultado="aprovado",
                           emitido_por=orientador.id))
    db.session.commit()
    resp = client.post(_url(orientacao, doc, versao), follow_redirects=True)
    assert "já recebeu parecer" in resp.data.decode()
    assert Documento.query.count() == 1


def test_devolucao_recusada(client, orientacao, orientador):
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao)
    doc.versao_atual.eh_devolucao = True
    db.session.commit()
    resp = client.post(_url(orientacao, doc, doc.versao_atual), follow_redirects=True)
    assert "devolução" in resp.data.decode()
    assert Documento.query.count() == 1


def test_tarefa_concluida_recusa(client, orientacao, orientador):
    marco = _marco(orientacao)
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao, marco_id=marco.id)
    marco.status = "concluido"
    db.session.commit()
    resp = client.post(_url(orientacao, doc, doc.versao_atual), follow_redirects=True)
    assert "concluída" in resp.data.decode()
    assert Documento.query.count() == 1


def test_entrega_sob_sinalizacao_recusa(client, orientacao, orientando):
    marco = _marco(orientacao, sinalizado=True)
    login(client, "orientando@teste.br")
    doc = _enviar(client, orientacao, marco_id=marco.id)
    resp = client.post(_url(orientacao, doc, doc.versao_atual), follow_redirects=True)
    assert "aguarda o orientador" in resp.data.decode()
    assert Documento.query.count() == 1


def test_orientanda_exclui_o_proprio_envio_antes_de_sinalizar(client, orientacao, orientando):
    marco = _marco(orientacao)
    login(client, "orientando@teste.br")
    doc = _enviar(client, orientacao, marco_id=marco.id)
    client.post(_url(orientacao, doc, doc.versao_atual))
    assert Documento.query.count() == 0


def test_admin_pode_excluir_envio_alheio(client, orientacao, orientador, admin):
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao)
    client.post("/auth/logout")
    login(client, "admin@teste.br")
    client.post(_url(orientacao, doc, doc.versao_atual))
    assert Documento.query.count() == 0


def test_intruso_nao_alcanca(client, orientacao, orientador, intruso):
    login(client, "orientador@teste.br")
    doc = _enviar(client, orientacao)
    client.post("/auth/logout")
    login(client, "intruso@teste.br")
    assert client.post(_url(orientacao, doc, doc.versao_atual)).status_code == 403
    assert Documento.query.count() == 1
