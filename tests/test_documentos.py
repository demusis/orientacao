from app.models import Documento, VersaoDocumento
from tests.conftest import login, pdf_falso, texto_com_extensao_pdf


def _criar_documento(client, orientacao, arquivo, titulo="Capítulo 1"):
    return client.post(
        f"/orientacoes/{orientacao.id}/documentos/novo",
        data={"titulo": titulo, "marco_id": 0, "arquivo": arquivo, "comentario": ""},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def test_upload_valido_cria_versao_1(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    resp = _criar_documento(client, orientacao, pdf_falso())
    assert resp.status_code == 200
    doc = Documento.query.one()
    assert doc.versao_atual.numero_versao == 1
    assert doc.versao_atual.nome_original == "arquivo.pdf"
    assert doc.versao_atual.nome_fisico != "arquivo.pdf"  # armazenado sob UUID


def test_nova_versao_incrementa_numeracao(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    _criar_documento(client, orientacao, pdf_falso())
    doc = Documento.query.one()
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("arquivo-v2.pdf"), "comentario": "revisão"},
        content_type="multipart/form-data",
    )
    assert doc.versao_atual.numero_versao == 2
    assert VersaoDocumento.query.count() == 2


def test_extensao_nao_permitida_rejeitada(client, orientacao, orientando):
    import io

    login(client, "orientando@teste.br")
    _criar_documento(client, orientacao, (io.BytesIO(b"MZ"), "virus.exe"))
    assert Documento.query.count() == 0


def test_assinatura_divergente_rejeitada(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    resp = _criar_documento(client, orientacao, texto_com_extensao_pdf())
    assert "não corresponde".encode() in resp.data
    assert Documento.query.count() == 0


def test_download_negado_a_nao_envolvido(client, orientacao, orientando, intruso):
    login(client, "orientando@teste.br")
    _criar_documento(client, orientacao, pdf_falso())
    doc = Documento.query.one()
    versao = doc.versao_atual

    client.post("/auth/logout")
    login(client, "intruso@teste.br")
    resp = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{versao.id}/download"
    )
    assert resp.status_code == 403


def test_download_autorizado_retorna_arquivo(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    _criar_documento(client, orientacao, pdf_falso())
    doc = Documento.query.one()
    resp = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{doc.versao_atual.id}/download"
    )
    assert resp.status_code == 200
    assert resp.data.startswith(b"%PDF")
