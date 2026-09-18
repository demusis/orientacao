"""Ciclo de revisão do marco: devolução para revisão, "de quem é a vez" e
atribuição de autoria das versões. Cobre o cenário que motivou a mudança — o
orientador devolve a v2 com anotações e a tarefa deve voltar ao orientando."""
from datetime import date

from app.extensions import db
from app.models import Documento, LogAuditoria, Marco, VersaoDocumento
from app.services import cronogramas as servico_cronograma
from tests.conftest import login, pdf_falso


def _marco(orientacao, *, sinalizado=False):
    m = Marco(
        orientacao_id=orientacao.id,
        titulo="Revisão da metodologia",
        data_prevista=date(2026, 8, 3),
    )
    if sinalizado:
        m.conclusao_sinalizada = True
        m.status = "em_andamento"
    db.session.add(m)
    db.session.commit()
    return m


def _documento_com_v1(orientacao, marco, enviado_por):
    doc = Documento(
        orientacao_id=orientacao.id,
        marco_id=marco.id,
        titulo="Revisão da metodologia",
        criado_por=enviado_por,
    )
    db.session.add(doc)
    db.session.flush()
    v = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=1,
        nome_original="rev.pdf",
        nome_fisico=f"{doc.id:032x}.pdf",
        tamanho_bytes=1024,
        mimetype="application/pdf",
        enviado_por=enviado_por,
    )
    db.session.add(v)
    db.session.commit()
    return doc


# --- serviço: devolver_para_revisao ---


def test_devolver_reseta_sinal_e_marca_devolucao(app, orientacao):
    marco = _marco(orientacao, sinalizado=True)
    assert marco.aguardando == "orientador"

    assert servico_cronograma.devolver_para_revisao(marco, "Falta discutir o vício") is True
    db.session.commit()

    assert marco.conclusao_sinalizada is False
    assert marco.status == "em_andamento"
    assert marco.devolvido_em is not None
    assert marco.nota_devolucao == "Falta discutir o vício"
    assert marco.aguardando == "orientando_revisao"
    assert LogAuditoria.query.filter_by(acao="devolucao_revisao_marco").count() == 1


def test_devolver_recusa_marco_concluido(app, orientacao):
    marco = _marco(orientacao)
    marco.status = "concluido"
    db.session.commit()
    assert servico_cronograma.devolver_para_revisao(marco) is False


def test_re_sinalizar_devolve_a_vez_ao_orientador(app, orientacao):
    marco = _marco(orientacao, sinalizado=True)
    servico_cronograma.devolver_para_revisao(marco, "corrija")
    db.session.commit()
    # aluno re-sinaliza: a vez volta ao orientador, devolvido_em fica de histórico
    marco.conclusao_sinalizada = True
    db.session.commit()
    assert marco.aguardando == "orientador"
    assert marco.devolvido_em is not None


# --- rota dedicada + RBAC ---


def test_rota_devolver_pelo_orientador(client, orientacao, orientador):
    marco = _marco(orientacao, sinalizado=True)
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "Revise o capítulo 2"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.expire(marco)
    assert marco.conclusao_sinalizada is False
    assert marco.aguardando == "orientando_revisao"


def test_rota_devolver_negada_ao_orientando(client, orientacao, orientando):
    marco = _marco(orientacao, sinalizado=True)
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "x"},
    )
    assert resp.status_code == 403
    db.session.expire(marco)
    assert marco.conclusao_sinalizada is True  # nada mudou


# --- nova versão do orientando não devolve ---
# (a devolução por upload do orientador é coberta em
#  test_nova_versao_como_devolucao_* / _como_entrega_*, agora por intenção
#  explícita — não mais pela identidade de quem envia)


def test_nova_versao_do_orientando_nao_devolve(client, orientacao, orientando):
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("v2.pdf"), "comentario": "corrigido"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.expire(marco)
    # reenvio do próprio aluno não vira devolução; segue sinalizado
    assert marco.conclusao_sinalizada is True
    assert marco.devolvido_em is None


# --- painel e avisos ---


def test_painel_move_devolvido_para_tarefas_abertas(app, client, orientacao, orientador):
    from app.services import painel

    marco = _marco(orientacao, sinalizado=True)
    servico_cronograma.devolver_para_revisao(marco, "ajuste")
    db.session.commit()

    login(client, "orientador@teste.br")
    with client.application.test_request_context():
        from flask_login import login_user

        login_user(orientador)
        pend = painel.pendencias()
    ids_confirmar = [m.id for m in pend["entregas_a_confirmar"]]
    ids_abertas = [m.id for m in pend["tarefas_abertas"]]
    assert marco.id not in ids_confirmar  # saiu da lista de confirmações
    assert marco.id in ids_abertas


def test_aviso_de_marco_devolvido_vai_ao_orientando(app, orientacao, orientando):
    from app.services import avisos

    marco = _marco(orientacao, sinalizado=True)
    servico_cronograma.devolver_para_revisao(marco, "ajuste")
    db.session.commit()

    coletado = avisos.coletar()
    assert orientando in coletado
    assert "marcos_devolvidos" in coletado[orientando]


# --- atribuição de autoria ---


def test_entregas_da_tarefa_mostram_quem_enviou(client, orientacao, orientador):
    marco = _marco(orientacao)
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientador_id)
    login(client, "orientador@teste.br")
    resp = client.get(f"/orientacoes/{orientacao.id}/cronograma/{marco.id}")
    corpo = resp.data.decode()
    assert "Enviada por" in corpo
    assert "Orientador A" in corpo  # nome do remetente (fixture)
    assert "(orientador)" in corpo


def test_parecer_form_atribui_ao_remetente_real(client, orientacao, orientador):
    """A v2 enviada pelo orientador não pode ser atribuída ao orientando na
    tela de emitir parecer."""
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientador_id)
    versao = doc.versoes.first()
    login(client, "orientador@teste.br")
    resp = client.get(
        f"/orientacoes/{orientacao.id}/pareceres/novo?versao={versao.id}"
    )
    corpo = resp.data.decode()
    assert "Enviada por Orientador A" in corpo
    assert "Orientando B" not in corpo.split("Enviada por")[1][:40]


# --- salvaguarda da incoerência + situação legível ---


def test_ultima_entrega_devolve_a_versao_mais_recente(app, orientacao):
    from datetime import UTC, datetime, timedelta

    marco = _marco(orientacao)
    assert marco.ultima_entrega is None  # sem entregas
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    v1 = doc.versoes.first()
    v1.enviado_em = datetime.now(UTC) - timedelta(days=1)
    v2 = VersaoDocumento(
        documento_id=doc.id,
        numero_versao=2,
        nome_original="anotado.pdf",
        nome_fisico=f"{doc.id:032x}b.pdf",
        tamanho_bytes=2048,
        mimetype="application/pdf",
        enviado_por=orientacao.orientador_id,
    )
    db.session.add(v2)
    db.session.commit()
    assert marco.ultima_entrega.id == v2.id  # a mais recente


def test_marco_preso_mostra_aviso_e_devolver_regulariza(client, orientacao, orientador):
    """Registro preso: sinalizado + última versão do orientador. A página exibe
    o aviso; após devolver, some e a situação vira 'aguardando o orientando'."""
    marco = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientador_id)
    login(client, "orientador@teste.br")

    corpo = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "foi enviada pelo orientador" in corpo  # aviso flash-warning
    assert "Aguardando o orientador" in corpo  # situação (autoritativa) ainda

    servico_cronograma.devolver_para_revisao(marco, "corrija")
    db.session.commit()
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "foi enviada pelo orientador" not in corpo  # aviso sumiu
    assert "aguardando o orientando" in corpo.lower()


def test_painel_marca_entrega_com_versao_do_orientador(app, client, orientacao, orientador):
    from app.services import painel

    preso = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, preso, enviado_por=orientacao.orientador_id)
    normal = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, normal, enviado_por=orientacao.orientando_id)

    with client.application.test_request_context():
        from flask_login import login_user

        login_user(orientador)
        pend = painel.pendencias()
    assert preso.id in pend["entregas_a_confirmar_revisao"]
    assert normal.id not in pend["entregas_a_confirmar_revisao"]


def test_situacao_badge_na_pagina_do_marco(client, orientacao, orientando):
    """Marco recém-criado, sem sinal: a vez é do orientando."""
    marco = _marco(orientacao)
    login(client, "orientando@teste.br")
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "Aguardando o orientando" in corpo


# --- versão como devolução (não pede parecer) ---


def _versoes_sem_parecer_ids(orientador):
    """Ids das versões que o Painel lista como aguardando parecer (contexto de
    requisição autenticado como o orientador)."""
    from flask import current_app
    from flask_login import login_user

    from app.services import painel

    with current_app.test_request_context():
        login_user(orientador)
        return {v.id for v in painel.pendencias()["versoes_sem_parecer"]}


def test_nova_versao_como_devolucao_devolve_e_sai_dos_pareceres(
    client, orientacao, orientador
):
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("anot.pdf"), "comentario": "corrigir",
              "eh_devolucao": "y"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.expire(marco)
    assert marco.aguardando == "orientando_revisao"
    nova = doc.versoes.first()
    assert nova.eh_devolucao is True
    assert nova.id not in _versoes_sem_parecer_ids(orientador)


def test_upload_do_orientador_nao_pede_parecer(client, orientacao, orientador):
    """Nada que o orientador sobe pede o parecer dele — nem sem marcar devolução.
    Só a entrega da orientanda entra em 'aguardando parecer'."""
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("v2.pdf"), "comentario": "registrando entrega"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    db.session.expire(marco)
    # sem marcar devolução: não devolve a tarefa
    assert marco.conclusao_sinalizada is True
    nova = doc.versoes.first()  # v2, enviada pelo orientador
    assert nova.eh_devolucao is False
    # e mesmo assim NÃO pede parecer dele (é upload dele, não entrega da aluna)
    assert nova.id not in _versoes_sem_parecer_ids(orientador)


def test_so_a_entrega_da_orientanda_pede_parecer(client, orientacao, orientador):
    da_aluna = _documento_com_v1(
        orientacao, _marco(orientacao), enviado_por=orientacao.orientando_id
    )
    do_orientador = _documento_com_v1(
        orientacao, _marco(orientacao), enviado_por=orientacao.orientador_id
    )
    ids = _versoes_sem_parecer_ids(orientador)
    assert da_aluna.versoes.first().id in ids
    assert do_orientador.versoes.first().id not in ids


def test_lista_de_parecer_tem_link_para_o_documento(client, orientacao, orientador):
    """A lista 'aguardando parecer' leva ao documento (onde se ajusta: marcar
    como devolução, etc.), além do atalho 'Emitir parecer'."""
    doc = _documento_com_v1(
        orientacao, _marco(orientacao), enviado_por=orientacao.orientando_id
    )
    login(client, "orientador@teste.br")
    corpo = client.get("/dashboard").data.decode()
    assert f"/orientacoes/{orientacao.id}/documentos/{doc.id}" in corpo


def test_orientando_nova_versao_nao_vira_devolucao(client, orientacao, orientando):
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientando@teste.br")
    # mesmo enviando o campo, a rota ignora para a orientanda
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("v2.pdf"), "eh_devolucao": "y"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert doc.versoes.first().eh_devolucao is False


def test_toggle_devolucao_por_versao(client, orientacao, orientador, orientando):
    # versão da orientanda (aparece em pareceres); marcar devolução a remove
    doc = _documento_com_v1(orientacao, _marco(orientacao), enviado_por=orientacao.orientando_id)
    versao = doc.versoes.first()
    login(client, "orientador@teste.br")
    assert versao.id in _versoes_sem_parecer_ids(orientador)
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{versao.id}/devolucao",
        follow_redirects=True,
    )
    db.session.expire(versao)
    assert versao.eh_devolucao is True
    assert versao.id not in _versoes_sem_parecer_ids(orientador)


def test_toggle_devolucao_negado_ao_orientando(client, orientacao, orientando):
    doc = _documento_com_v1(orientacao, _marco(orientacao), enviado_por=orientacao.orientador_id)
    versao = doc.versoes.first()
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{versao.id}/devolucao",
    )
    assert resp.status_code == 403


def test_devolver_marco_marca_versao_do_orientador(app, orientacao):
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientador_id)
    servico_cronograma.devolver_para_revisao(marco, "corrija")
    db.session.commit()
    assert doc.versoes.first().eh_devolucao is True
