"""Ciclo da reunião: agendar, avisar, alterar, cancelar, excluir e derivar.

A reunião é a própria ata em rascunho. O que estes testes guardam é a divisão
entre o que existe antes do encontro (data, convidados, pauta) e o que só existe
depois (presenças, deliberações, tarefas), além do aviso que sai no ato.
"""
from datetime import date, timedelta

import pytest

from app.extensions import db
from app.models import Ata, AtaParticipacao, LogAuditoria, Marco, OrientacaoOrientador
from app.models.ata import STATUS_ATA
from app.services import convites
from app.services.atas import (
    AtaImutavel,
    OperacaoInvalida,
    alterar_convidados,
    cancelar_reuniao,
    excluir_reuniao,
    finalizar_ata,
)
from tests.conftest import _criar_usuario, login

FUTURO = (date.today() + timedelta(days=10)).isoformat()
PASSADO = date.today() - timedelta(days=3)


@pytest.fixture
def sem_smtp(monkeypatch):
    """Neutraliza a rede: a suíte não depende de servidor de e-mail. Devolve a
    lista de mensagens que teriam saído."""
    capturadas = []

    def _lote(mensagens):
        capturadas.extend(mensagens)
        return [m[0] for m in mensagens], []

    monkeypatch.setattr("app.services.email.enviar_lote", _lote)
    return capturadas


def _agendar(client, orientacoes, data=FUTURO, pauta="Alinhar o capítulo 2"):
    return client.post(
        "/reunioes/agendar",
        data={
            "data_reuniao": data,
            "hora_reuniao": "14:30",
            "pauta": pauta,
            "orientacoes": [str(o.id) for o in orientacoes],
        },
        follow_redirects=True,
    )


def _reuniao_realizada(orientacao, orientador, deliberacoes=""):
    """Reunião cuja data já passou, montada direto no banco."""
    ata = Ata(
        orientador_id=orientador.id,
        data_reuniao=PASSADO,
        pauta="Pauta",
        deliberacoes=deliberacoes,
        redigida_por=orientador.id,
        participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
    )
    db.session.add(ata)
    db.session.commit()
    return ata


# ---------------------------------------------------------------------------
# Agendar


def test_agenda_sem_deliberacoes(client, orientacao, orientador, sem_smtp):
    """O que se pede ao agendar é data, hora, pauta e convidados. Deliberação é
    o que se decidiu, e não existe antes do encontro."""
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao])

    ata = Ata.query.one()
    assert ata.status == "rascunho"
    assert ata.deliberacoes == ""
    assert ata.ata_redigida is False
    assert ata.agendada is True
    assert ata.realizada is False
    assert ata.tipo == "individual"
    assert [p.orientacao_id for p in ata.participacoes] == [orientacao.id]
    assert LogAuditoria.query.filter_by(acao="agendamento_reuniao").count() == 1


def test_agendar_para_dois_orientandos_e_reuniao_de_grupo(
    client, orientacao, orientacao2, orientador, sem_smtp
):
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao, orientacao2])
    assert Ata.query.one().tipo == "grupo"


def test_agendamento_avisa_os_convidados(
    client, orientacao, orientador, orientando, sem_smtp
):
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao])

    destinos = {m[0] for m in sem_smtp}
    assert destinos == {orientando.email, orientador.email}
    assunto = sem_smtp[0][1]
    assert assunto.startswith("ARIADNE: Reunião de orientação agendada")
    # texto simples primeiro, HTML como alternativa
    assert "Alinhar o capítulo 2" in sem_smtp[0][2]
    assert "Alinhar o capítulo 2" in sem_smtp[0][3]
    assert LogAuditoria.query.filter_by(acao="envio_convite").count() == 1


def test_convite_alcanca_coorientador_e_ignora_conta_desativada(
    app, orientacao, orientador, orientando
):
    """Convite não segue a convenção dos avisos de pendência: quem vai à
    reunião é avisado dela, coorientador incluído. Conta desativada fica de
    fora, como em `avisos.coletar`."""
    coorientador = _criar_usuario("Coorientador", "co@teste.br", "orientador")
    db.session.add(
        OrientacaoOrientador(
            orientacao_id=orientacao.id,
            usuario_id=coorientador.id,
            funcao="coorientador",
        )
    )
    ata = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() + timedelta(days=5),
        pauta="Pauta",
        deliberacoes="",
        redigida_por=orientador.id,
        participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
    )
    db.session.add(ata)
    db.session.commit()

    emails = {p.email for p in convites.destinatarios(ata)}
    assert emails == {orientando.email, orientador.email, coorientador.email}

    orientando.ativo = False
    db.session.commit()
    assert orientando.email not in {p.email for p in convites.destinatarios(ata)}


def test_falha_de_envio_nao_derruba_o_agendamento(
    client, orientacao, orientador, monkeypatch
):
    """A reunião fica agendada mesmo com o servidor de e-mail fora do ar, e a
    tela diz que o aviso não saiu."""
    monkeypatch.setattr(
        "app.services.email.enviar_lote",
        lambda mensagens: ([], [m[0] for m in mensagens]),
    )
    login(client, "orientador@teste.br")
    resposta = _agendar(client, [orientacao])

    assert Ata.query.count() == 1
    assert "não pôde ser enviado" in resposta.data.decode()


# ---------------------------------------------------------------------------
# Finalizar


def test_finalizar_sem_deliberacoes_e_recusado(app, orientacao, orientador):
    """Sem esta guarda, uma reunião agendada e nunca realizada seria congelada
    em PDF assinável com o campo em branco."""
    ata = _reuniao_realizada(orientacao, orientador)
    with pytest.raises(OperacaoInvalida):
        finalizar_ata(ata)
    assert ata.status == "rascunho"

    ata.deliberacoes = "Revisar a metodologia"
    finalizar_ata(ata)
    assert ata.status == "finalizada"


# ---------------------------------------------------------------------------
# Convidados


def test_alterar_convidados_inclui_e_exclui(app, orientacao, orientacao2, orientador):
    ata = _reuniao_realizada(orientacao, orientador)
    incluidos, excluidos = alterar_convidados(ata, [orientacao2])
    db.session.commit()

    assert incluidos == [orientacao2.id]
    assert excluidos == [orientacao.id]
    assert [p.orientacao_id for p in ata.participacoes] == [orientacao2.id]
    assert LogAuditoria.query.filter_by(acao="alteracao_convidados_reuniao").count() == 1


def test_nao_retira_convidado_com_presenca_assinalada(
    app, orientacao, orientacao2, orientador
):
    """A presença é fato registrado com autor e carimbo; retirar o convidado
    apagaria esse fato sem deixar rastro."""
    ata = _reuniao_realizada(orientacao, orientador)
    ata.participacoes[0].presenca = "presente"
    db.session.commit()

    with pytest.raises(OperacaoInvalida):
        alterar_convidados(ata, [orientacao2])
    assert [p.orientacao_id for p in ata.participacoes] == [orientacao.id]


def test_reuniao_sem_convidado_e_recusada(app, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador)
    with pytest.raises(OperacaoInvalida):
        alterar_convidados(ata, [])


# ---------------------------------------------------------------------------
# Cancelar e excluir


def test_cancelada_sai_da_agenda_do_lembrete_e_das_pendencias(
    app, orientacao, orientador, orientando
):
    from app.services import avisos, painel

    ata = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today() + timedelta(days=1),
        pauta="Pauta",
        deliberacoes="",
        redigida_por=orientador.id,
        participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
    )
    db.session.add(ata)
    db.session.commit()

    destino = {}
    avisos.reunioes_proximas(destino)
    assert orientando in destino  # antes de cancelar, o lembrete alcança

    cancelar_reuniao(ata, orientador, "Conflito de agenda da banca")
    db.session.commit()

    assert ata.status == "cancelada"
    assert ata.imutavel is True
    assert ata.motivo_cancelamento == "Conflito de agenda da banca"
    assert ata.cancelada_por == orientador.id

    destino = {}
    avisos.reunioes_proximas(destino)
    assert destino == {}

    with client_de(app, orientador):
        assert painel.pendencias()["proximas_reunioes"] == []


def client_de(app, usuario):
    """Contexto de requisição autenticado, para os serviços que leem
    `current_user`."""
    from flask_login import login_user

    ctx = app.test_request_context()
    ctx.push()
    login_user(usuario)

    class _Ctx:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            ctx.pop()
            return False

    return _Ctx()


def test_cancelada_nao_finaliza_nem_reagenda(app, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador, deliberacoes="Texto")
    cancelar_reuniao(ata, orientador, "Motivo")
    db.session.commit()

    with pytest.raises(AtaImutavel):
        finalizar_ata(ata)


def test_cancelamento_exige_motivo(app, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador)
    with pytest.raises(OperacaoInvalida):
        cancelar_reuniao(ata, orientador, "   ")


def test_ata_finalizada_nao_e_cancelada_nem_excluida(app, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador, deliberacoes="Texto")
    finalizar_ata(ata)
    db.session.commit()

    with pytest.raises(AtaImutavel):
        cancelar_reuniao(ata, orientador, "Motivo")
    with pytest.raises(AtaImutavel):
        excluir_reuniao(ata)


def test_exclui_reuniao_limpa(app, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador)
    assert ata.tem_historico is False
    excluir_reuniao(ata)
    db.session.commit()

    assert Ata.query.count() == 0
    assert LogAuditoria.query.filter_by(acao="exclusao_reuniao").count() == 1


def test_exclusao_recusada_quando_ha_presenca(app, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador)
    ata.participacoes[0].presenca = "ausente"
    db.session.commit()

    assert ata.tem_historico is True
    with pytest.raises(OperacaoInvalida):
        excluir_reuniao(ata)
    db.session.commit()

    assert Ata.query.count() == 1
    assert LogAuditoria.query.filter_by(acao="exclusao_reuniao_recusada").count() == 1


def test_exclusao_recusada_quando_ha_ata_redigida(app, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador, deliberacoes="Já escrito")
    assert ata.tem_historico is True
    with pytest.raises(OperacaoInvalida):
        excluir_reuniao(ata)


# ---------------------------------------------------------------------------
# Tarefa derivada


def test_tarefa_derivada_liga_o_marco_a_reuniao(
    client, orientacao, orientacao2, orientador, sem_smtp
):
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao, orientacao2])
    ata = Ata.query.one()

    client.post(
        f"/reunioes/{ata.id}/tarefas/nova",
        data={
            "titulo": "Revisar a metodologia",
            "tipo": "outro",
            "descricao": "",
            "data_prevista": FUTURO,
            "etapa": "0",
            "orientacoes": [str(orientacao.id), str(orientacao2.id)],
        },
        follow_redirects=True,
    )

    marcos = Marco.query.all()
    assert len(marcos) == 2
    assert {m.orientacao_id for m in marcos} == {orientacao.id, orientacao2.id}
    assert len({m.grupo_id for m in marcos}) == 1
    # a derivação fica registrada nos dois sentidos
    assert {m.id for m in ata.marcos} == {m.id for m in marcos}
    assert all(m.tem_historico for m in marcos)


def test_reuniao_cancelada_nao_deriva_tarefa(client, orientacao, orientador, sem_smtp):
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao])
    ata = Ata.query.one()
    cancelar_reuniao(ata, orientador, "Motivo")
    db.session.commit()

    client.post(
        f"/reunioes/{ata.id}/tarefas/nova",
        data={
            "titulo": "X",
            "tipo": "outro",
            "descricao": "",
            "data_prevista": FUTURO,
            "etapa": "0",
            "orientacoes": [str(orientacao.id)],
        },
        follow_redirects=True,
    )
    assert Marco.query.count() == 0


# ---------------------------------------------------------------------------
# Autorização e painel


def test_reuniao_de_outro_orientador_da_404(client, orientacao, orientador, app):
    outro = _criar_usuario("Outro", "outro@teste.br", "orientador")
    ata = _reuniao_realizada(orientacao, outro)

    login(client, "orientador@teste.br")
    assert client.get(f"/reunioes/{ata.id}/convidados").status_code == 404
    assert client.post(f"/reunioes/{ata.id}/excluir").status_code == 404


def test_orientando_nao_acessa_a_agenda(client, orientacao, orientando):
    login(client, "orientando@teste.br")
    assert client.get("/reunioes/").status_code == 403
    assert client.get("/reunioes/agendar").status_code == 403


def test_agenda_e_do_orientador_e_o_admin_usa_o_modulo_de_atas(
    client, orientacao, orientador, admin
):
    """A agenda é pessoal do convocante. O administrador não entra nela, e por
    isso a página da reunião não lhe oferece os atalhos que dariam 403; ele
    trata a mesma reunião pelo módulo de atas do vínculo, que já o autoriza."""
    ata = _reuniao_realizada(orientacao, orientador)
    login(client, "admin@teste.br")

    assert client.get("/reunioes/").status_code == 403
    assert client.get(f"/reunioes/{ata.id}/convidados").status_code == 403

    pagina = client.get(f"/orientacoes/{orientacao.id}/atas/{ata.id}")
    assert pagina.status_code == 200
    assert "Alterar convidados" not in pagina.data.decode()


def test_reuniao_futura_nao_e_pendencia_do_painel(
    client, orientacao, orientador, sem_smtp
):
    """Antes da divisão por estado, a reunião marcada para daqui a dez dias
    figurava no Painel como 'ata em rascunho a finalizar' desde o agendamento."""
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao])

    pagina = client.get("/dashboard").data.decode()
    assert "Próximas reuniões" in pagina
    assert "Nenhuma pendência em aberto" in pagina


def test_reuniao_realizada_sem_ata_e_pendencia(client, orientacao, orientador):
    _reuniao_realizada(orientacao, orientador)
    login(client, "orientador@teste.br")

    pagina = client.get("/dashboard").data.decode()
    assert "Reuniões realizadas sem ata" in pagina


def test_status_cancelada_declarado_no_modelo():
    assert "cancelada" in STATUS_ATA


# ---------------------------------------------------------------------------
# Renderização das telas em cada estado


def test_telas_do_ciclo_renderizam(
    client, orientacao, orientacao2, orientador, sem_smtp
):
    """Percorre a agenda com reuniões nos cinco estados ao mesmo tempo, e abre
    cada tela do ciclo. Guarda contra erro de template, que os testes de regra
    de negócio não alcançam."""
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao, orientacao2])
    agendada = Ata.query.one()

    aguardando = _reuniao_realizada(orientacao, orientador)
    em_redacao = _reuniao_realizada(orientacao, orientador, deliberacoes="Escrito")
    finalizada = _reuniao_realizada(orientacao, orientador, deliberacoes="Escrito")
    finalizar_ata(finalizada)
    cancelada = _reuniao_realizada(orientacao, orientador)
    cancelar_reuniao(cancelada, orientador, "Conflito de agenda")
    db.session.commit()

    agenda = client.get("/reunioes/")
    assert agenda.status_code == 200
    corpo = agenda.data.decode()
    for titulo in (
        "Próximas reuniões",
        "Aguardando ata",
        "Ata em redação",
        "Encerradas",
        "Canceladas",
    ):
        assert titulo in corpo
    assert "Conflito de agenda" in corpo

    assert client.get("/reunioes/agendar").status_code == 200
    assert client.get(f"/reunioes/{agendada.id}/convidados").status_code == 200
    assert client.get(f"/reunioes/{agendada.id}/tarefas/nova").status_code == 200

    # a página da reunião muda de aviso conforme o estado
    def pagina(ata):
        return client.get(
            f"/orientacoes/{orientacao.id}/atas/{ata.id}"
        ).data.decode()

    assert "Reunião ainda por acontecer" in pagina(agendada)
    assert "A data já passou" in pagina(aguardando)
    assert "Reunião cancelada" in pagina(cancelada)
    assert "Exportar PDF" in pagina(finalizada)
    assert "ata em redação" in pagina(em_redacao)

    # a listagem do vínculo distingue os estados
    listagem = client.get(f"/orientacoes/{orientacao.id}/atas").data.decode()
    for selo in ("agendada", "aguardando ata", "ata em redação", "ata finalizada",
                 "cancelada"):
        assert selo in listagem


# ---------------------------------------------------------------------------
# Fronteira entre "imutável" e "finalizada"
#
# `imutavel` passou a abranger a cancelada. Todo ponto que antes o usava como
# sinônimo de "finalizada" precisa distinguir os dois, sob pena de tratar como
# registro verificável uma reunião que nunca teve ata.


def test_cancelada_nao_gera_pdf(client, orientacao, orientador):
    ata = _reuniao_realizada(orientacao, orientador)
    cancelar_reuniao(ata, orientador, "Motivo")
    db.session.commit()

    login(client, "orientador@teste.br")
    resposta = client.get(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}/pdf", follow_redirects=True
    )
    assert "Apenas atas finalizadas" in resposta.data.decode()
    assert b"%PDF" not in resposta.data


def test_verificacao_publica_nao_quebra_com_cancelada(client, orientacao, orientador):
    """A verificação é pública e o identificador é sequencial. Antes, a ata
    cancelada entrava no ramo de finalizada e o `finalizada_em` nulo derrubava a
    página com erro 500."""
    ata = _reuniao_realizada(orientacao, orientador)
    cancelar_reuniao(ata, orientador, "Motivo")
    db.session.commit()

    resposta = client.get(f"/verificar/ata/{ata.id}/qualquerhash")
    assert resposta.status_code == 200
    assert "NÃO CONFERE" in resposta.data.decode()


def test_ata_finalizada_nao_recebe_tarefa_derivada(
    client, orientacao, orientador
):
    """Ligar um marco novo alteraria os marcos discutidos, que a finalização
    congela."""
    ata = _reuniao_realizada(orientacao, orientador, deliberacoes="Escrito")
    finalizar_ata(ata)
    db.session.commit()

    login(client, "orientador@teste.br")
    client.post(
        f"/reunioes/{ata.id}/tarefas/nova",
        data={
            "titulo": "X",
            "tipo": "outro",
            "descricao": "",
            "data_prevista": FUTURO,
            "etapa": "0",
            "orientacoes": [str(orientacao.id)],
        },
        follow_redirects=True,
    )
    assert Marco.query.count() == 0
    assert ata.marcos == []


def test_cancelada_nao_e_excluida(app, orientacao, orientador):
    """O cancelamento, com autor, carimbo e motivo, é o registro que se quis
    preservar ao cancelar; apagá-lo desfaria a escolha."""
    ata = _reuniao_realizada(orientacao, orientador)
    cancelar_reuniao(ata, orientador, "Motivo")
    db.session.commit()

    with pytest.raises(AtaImutavel):
        excluir_reuniao(ata)
    assert Ata.query.count() == 1


def test_deliberacoes_escritas_nao_somem_ao_salvar_em_branco(
    client, orientacao, orientador
):
    """O formulário aceita o campo vazio por causa da reunião agendada; uma vez
    escritas, esvaziá-las é perda de conteúdo, não edição."""
    ata = _reuniao_realizada(orientacao, orientador, deliberacoes="Texto valioso")
    login(client, "orientador@teste.br")

    resposta = client.post(
        f"/orientacoes/{orientacao.id}/atas/{ata.id}",
        data={"pauta": "Pauta", "deliberacoes": "   ", "submit": "Salvar alterações"},
        follow_redirects=True,
    )
    assert "não podem ser apagadas" in resposta.data.decode()
    assert ata.deliberacoes == "Texto valioso"


def test_reuniao_de_hoje_nao_e_dada_por_realizada(app, orientacao, orientador):
    """A hora é digitada no fuso do usuário e o servidor roda em UTC. Comparar
    as duas grandezas dava a reunião de hoje às 16:00 como realizada às 13:00 de
    Brasília. Só a virada do dia decide."""
    from datetime import time

    ata = Ata(
        orientador_id=orientador.id,
        data_reuniao=date.today(),
        hora_reuniao=time(0, 1),
        pauta="Pauta",
        deliberacoes="",
        redigida_por=orientador.id,
        participacoes=[AtaParticipacao(orientacao_id=orientacao.id)],
    )
    db.session.add(ata)
    db.session.commit()

    assert ata.realizada is False
    assert ata.agendada is True


def test_convidado_retirado_recebe_o_aviso(
    client, orientacao, orientacao2, orientador, orientando2, sem_smtp
):
    """Quem foi desconvidado é quem mais precisa saber, e no instante do envio
    ele já não consta de `ata.orientacoes`."""
    login(client, "orientador@teste.br")
    _agendar(client, [orientacao, orientacao2])
    ata = Ata.query.one()
    sem_smtp.clear()

    client.post(
        f"/reunioes/{ata.id}/convidados",
        data={"orientacoes": [str(orientacao.id)]},
        follow_redirects=True,
    )

    assert [p.orientacao_id for p in ata.participacoes] == [orientacao.id]
    assert orientando2.email in {m[0] for m in sem_smtp}


def test_ajuda_documenta_o_ciclo(client, orientando):
    login(client, "orientando@teste.br")
    ajuda = client.get("/ajuda").data.decode()
    assert "Agendar uma reunião" in ajuda
    assert "Tarefas derivadas" in ajuda
    # o manual não pode mandar clicar num botão que não existe mais
    assert "+ Nova ata de reunião" not in ajuda
