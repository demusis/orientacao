"""Regras de negócio da reunião e da sua ata: agendamento, convidados,
imutabilidade, reagendamento, presenças e cancelamento. Todos os eventos recebem
carimbo de data/hora (UTC) e registro em auditoria.

A reunião **é** a ata em rascunho: o mesmo registro atravessa o ciclo inteiro,
de marcada a finalizada. Agendar cria a linha com as deliberações em branco;
realizada a reunião, é a mesma linha que recebe presenças, texto e tarefas
derivadas. Uma entidade separada duplicaria data, hora e participantes, e
deixaria o lembrete de 48 h, o painel e o PDF olhando para o lugar errado.

Nenhuma função aqui dá commit: a rota decide o momento, e o envio de e-mail que
porventura se siga precisa acontecer **depois** dele, para não segurar a trava de
escrita do SQLite durante a sessão SMTP."""
from datetime import UTC, datetime

from app.extensions import db
from app.models import Ata, AtaParticipacao, Reagendamento
from app.services import auditoria


class AtaImutavel(Exception):
    pass


class OperacaoInvalida(Exception):
    pass


# Sentinela de "argumento não informado", distinta de None, que aqui significa
# "apague o valor".
_MANTER = object()


def limpar_link(link) -> str | None:
    """Espaço em volta some, e o campo vazio vira NULL em vez de string vazia:
    o template decide se mostra o link por `if ata.link_reuniao`, e `""` é falso
    em Jinja mas ocuparia a coluna sem significar nada."""
    return (link or "").strip() or None


def agendar_reuniao(orientador, *, vinculos, data, hora, pauta, link=None) -> Ata:
    """Marca uma reunião futura. As deliberações nascem vazias e só são
    exigidas na finalização: não há o que deliberar antes do encontro.

    Com um único convidado a reunião é individual, e o registro fica idêntico ao
    criado pelo módulo de atas do próprio vínculo."""
    if not vinculos:
        raise OperacaoInvalida("Selecione ao menos um orientando.")
    ata = Ata(
        tipo="grupo" if len(vinculos) > 1 else "individual",
        orientador_id=orientador.id,
        data_reuniao=data,
        hora_reuniao=hora,
        link_reuniao=limpar_link(link),
        pauta=pauta,
        deliberacoes="",
        redigida_por=orientador.id,
        participacoes=[AtaParticipacao(orientacao_id=o.id) for o in vinculos],
    )
    db.session.add(ata)
    db.session.flush()
    auditoria.registrar(
        "agendamento_reuniao",
        "ata",
        ata.id,
        {
            "data": f"{data} {hora or ''}".strip(),
            "online": bool(limpar_link(link)),
            "orientacoes": [o.id for o in vinculos],
        },
    )
    return ata


def alterar_convidados(ata: Ata, vinculos) -> tuple[list, list]:
    """Redefine os participantes, devolvendo (incluídos, excluídos) por id.

    Recusa retirar quem já teve presença assinalada: a presença é um fato
    registrado com autor e carimbo, e removê-la pela porta dos fundos apagaria
    esse fato sem deixar rastro. Nesse caso, o caminho é reverter a presença a
    pendente antes, ou manter o convidado."""
    if ata.imutavel:
        auditoria.registrar("tentativa_edicao_ata_finalizada", "ata", ata.id)
        raise AtaImutavel("Reunião encerrada ou cancelada não muda de convidados.")
    if not vinculos:
        raise OperacaoInvalida("A reunião precisa de ao menos um convidado.")

    desejados = {o.id for o in vinculos}
    atuais = {p.orientacao_id: p for p in ata.participacoes}

    with_presenca = [
        oid
        for oid, p in atuais.items()
        if oid not in desejados and p.presenca != "pendente"
    ]
    if with_presenca:
        raise OperacaoInvalida(
            "Não é possível retirar quem já teve presença assinalada. "
            "Reverta a presença a pendente antes, ou mantenha o convidado."
        )

    excluidos = sorted(set(atuais) - desejados)
    incluidos = sorted(desejados - set(atuais))
    for oid in excluidos:
        ata.participacoes.remove(atuais[oid])
    for oid in incluidos:
        ata.participacoes.append(AtaParticipacao(orientacao_id=oid))
    # o tipo acompanha o tamanho: retirar convidados de uma reunião de grupo até
    # sobrar um a torna individual, e o PDF deve dizer o que ela de fato foi
    ata.tipo = "grupo" if len(desejados) > 1 else "individual"

    auditoria.registrar(
        "alteracao_convidados_reuniao",
        "ata",
        ata.id,
        {"incluidos": incluidos, "excluidos": excluidos},
    )
    return incluidos, excluidos


def cancelar_reuniao(ata: Ata, usuario, motivo: str) -> None:
    """A reunião marcada que não vai ocorrer. O registro permanece, com autor,
    carimbo e motivo; o que cessa é a agenda, o lembrete e a cobrança da ata."""
    if ata.status == "finalizada":
        auditoria.registrar("tentativa_cancelamento_ata_finalizada", "ata", ata.id)
        raise AtaImutavel("Ata finalizada não pode ser cancelada.")
    if ata.status == "cancelada":
        raise OperacaoInvalida("Esta reunião já está cancelada.")
    if not (motivo or "").strip():
        raise OperacaoInvalida("Informe o motivo do cancelamento.")
    ata.status = "cancelada"
    ata.cancelada_em = datetime.now(UTC)
    ata.cancelada_por = usuario.id
    ata.motivo_cancelamento = motivo
    auditoria.registrar("cancelamento_reuniao", "ata", ata.id, {"motivo": motivo})


def excluir_reuniao(ata: Ata) -> None:
    """Apaga a reunião, e só a que nada produziu: agendamento equivocado.

    Havendo qualquer registro (presença assinalada, reagendamento, ata redigida
    ou marco ligado), a exclusão é recusada e o caminho passa a ser o
    cancelamento. Mesmo critério de `excluir_tarefa_grupo` e da exclusão de
    contas: preserva-se o que já produziu história."""
    if ata.imutavel:
        # a cancelada também não se apaga: o cancelamento, com autor, carimbo e
        # motivo, é justamente o registro que se quis preservar ao cancelar
        auditoria.registrar("tentativa_exclusao_ata_finalizada", "ata", ata.id)
        raise AtaImutavel(
            "Reunião encerrada ou cancelada não pode ser excluída; o registro "
            "é preservado."
        )
    if ata.tem_historico:
        auditoria.registrar("exclusao_reuniao_recusada", "ata", ata.id)
        raise OperacaoInvalida(
            "Exclusão recusada: a reunião já tem histórico (presença "
            "assinalada, reagendamento, ata redigida ou tarefa ligada). "
            "Cancele-a, e o registro é preservado."
        )
    auditoria.registrar(
        "exclusao_reuniao",
        "ata",
        ata.id,
        {"orientacoes": sorted(p.orientacao_id for p in ata.participacoes)},
    )
    db.session.delete(ata)


def atualizar_ata(ata: Ata, *, pauta, deliberacoes, marcos=None, link=_MANTER):
    """Edição de conteúdo do rascunho. Data/hora da reunião mudam apenas via
    reagendar_ata, para que toda alteração de agenda deixe registro próprio.

    `marcos` (lista de Marco), quando fornecida, substitui os marcos discutidos;
    a imutabilidade da ata finalizada já os congela, pois a edição é barrada
    aqui antes de qualquer atribuição.

    `link` é o endereço da sala virtual, frequentemente criado depois do
    agendamento. O padrão é a sentinela `_MANTER`, e não None, para distinguir
    "não mexa" de "apague": quem não passa o argumento preserva o que havia."""
    if ata.imutavel:
        auditoria.registrar("tentativa_edicao_ata_finalizada", "ata", ata.id)
        raise AtaImutavel("Ata finalizada ou cancelada é imutável.")
    # O formulário aceita deliberações vazias, porque a reunião agendada ainda
    # não as tem. Uma vez escritas, porém, esvaziá-las é perda de conteúdo, e
    # não edição: o texto sumiria sem confirmação nem cópia, e a ata regrediria
    # em silêncio de "em redação" para "aguardando ata".
    if ata.ata_redigida and not (deliberacoes or "").strip():
        raise OperacaoInvalida(
            "As deliberações já escritas não podem ser apagadas. Corrija o "
            "texto, ou cancele a reunião se ela não ocorreu."
        )
    ata.pauta = pauta
    ata.deliberacoes = deliberacoes
    if marcos is not None:
        ata.marcos = marcos
    if link is not _MANTER:
        ata.link_reuniao = limpar_link(link)
    auditoria.registrar("edicao_ata", "ata", ata.id)


def finalizar_ata(ata: Ata):
    if ata.status == "cancelada":
        raise AtaImutavel("Reunião cancelada não tem ata a finalizar.")
    if ata.imutavel:
        raise AtaImutavel("Ata já finalizada.")
    # a reunião agendada nasce sem deliberações; congelar assim produziria um
    # PDF assinável com o campo em branco, que é o oposto de um registro
    if not (ata.pauta or "").strip() or not ata.ata_redigida:
        raise OperacaoInvalida(
            "Preencha a pauta e as deliberações antes de finalizar a ata."
        )
    ata.status = "finalizada"
    ata.finalizada_em = datetime.now(UTC)
    # congela o conteúdo impresso: PDF e hash passam a derivar do snapshot
    from app.services.exportacao import congelar_ata

    congelar_ata(ata)
    auditoria.registrar("finalizacao_ata", "ata", ata.id)


def reagendar_ata(ata: Ata, usuario, *, data_nova, hora_nova, motivo=None):
    if ata.imutavel:
        auditoria.registrar("tentativa_reagendamento_ata_finalizada", "ata", ata.id)
        raise AtaImutavel(
            "Reunião encerrada ou cancelada não pode ser reagendada."
        )
    registro = Reagendamento(
        ata_id=ata.id,
        data_anterior=ata.data_reuniao,
        hora_anterior=ata.hora_reuniao,
        data_nova=data_nova,
        hora_nova=hora_nova,
        motivo=motivo,
        registrado_por=usuario.id,
    )
    db.session.add(registro)
    ata.data_reuniao = data_nova
    ata.hora_reuniao = hora_nova
    auditoria.registrar(
        "reagendamento_reuniao",
        "ata",
        ata.id,
        {
            "de": f"{registro.data_anterior} {registro.hora_anterior or ''}".strip(),
            "para": f"{data_nova} {hora_nova or ''}".strip(),
            "motivo": motivo,
        },
    )
    return registro


def registrar_presenca(participacao: AtaParticipacao, presenca: str, usuario):
    if presenca not in ("presente", "ausente"):
        raise OperacaoInvalida("Valor de presença inválido.")
    if participacao.ata.imutavel:
        auditoria.registrar(
            "tentativa_presenca_ata_finalizada", "ata", participacao.ata_id
        )
        raise AtaImutavel("Presenças não podem ser alteradas após a finalização da ata.")
    participacao.presenca = presenca
    participacao.presenca_registrada_em = datetime.now(UTC)
    participacao.presenca_registrada_por = usuario.id
    auditoria.registrar(
        "registro_presenca",
        "ata",
        participacao.ata_id,
        {"orientacao_id": participacao.orientacao_id, "presenca": presenca},
    )


# Nota LGPD: o registro de justificativa de ausência foi retirado por decisão de
# 19/07/2026 (potencial dado sensível). As colunas e os dados eventualmente
# gravados foram expurgados do esquema pela migração f2b6d81c4a55.
