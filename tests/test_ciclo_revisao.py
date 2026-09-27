"""Ciclo de revisão do marco: devolução para revisão, "de quem é a vez" e
atribuição de autoria das versões. Cobre o cenário que motivou a mudança — o
orientador devolve a v2 com anotações e a tarefa deve voltar ao orientando."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Documento, LogAuditoria, Marco, VersaoDocumento
from app.services import cronogramas as servico_cronograma
from app.services.uploads import UploadInvalido, salvar_versao
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


def _documento_com_v1(orientacao, marco, enviado_por, em_nome=False):
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
        em_nome_do_orientando=em_nome,
    )
    db.session.add(v)
    db.session.commit()
    return doc


# --- serviço: devolver_para_revisao ---


def test_devolver_reseta_sinal_e_marca_devolucao(app, orientacao):
    marco = _marco(orientacao, sinalizado=True)
    assert marco.aguardando == "orientador"

    assert servico_cronograma.devolver_entrega(marco, "Falta discutir o vício") is True
    db.session.commit()

    assert marco.conclusao_sinalizada is False
    assert marco.status == "em_andamento"
    assert marco.devolvido_em is not None
    assert marco.nota_devolucao == "Falta discutir o vício"
    assert marco.aguardando == "orientando_revisao"
    assert LogAuditoria.query.filter_by(acao="devolucao_revisao_marco").count() == 1


def test_devolver_recusa_marco_concluido(app, orientacao):
    """Sinalizado E concluído: sem isto o teste passava pela guarda de "não
    sinalizado" e nunca tocava a de "concluído"."""
    marco = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    servico_cronograma.confirmar_conclusao(marco)
    db.session.commit()
    assert marco.status == "concluido" and marco.conclusao_sinalizada is True
    assert servico_cronograma.devolver_entrega(marco, "x") is False
    assert marco.devolvido_em is None


def test_re_sinalizar_devolve_a_vez_ao_orientador(app, orientacao):
    marco = _marco(orientacao, sinalizado=True)
    servico_cronograma.devolver_entrega(marco, "corrija")
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
    servico_cronograma.devolver_entrega(marco, "ajuste")
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
    servico_cronograma.devolver_entrega(marco, "ajuste")
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


def test_painel_conferir_entrega_com_devolver(client, orientacao, orientador):
    """Sinalizada a entrega, a página oferece o painel "Conferir a entrega" com
    confirmar e devolver (a porta única de devolução)."""
    marco = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "Conferir a entrega" in corpo
    assert "Confirmar conclusão" in corpo
    assert "Devolver para revisão" in corpo
    assert "Arquivo corrigido" in corpo  # devolver aceita anexar num passo


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


def test_devolver_com_arquivo_pela_rota(client, orientacao, orientador):
    """A porta única: devolver anexa o arquivo corrigido ao documento-alvo,
    carimba-o como devolução e move o marco — tudo num passo."""
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "revise o cap. 2", "documento_id": str(doc.id),
              "arquivo": pdf_falso("anotado.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.expire(marco)
    assert marco.aguardando == "orientando_revisao"
    assert marco.nota_devolucao == "revise o cap. 2"
    nova = doc.versoes.first()  # a versão anexada, carimbada devolução
    assert nova.eh_devolucao is True
    assert nova.comentario is None  # a nota vive na tarefa, não se duplica aqui
    assert nova.id not in _versoes_sem_parecer_ids(orientador)


def test_devolver_com_arquivo_sem_documento_avisa(client, orientacao, orientador):
    """Marco sinalizado sem documento: um arquivo anexado não tem onde ir —
    avisa e devolve só com a nota, em vez de descartar o arquivo em silêncio."""
    marco = _marco(orientacao, sinalizado=True)  # sinalizado, SEM documentos
    login(client, "orientador@teste.br")
    antes = VersaoDocumento.query.count()
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "corrija", "arquivo": pdf_falso("x.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "não foi anexado" in resp.data.decode()
    assert VersaoDocumento.query.count() == antes  # nada gravado
    db.session.expire(marco)
    assert marco.aguardando == "orientando_revisao"  # devolveu só com a nota
    assert marco.nota_devolucao == "corrija"


def test_versao_devolucao_nao_tem_seletor_de_reclassificar(client, orientacao, orientador):
    """O seletor registro/entrega não aparece para uma versão-devolução: não pode
    representá-la como 'registro' e, num Aplicar, apagar a etiqueta."""
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    v1 = doc.versoes.first()
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "x", "documento_id": str(doc.id), "arquivo": pdf_falso("c.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    v2 = doc.versoes.first()  # a devolução carimbada
    assert v2.eh_devolucao is True
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}"
    ).data.decode()
    assert f"/versoes/{v2.id}/classificar" not in corpo  # devolução: sem seletor
    assert f"/versoes/{v1.id}/classificar" in corpo  # entrega da aluna: com seletor


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
        data={"arquivo": pdf_falso("v2.pdf"), "natureza": "devolucao"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert doc.versoes.first().eh_devolucao is False


def test_classificar_nao_aceita_devolucao(client, orientacao, orientador, orientando):
    """O seletor reclassifica só o eixo de parecer (registro/entrega); "devolução"
    não é opção dele — devolver é ação da tarefa."""
    doc = _documento_com_v1(orientacao, _marco(orientacao), enviado_por=orientacao.orientador_id)
    versao = doc.versoes.first()
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{versao.id}/classificar",
        data={"natureza": "devolucao"},  # valor forjado, fora das choices
        follow_redirects=True,
    )
    db.session.expire(versao)
    assert versao.eh_devolucao is False  # não aceitou a devolução pelo seletor


def test_classificar_negado_ao_orientando(client, orientacao, orientando):
    doc = _documento_com_v1(orientacao, _marco(orientacao), enviado_por=orientacao.orientador_id)
    versao = doc.versoes.first()
    login(client, "orientando@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{versao.id}/classificar",
        data={"natureza": "entrega"},
    )
    assert resp.status_code == 403


# --- registrar entrega em nome da orientanda ---


def test_upload_como_entrega_da_orientanda_pede_parecer(client, orientacao, orientador):
    """O orientador registra o arquivo que a aluna mandou por fora: conta como
    entrega dela e entra na lista de pareceres."""
    doc = _documento_com_v1(orientacao, _marco(orientacao), enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("dela.pdf"), "comentario": "recebido por e-mail",
              "natureza": "entrega"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    nova = doc.versoes.first()
    assert nova.em_nome_do_orientando is True
    assert nova.natureza == "entrega"
    assert nova.id in _versoes_sem_parecer_ids(orientador)


def test_classificar_versao_como_entrega_da_orientanda(client, orientacao, orientador):
    """Escotilha: um upload antigo do orientador pode ser reclassificado como
    entrega da orientanda e volta a pedir parecer."""
    doc = _documento_com_v1(orientacao, _marco(orientacao), enviado_por=orientacao.orientador_id)
    versao = doc.versoes.first()
    login(client, "orientador@teste.br")
    assert versao.id not in _versoes_sem_parecer_ids(orientador)
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{versao.id}/classificar",
        data={"natureza": "entrega"},
        follow_redirects=True,
    )
    db.session.expire(versao)
    assert versao.natureza == "entrega"
    assert versao.id in _versoes_sem_parecer_ids(orientador)


def test_natureza_padrao_do_upload_do_orientador_e_registro(client, orientacao, orientador):
    doc = _documento_com_v1(orientacao, _marco(orientacao), enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    client.post(  # sem informar natureza: vale o padrão "registro"
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"arquivo": pdf_falso("meu.pdf")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    nova = doc.versoes.first()
    assert nova.natureza == "registro"
    assert nova.id not in _versoes_sem_parecer_ids(orientador)


# (o antigo test_devolver_marco_marca_versao_do_orientador saiu na volta 2 da
#  corrida 2026-09-19: devolver deixou de carimbar versões — a classificação é
#  ato do documento, e a fila de pareceres já ignora o upload do orientador.
#  Ver test_devolver_nao_carimba_versao_alheia.)


# ======================= corrida 2026-09-19, volta 1 =======================


def test_devolver_preserva_entrega_registrada_em_nome_da_aluna(app, orientacao):
    """Devolver não pode marcar como devolução a entrega que o orientador
    registrou em nome da orientanda: ela some da fila de pareceres."""
    marco = _marco(orientacao, sinalizado=True)
    entrega = _documento_com_v1(
        orientacao, marco, enviado_por=orientacao.orientador_id, em_nome=True
    )

    servico_cronograma.devolver_entrega(marco, "corrija")
    db.session.commit()

    assert entrega.versoes.first().eh_devolucao is False  # entrega dela, intacta
    assert entrega.versoes.first().natureza == "entrega"


def test_devolver_no_mesmo_ciclo_nao_repete(app, orientacao):
    """Devolvida a entrega, o upload seguinte não devolve de novo (não há
    entrega sinalizada) — e por isso não mexe na nota já escrita."""
    marco = _marco(orientacao, sinalizado=True)
    servico_cronograma.devolver_entrega(marco, "Refazer a análise do cap. 3")
    db.session.commit()
    assert servico_cronograma.devolver_entrega(marco, "") is False
    assert marco.nota_devolucao == "Refazer a análise do cap. 3"


def test_reenvio_preserva_a_nota_para_o_orientador_decidir(client, orientacao, orientando):
    """A nota NÃO é apagada no reenvio: é o registro da última devolução, e o
    orientador precisa dela ao decidir confirmar ou devolver de novo."""
    marco = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    servico_cronograma.devolver_entrega(marco, "Refazer a análise do cap. 3")
    db.session.commit()

    login(client, "orientando@teste.br")  # ela corrige e sinaliza de novo
    client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/sinalizar",
        data={"nota": "corrigido"},
        follow_redirects=True,
    )
    db.session.expire(marco)
    assert marco.aguardando == "orientador"
    assert marco.nota_devolucao == "Refazer a análise do cap. 3"  # segue disponível


def test_nova_devolucao_sobrescreve_nota_e_data(app, orientacao):
    """Toda devolução grava a nota do ato (nota e data juntas): nunca se vê nota
    velha sob data nova. Devolver sem nota zera."""
    marco = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    servico_cronograma.devolver_entrega(marco, "Refazer a análise do cap. 3")
    db.session.commit()
    assert marco.nota_devolucao == "Refazer a análise do cap. 3"

    marco.conclusao_sinalizada = True  # aluna reenvia e sinaliza
    db.session.commit()
    servico_cronograma.devolver_entrega(marco, "")  # devolve de novo, sem nota
    db.session.commit()
    assert marco.nota_devolucao is None  # a nota do ciclo anterior não sobrevive


def test_devolver_nao_carimba_versao_alheia(app, orientacao):
    """Devolver move o estado do marco e nada mais: a ata da reunião anexada à
    tarefa não pode virar "devolução" e perder o link de parecer."""
    marco = _marco(orientacao, sinalizado=True)
    ata = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientador_id)
    servico_cronograma.devolver_entrega(marco, "corrija")
    db.session.commit()
    assert ata.versoes.first().eh_devolucao is False
    assert ata.versoes.first().natureza == "registro"


def test_devolver_recusa_marco_sem_entrega(app, orientacao):
    """Marco vazio: nada a devolver — evita anunciar à aluna a devolução de
    algo que ela não entregou."""
    marco = _marco(orientacao)  # sem sinal e sem arquivo
    assert servico_cronograma.devolver_entrega(marco, "x") is False
    assert marco.devolvido_em is None


def test_devolver_aceita_entrega_nao_sinalizada(app, orientacao):
    """Ela enviou o arquivo e esqueceu de sinalizar: há o que devolver, e a
    tela não oferece outro caminho para pedir correções."""
    marco = _marco(orientacao)  # não sinalizado, mas COM entrega
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    assert servico_cronograma.devolver_entrega(marco, "corrija") is True
    assert marco.aguardando == "orientando_revisao"


def _coorientador(orientacao):
    from app.models import OrientacaoOrientador
    from tests.conftest import _criar_usuario

    co = _criar_usuario("Coorientador", "co@teste.br", "orientador")
    db.session.add(OrientacaoOrientador(orientacao_id=orientacao.id, usuario_id=co.id))
    db.session.commit()
    return co


def test_coorientador_nao_ve_a_opcao_de_devolucao(client, app, orientacao, orientador):
    """A tela não pode oferecer ao coorientador uma opção que o POST recusa: o
    upload seria descartado sem explicação."""
    _coorientador(orientacao)
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "co@teste.br")

    for url in (
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}",
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
    ):
        corpo = client.get(url).data.decode()
        assert 'value="entrega"' in corpo  # registra entrega da aluna, pode
        assert 'value="devolucao"' not in corpo  # devolver, não


def test_coorientador_nao_devolve(client, app, orientacao, orientador):
    """Devolver é do orientador principal: a rota /devolver responde 403 ao
    coorientador, e a tarefa não se move."""
    _coorientador(orientacao)
    marco = _marco(orientacao, sinalizado=True)
    login(client, "co@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "x"},
    )
    assert resp.status_code == 403
    db.session.expire(marco)
    assert marco.conclusao_sinalizada is True  # nada mudou
    assert marco.devolvido_em is None


def test_devolver_marco_sem_entrega_da_aluna_avisa(client, orientacao, orientador):
    """Devolver um marco sem entrega da orientanda (só o orientador mexeu) não
    devolve nada — e a tela diz por quê, em vez de anunciar à aluna algo que ela
    não entregou."""
    marco = _marco(orientacao)  # não sinalizado
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientador_id)
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "corrija"},
        follow_redirects=True,
    )
    assert "ainda não tem entrega da orientanda" in resp.data.decode()
    db.session.expire(marco)
    assert marco.devolvido_em is None


def test_rotulo_de_entrega_registrada_na_tarefa(client, orientacao, orientador):
    """Na tabela da tarefa, a versão registrada em nome da aluna não pode ser
    rotulada "(orientando)" ao lado do nome do orientador."""
    marco = _marco(orientacao)
    _documento_com_v1(
        orientacao, marco, enviado_por=orientacao.orientador_id, em_nome=True
    )
    login(client, "orientador@teste.br")
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "Orientador A <small>(em nome da orientanda)</small>" in corpo


def test_card_de_devolucao_some_em_marco_concluido(client, orientacao, orientador):
    marco = _marco(orientacao, sinalizado=True)
    servico_cronograma.devolver_entrega(marco, "Refazer a seção 3.2")
    db.session.commit()
    login(client, "orientador@teste.br")
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "Refazer a seção 3.2" in corpo

    marco.conclusao_sinalizada = True
    db.session.commit()
    servico_cronograma.confirmar_conclusao(marco)
    db.session.commit()
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}"
    ).data.decode()
    assert "Devolvido para revisão" not in corpo  # não contradiz "Concluído"


# ============ versão só com comentário (arquivo opcional) ============


def test_salvar_versao_so_comentario(app, orientacao, orientador):
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    v = salvar_versao(doc, None, orientador, comentario="Todo o retorno está aqui.")
    db.session.commit()
    assert v.tem_arquivo is False
    assert v.nome_fisico is None and v.tamanho_bytes is None
    assert v.comentario == "Todo o retorno está aqui."
    assert v.numero_versao == 2  # segue a numeração


def test_salvar_versao_vazia_recusa(app, orientacao, orientador):
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    with pytest.raises(UploadInvalido):
        salvar_versao(doc, None, orientador, comentario="   ")


def test_nova_versao_so_comentario_pela_rota(client, orientacao, orientador):
    """Versão só com comentário (arquivo opcional): o upload grava a versão e não
    devolve nada (devolver é ação da tarefa)."""
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"comentario": "Retorno textual: revise os pontos 1 a 5.",
              "natureza": "registro"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    nova = doc.versoes.first()
    assert nova.tem_arquivo is False
    assert nova.comentario.startswith("Retorno textual")
    db.session.expire(marco)
    assert marco.conclusao_sinalizada is True  # o upload não devolveu a tarefa
    assert marco.devolvido_em is None


def test_devolver_so_com_nota_pela_rota(client, orientacao, orientador):
    """Devolver só com a nota (sem arquivo): a tarefa volta e a nota aparece."""
    marco = _marco(orientacao, sinalizado=True)
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    resp = client.post(
        f"/orientacoes/{orientacao.id}/cronograma/{marco.id}/devolver",
        data={"nota": "Revise os pontos 1 a 5."},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    db.session.expire(marco)
    assert marco.aguardando == "orientando_revisao"
    assert marco.nota_devolucao == "Revise os pontos 1 a 5."


def test_versao_vazia_recusada_pela_rota(client, orientacao, orientador):
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    antes = VersaoDocumento.query.count()
    resp = client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"comentario": "", "natureza": "registro"},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Envie um arquivo ou escreva um comentário" in resp.data.decode()
    assert VersaoDocumento.query.count() == antes  # nada gravado


def test_orientanda_versao_so_comentario_nao_pede_parecer(
    client, orientacao, orientando, orientador
):
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientando@teste.br")
    client.post(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}",
        data={"comentario": "Professor, uma dúvida antes de eu revisar."},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    nova = doc.versoes.first()
    assert nova.tem_arquivo is False
    assert nova.id not in _versoes_sem_parecer_ids(orientador)


def test_download_de_versao_so_comentario_404(client, orientacao, orientador):
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    v = salvar_versao(doc, None, orientador, comentario="texto")
    db.session.commit()
    login(client, "orientador@teste.br")
    resp = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}/versoes/{v.id}/download"
    )
    assert resp.status_code == 404


def test_emitir_parecer_nao_lista_versao_so_comentario(client, orientacao, orientador):
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    v1 = doc.versoes.first()
    so_comentario = salvar_versao(doc, None, orientador, comentario="texto")
    db.session.commit()
    login(client, "orientador@teste.br")
    corpo = client.get(f"/orientacoes/{orientacao.id}/pareceres/novo").data.decode()
    assert f'value="{v1.id}"' in corpo  # a versão com arquivo pode ser avaliada
    assert f'value="{so_comentario.id}"' not in corpo  # a só-comentário, não


def test_csrf_sem_limite_de_tempo(app):
    # token válido pela sessão inteira, não 1 h — evita "CSRF token expired"
    assert app.config.get("WTF_CSRF_TIME_LIMIT") is None


# ============ redesenho da devolução (porta única) ============


def test_pode_devolver_exige_entrega_da_orientanda(app, orientacao):
    """A precondição vazia corrigida: o upload do próprio orientador não conta —
    só entrega da orientanda (sinalizada ou não) habilita devolver."""
    marco = _marco(orientacao)  # nem sinalizado, nem entregue
    assert servico_cronograma.pode_devolver(marco) is False
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientador_id)
    db.session.expire(marco)
    assert servico_cronograma.pode_devolver(marco) is False  # só o orientador mexeu
    _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    db.session.expire(marco)
    assert servico_cronograma.pode_devolver(marco) is True  # agora há entrega dela


def test_devolver_entrega_carimba_a_versao_passada(app, orientacao):
    """`devolver_entrega(versao=v)` carimba v como devolução, num ato só."""
    marco = _marco(orientacao, sinalizado=True)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    v = doc.versoes.first()
    assert servico_cronograma.devolver_entrega(marco, "x", versao=v) is True
    db.session.commit()
    assert v.eh_devolucao is True
    assert marco.aguardando == "orientando_revisao"


def test_ultima_versao_desempata_por_id(app, orientacao):
    """Duas versões no mesmo instante: a 'última' é sempre a de maior id, nos dois
    lados (modelo e painel), para não divergirem."""
    from datetime import datetime

    from app.models.cronograma import ultima_versao

    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    v1 = doc.versoes.first()
    instante = datetime(2026, 9, 1, 12, 0, 0)
    v1.enviado_em = instante
    v2 = VersaoDocumento(
        documento_id=doc.id, numero_versao=2, nome_original="b.pdf",
        nome_fisico=f"{doc.id:032x}b.pdf", tamanho_bytes=10, mimetype="application/pdf",
        enviado_por=orientacao.orientador_id, enviado_em=instante,
    )
    db.session.add(v2)
    db.session.commit()
    escolhida = ultima_versao([(doc, v1), (doc, v2)])
    assert escolhida.id == max(v1.id, v2.id) == v2.id


def test_upload_nao_oferece_devolucao(client, orientacao, orientador):
    """O envio de versão não tem mais a opção 'devolução' — é eixo binário."""
    marco = _marco(orientacao)
    doc = _documento_com_v1(orientacao, marco, enviado_por=orientacao.orientando_id)
    login(client, "orientador@teste.br")
    corpo = client.get(
        f"/orientacoes/{orientacao.id}/documentos/{doc.id}"
    ).data.decode()
    assert 'value="registro"' in corpo and 'value="entrega"' in corpo
    assert 'value="devolucao"' not in corpo
