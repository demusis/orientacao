"""Vários arquivos numa versão: o principal (o texto que o parecer avalia) e os
anexos que o acompanham — planilha, figuras, carta."""
import io
import os
import zipfile

from app.extensions import db
from app.models import AnexoVersao, Documento, Parecer, VersaoDocumento
from app.services import eliminacao
from tests.conftest import login, pdf_falso, texto_com_extensao_pdf


def _txt(nome):
    return (io.BytesIO(b"dados;valores\n1;2\n"), nome)


def _criar(client, orientacao, arquivo, anexos=(), titulo="Capítulo 2"):
    dados = {"titulo": titulo, "marco_id": 0, "comentario": "", "arquivo": arquivo}
    if anexos:
        dados["anexos"] = list(anexos)
    return client.post(
        f"/orientacoes/{orientacao.id}/documentos/novo",
        data=dados,
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _arquivos_no_disco(app):
    return set(os.listdir(app.config["UPLOAD_FOLDER"]))


def test_principal_e_anexos_na_mesma_versao(client, app, orientacao, orientando):
    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("capitulo2.pdf"),
           [_txt("tabela.txt"), pdf_falso("figura.pdf")])

    versao = Documento.query.one().versao_atual
    assert versao.nome_original == "capitulo2.pdf"  # o principal fica na versão
    assert [a.nome_original for a in versao.anexos] == ["tabela.txt", "figura.pdf"]
    assert versao.quantidade_arquivos == 3
    assert len(_arquivos_no_disco(app)) == 3

    pagina = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{versao.documento_id}"
    ).data.decode()
    assert "Principal:" in pagina
    assert "tabela.txt" in pagina and "figura.pdf" in pagina


def test_sem_anexos_segue_como_antes(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("unico.pdf"))
    versao = Documento.query.one().versao_atual
    assert versao.anexos == []
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{versao.documento_id}"
    ).data.decode()
    assert "Arquivo: unico.pdf" in pagina
    assert "Principal:" not in pagina


def test_anexos_sem_principal_sao_recusados(client, app, orientacao, orientando):
    login(client, "orientando@teste.br")
    resp = _criar(client, orientacao, None, [pdf_falso("solto.pdf")])
    assert "acompanham um arquivo principal" in resp.data.decode()
    assert Documento.query.count() == 0
    assert _arquivos_no_disco(app) == set()


def test_um_anexo_invalido_derruba_o_envio_inteiro(client, app, orientacao, orientando):
    """Valida todos antes de gravar: nada fica pela metade no disco."""
    login(client, "orientando@teste.br")
    resp = _criar(client, orientacao, pdf_falso("ok.pdf"),
                  [pdf_falso("ok2.pdf"), texto_com_extensao_pdf("falso.pdf")])
    corpo = resp.data.decode()
    assert "falso.pdf" in corpo and "não corresponde" in corpo
    assert Documento.query.count() == 0
    assert VersaoDocumento.query.count() == 0
    assert _arquivos_no_disco(app) == set()


def test_limite_de_arquivos_por_versao(client, orientacao, orientando):
    from app.services.uploads import MAX_ARQUIVOS_POR_VERSAO

    login(client, "orientando@teste.br")
    anexos = [pdf_falso(f"a{i}.pdf") for i in range(MAX_ARQUIVOS_POR_VERSAO)]
    resp = _criar(client, orientacao, pdf_falso("p.pdf"), anexos)
    assert f"no máximo {MAX_ARQUIVOS_POR_VERSAO} arquivos" in resp.data.decode()
    assert Documento.query.count() == 0


def test_nova_versao_com_anexos(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("v1.pdf"))
    doc = Documento.query.one()
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("v2.pdf"), "anexos": [_txt("dados.txt")],
              "comentario": "com os dados"},
        content_type="multipart/form-data",
    )
    v2 = doc.versao_atual
    assert v2.numero_versao == 2
    assert [a.nome_original for a in v2.anexos] == ["dados.txt"]


def test_download_do_anexo_e_controle_de_acesso(client, orientacao, orientando, intruso):
    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("p.pdf"), [_txt("dados.txt")])
    versao = Documento.query.one().versao_atual
    anexo = versao.anexos[0]
    base = f"/orientacoes/{orientacao.id}/documentos/{versao.documento_id}/versoes"

    resp = client.get(f"{base}/{versao.id}/anexos/{anexo.id}/download")
    assert resp.status_code == 200
    assert resp.data.startswith(b"dados;valores")
    assert "dados.txt" in resp.headers["Content-Disposition"]

    # o anexo só é alcançável pela própria versão
    assert client.get(f"{base}/{versao.id + 1}/anexos/{anexo.id}/download").status_code == 404

    client.post("/auth/logout")
    login(client, "intruso@teste.br")
    assert client.get(f"{base}/{versao.id}/anexos/{anexo.id}/download").status_code == 403


def test_parecer_mostra_os_anexos(client, orientacao, orientando, orientador):
    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("p.pdf"), [_txt("dados.txt")])
    versao = Documento.query.one().versao_atual
    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    pagina = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={versao.id}"
    ).data.decode()
    assert "dados.txt" in pagina


def test_eliminacao_lgpd_recolhe_os_anexos(client, app, orientacao, orientando, admin):
    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("p.pdf"), [_txt("dados.txt")])
    client.post("/auth/logout")
    versao = Documento.query.one().versao_atual
    fisico_anexo = versao.anexos[0].nome_fisico

    resumo = eliminacao.eliminar_usuario(orientando, admin)
    db.session.commit()
    assert fisico_anexo in resumo["arquivos"]
    assert versao.nome_fisico in resumo["arquivos"]
    assert AnexoVersao.query.count() == 0


def test_backup_leva_os_anexos_e_restaura(client, app, admin, orientacao, orientando):
    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("p.pdf"), [_txt("dados.txt")])
    client.post("/auth/logout")
    login(client, "admin@teste.br")
    pacote = client.post("/admin/backup/gerar").data
    with zipfile.ZipFile(io.BytesIO(pacote)) as z:
        assert "dados/anexo_versao.json" in z.namelist()
        assert sum(n.startswith("uploads/") for n in z.namelist()) == 2

    client.post("/admin/backup/expurgar", data={"confirmacao": "APAGAR"})
    assert AnexoVersao.query.count() == 0
    client.post(
        "/admin/backup/restaurar",
        data={"arquivo": (io.BytesIO(pacote), "b.zip"), "confirmacao": "RESTAURAR"},
        content_type="multipart/form-data",
    )
    anexo = AnexoVersao.query.one()
    assert anexo.nome_original == "dados.txt"
    assert anexo.nome_fisico in _arquivos_no_disco(app)


def test_versao_com_anexos_segue_pedindo_um_parecer(client, orientacao, orientando, orientador):
    """O parecer é da versão (o principal); os anexos não geram pendências
    próprias."""
    from app.services import indicadores

    login(client, "orientando@teste.br")
    _criar(client, orientacao, pdf_falso("p.pdf"), [_txt("a.txt"), _txt("b.txt")])
    assert indicadores.documentos()["versoes_correntes_sem_parecer"] == 1
    versao = Documento.query.one().versao_atual
    db.session.add(Parecer(orientacao_id=orientacao.id, versao_documento_id=versao.id,
                           tipo="documento", conteudo="ok", resultado="aprovado",
                           emitido_por=orientador.id))
    db.session.commit()
    assert indicadores.documentos()["versoes_correntes_sem_parecer"] == 0


def test_devolver_com_arquivo_corrigido_e_anexos(client, orientacao, orientador):
    from tests.test_ciclo_revisao import _documento_com_v1, _marco

    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "veja as marcações", "documento_id": str(doc.id),
              "arquivo": pdf_falso("anotado.pdf"), "anexos": [_txt("tabela.txt")]},
        content_type="multipart/form-data",
    )
    nova = doc.versoes.first()
    assert nova.eh_devolucao is True
    assert [a.nome_original for a in nova.anexos] == ["tabela.txt"]


def test_devolver_com_anexos_sem_arquivo_corrigido_nao_devolve(client, orientacao, orientador):
    """Anexo solto não se perde em silêncio: recusa o ato inteiro."""
    from tests.test_ciclo_revisao import _documento_com_v1, _marco

    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "x", "documento_id": str(doc.id), "anexos": [_txt("t.txt")]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Nada foi devolvido" in resp.data.decode()
    db.session.expire(marco)
    assert marco.aguardando == "orientador"
    assert doc.versoes.count() == 1
