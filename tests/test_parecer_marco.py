"""P-6: ao emitir parecer favorável numa versão cujo documento cumpre um marco,
o marco pode ser concluído no mesmo passo. Resultado desfavorável nunca conclui."""
import html
import re
from datetime import UTC, date, datetime, timedelta

from app.extensions import db
from app.models import Documento, Marco, Parecer, VersaoDocumento
from tests.conftest import login, pdf_falso


def _montar_entrega_de_marco(orientacao, orientando):
    """Cria um marco, um documento ligado a ele e uma versão — a entrega que o
    parecer vai apreciar."""
    marco = Marco(
        orientacao_id=orientacao.id,
        titulo="Exame de qualificação",
        tipo="qualificacao",
        etapa=40,
        data_prevista=date(2027, 3, 1),
    )
    db.session.add(marco)
    db.session.flush()
    documento = Documento(
        orientacao_id=orientacao.id,
        marco_id=marco.id,
        titulo="Texto de qualificação",
        criado_por=orientando.id,
    )
    db.session.add(documento)
    db.session.flush()
    versao = VersaoDocumento(
        documento_id=documento.id,
        numero_versao=1,
        nome_original="qualificacao.pdf",
        nome_fisico="a" * 32 + ".pdf",
        tamanho_bytes=10,
        mimetype="application/pdf",
        enviado_por=orientando.id,
    )
    db.session.add(versao)
    db.session.commit()
    return marco, versao


def _emitir(client, orientacao, versao, *, resultado, concluir):
    dados = {
        "tipo": "documento",
        "versao_documento_id": versao.id,
        "conteudo": "Apreciação do texto.",
        "resultado": resultado,
    }
    if concluir:
        dados["concluir_marco"] = "y"
    return client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo", data=dados, follow_redirects=True
    )


def test_parecer_aprovado_conclui_marco_vinculado(client, orientacao, orientando):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    login(client, "orientador@teste.br")
    r = _emitir(client, orientacao, versao, resultado="aprovado", concluir=True)
    assert r.status_code == 200
    assert db.session.get(Marco, marco.id).status == "concluido"


def test_parecer_reprovado_nao_conclui_marco(client, orientacao, orientando):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    login(client, "orientador@teste.br")
    _emitir(client, orientacao, versao, resultado="reprovado", concluir=True)
    assert db.session.get(Marco, marco.id).status != "concluido"


def test_sem_checkbox_nao_conclui_marco(client, orientacao, orientando):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    login(client, "orientador@teste.br")
    _emitir(client, orientacao, versao, resultado="aprovado", concluir=False)
    assert db.session.get(Marco, marco.id).status != "concluido"


def test_confirmar_marco_tira_versao_da_fila_de_parecer(
    client, orientacao, orientador, orientando
):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    marco.conclusao_sinalizada = True
    marco.status = "em_andamento"
    db.session.commit()

    login(client, "orientador@teste.br")
    assert f"versao={versao.id}" in client.get("/dashboard").data.decode()

    client.post(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/confirmar")
    assert db.session.get(Marco, marco.id).status == "concluido"
    assert "Emitir parecer" not in client.get("/dashboard").data.decode()


def test_devolver_marco_so_com_nota_tira_versao_da_fila_ate_novo_envio(
    client, orientacao, orientador, orientando
):
    marco, v1 = _montar_entrega_de_marco(orientacao, orientando)
    v1.enviado_em = datetime.now(UTC) - timedelta(hours=1)
    marco.conclusao_sinalizada = True
    marco.status = "em_andamento"
    db.session.commit()

    login(client, "orientador@teste.br")
    assert f"versao={v1.id}" in client.get("/dashboard").data.decode()

    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "Ajustar introdução"},
    )
    assert f"versao={v1.id}" not in client.get("/dashboard").data.decode()

    client.post("/auth/logout")
    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/anexar",
        data={
            "destino": str(v1.documento_id),
            "arquivo": pdf_falso("v2.pdf"),
            "comentario": "",
            "sinalizar": "y",
        },
        content_type="multipart/form-data",
    )
    v2 = v1.documento.versao_atual
    assert v2.numero_versao == 2

    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    assert f"versao={v2.id}" in client.get("/dashboard").data.decode()


def test_parecer_reprovado_devolve_marco_automaticamente(
    client, orientacao, orientador, orientando
):
    marco, versao = _montar_entrega_de_marco(orientacao, orientando)
    marco.conclusao_sinalizada = True
    marco.status = "em_andamento"
    db.session.commit()

    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={versao.id}",
        data={
            "tipo": "documento",
            "versao_documento_id": versao.id,
            "conteudo": "Faltam referências essenciais.",
            "resultado": "reprovado",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "devolvida para revisão" in resp.data.decode()
    marco_atual = db.session.get(Marco, marco.id)
    assert marco_atual.status == "em_andamento"
    assert marco_atual.aguardando == "orientando_revisao"
    assert marco_atual.conclusao_sinalizada is False
    assert marco_atual.nota_devolucao == "Faltam referências essenciais."


def test_parecer_aprovado_conclui_tarefa_de_revisao(
    client, orientacao, orientador, orientando
):
    marco_orig, v1 = _montar_entrega_de_marco(orientacao, orientando)
    marco_orig.status = "concluido"
    marco_orig.data_conclusao = date.today()
    v1.enviado_em = datetime.now(UTC) - timedelta(days=2)
    doc = v1.documento
    marco_rev = Marco(
        orientacao_id=orientacao.id,
        titulo="Revisar qualificação",
        tipo="qualificacao",
        etapa=40,
        data_prevista=date(2027, 4, 1),
        entrega_esperada="revisao",
        documento_base_id=doc.id,
        criado_em=datetime.now(UTC) - timedelta(days=1),
    )
    db.session.add(marco_rev)
    db.session.commit()

    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco_rev.id}/anexar",
        data={
            "destino": str(doc.id),
            "arquivo": pdf_falso("qualif-rev.pdf"),
            "comentario": "",
            "sinalizar": "y",
        },
        content_type="multipart/form-data",
    )
    v2 = doc.versao_atual

    client.post("/auth/logout")
    login(client, "orientador@teste.br")
    tela = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={v2.id}"
    ).data.decode()
    assert f"fecha o marco: {marco_rev.titulo}" in tela
    marcado = re.search(r'<input[^>]*id="concluir_marco"[^>]*>', tela)
    assert marcado and "checked" in marcado.group(0)

    _emitir(client, orientacao, v2, resultado="aprovado", concluir=True)
    assert db.session.get(Marco, marco_rev.id).status == "concluido"


def test_envio_pela_aba_documentos_sinaliza_marco_vinculado(
    client, orientacao, orientando
):
    marco1 = Marco(
        orientacao_id=orientacao.id,
        titulo="Capítulo 1",
        data_prevista=date(2027, 5, 1),
    )
    marco2 = Marco(
        orientacao_id=orientacao.id,
        titulo="Capítulo 2",
        data_prevista=date(2027, 6, 1),
    )
    db.session.add_all([marco1, marco2])
    db.session.commit()

    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/novo",
        data={
            "titulo": "Texto do Cap 1",
            "marco_id": marco1.id,
            "arquivo": pdf_falso("cap1.pdf"),
            "comentario": "",
            "sinalizar": "y",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert db.session.get(Marco, marco1.id).conclusao_sinalizada is True

    doc2 = Documento(
        orientacao_id=orientacao.id,
        marco_id=marco2.id,
        titulo="Texto do Cap 2",
        criado_por=orientando.id,
    )
    db.session.add(doc2)
    db.session.flush()
    db.session.add(
        VersaoDocumento(
            documento_id=doc2.id,
            numero_versao=1,
            nome_original="cap2-v1.pdf",
            nome_fisico="b" * 32 + ".pdf",
            tamanho_bytes=10,
            mimetype="application/pdf",
            enviado_por=orientando.id,
        )
    )
    db.session.commit()

    pagina_doc2 = html.unescape(
        client.get(f"/orientacoes/{orientacao.id}/documentos/{doc2.id}").data.decode()
    )
    assert f'entrega da tarefa "{marco2.titulo}"' in pagina_doc2

    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc2.id}",
        data={
            "arquivo": pdf_falso("cap2-v2.pdf"),
            "comentario": "Versão pronta",
            "sinalizar": "y",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert db.session.get(Marco, marco2.id).conclusao_sinalizada is True


def test_visibilidade_unificada_entre_documento_parecer_e_cronograma(
    client, orientacao, orientador, orientando
):
    marco, v1 = _montar_entrega_de_marco(orientacao, orientando)
    marco.conclusao_sinalizada = True
    marco.status = "em_andamento"
    db.session.commit()
    doc = v1.documento

    login(client, "orientador@teste.br")
    # página da tarefa oferece atalho de parecer formal sobre a entrega sinalizada
    tarefa_html = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert f"pareceres/novo?versao={v1.id}" in tarefa_html

    # parecer sobre v1 (versão corrente) aparece na listagem de documentos e na tarefa
    db.session.add(
        Parecer(
            orientacao_id=orientacao.id,
            versao_documento_id=v1.id,
            tipo="documento",
            conteudo="Bom avanço.",
            resultado="aprovado_com_ressalvas",
            emitido_por=orientador.id,
        )
    )
    db.session.commit()

    docs_lista_html = client.get(
        f"/orientacoes/{orientacao.id}/documentos/"
    ).data.decode()
    assert marco.titulo in docs_lista_html
    assert f"/cronograma/{marco.id}" in docs_lista_html
    assert "Aprovado com ressalvas" in docs_lista_html

    tarefa_com_parecer = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "parecer: Aprovado com ressalvas" in tarefa_com_parecer

    # devolução com arquivo + nota aparece na linha do tempo do documento
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={
            "nota": "Corrigir tabela 1",
            "documento_id": str(doc.id),
            "arquivo": pdf_falso("anotado.pdf"),
        },
        content_type="multipart/form-data",
    )

    doc_html = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}"
    ).data.decode()
    assert "Aprovado com ressalvas" in doc_html
    assert "Ver parecer" in doc_html
    assert "Corrigir tabela 1" in doc_html
    assert f"versao={v1.id}" not in doc_html

    # cria tarefa de revisão apontando doc e verifica selo na tabela do cronograma
    marco_rev = Marco(
        orientacao_id=orientacao.id,
        titulo="Revisão pós-banca",
        data_prevista=date(2027, 7, 1),
        entrega_esperada="revisao",
        documento_base_id=doc.id,
    )
    db.session.add(marco_rev)
    db.session.commit()

    cronograma_html = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/"
    ).data.decode()
    assert f"revisão: {doc.titulo}" in cronograma_html
