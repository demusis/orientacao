"""Avisos de pendência por e-mail, disparados uma vez por dia.

**Por que o gatilho é o próprio tráfego.** Tarefas agendadas são exclusivas de
conta paga no PythonAnywhere (verificado em 21/07/2026, aba Tasks). A
alternativa seria expor rota chamável de fora, protegida só por token — porta
nova que não se justifica nesta escala. Aqui, a cada requisição verifica-se se
os avisos do dia já saíram; em caso negativo, saem.

O que isso promete e o que não promete: **no máximo um envio por dia, havendo ao
menos uma visita**. Um dia sem nenhum acesso não gera envio, e a pendência é
comunicada no dia seguinte. Não é "todo dia às 8h".

A trava contra envio duplo é a atualização condicional em
`marcar_dia_como_enviado`: duas requisições simultâneas tentam gravar a data de
hoje, mas só uma altera linha, e apenas essa envia.

Cada pessoa recebe **uma** mensagem reunindo suas pendências, e não uma por
categoria — quatro e-mails no mesmo minuto seriam ignorados como ruído.
"""
from datetime import date, datetime, timedelta, timezone

from flask import current_app, has_request_context, render_template, request
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    Ata,
    AtaParticipacao,
    ConfiguracaoEmail,
    Documento,
    Marco,
    Orientacao,
    Parecer,
    VersaoDocumento,
)
from app.services import email as email_service
# uma reunião registrada e não formalizada por mais de duas semanas
DIAS_RASCUNHO_VELHO = 15
# Espera entre tentativas quando o envio falha. A saída de rede desta
# hospedagem é intermitente — em 21/07/2026 o mesmo destino conectou e, minutos
# depois, devolveu ENETUNREACH. Repetir de meia em meia hora dá dezenas de
# chances ao longo do dia; repetir a cada requisição castigaria os usuários.
INTERVALO_ENTRE_TENTATIVAS = timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Categorias. Cada uma devolve {Usuario destinatário: [linha, ...]}.
# Acrescentar categoria = escrever a função e incluí-la em CATEGORIAS.


# Cada seção declara o rótulo e a providência que cabe a quem a recebe. A
# providência é agregada no fim da mensagem: dizer o que fazer é o que separa um
# aviso útil de uma notificação que só informa.
SECOES = {
    "marcos_vencidos": (
        "Marcos com prazo vencido",
        "sinalizar a conclusão dos marcos já concluídos, no Cronograma do vínculo",
    ),
    "a_confirmar": (
        "Entregas aguardando sua confirmação",
        "confirmar as conclusões que seus orientandos sinalizaram",
    ),
    "sem_parecer": (
        "Entregas aguardando parecer",
        "emitir parecer sobre as versões entregues",
    ),
    "atas_rascunho": (
        "Atas em rascunho",
        "finalizar as atas pendentes, tornando-as registros imutáveis",
    ),
}


def _acumular(destino: dict, pessoa, secao: str, titulo: str, detalhe: str) -> None:
    """Item guardado em partes — título e detalhe — para que texto simples e
    HTML possam formatá-lo cada um a seu modo, sem duplicar a regra."""
    destino.setdefault(pessoa, {}).setdefault(secao, []).append(
        {"titulo": titulo, "detalhe": detalhe}
    )


def marcos_atrasados(destino: dict) -> None:
    """Ao orientando: prazo vencido sem conclusão."""
    hoje = date.today()
    itens = (
        Marco.query.join(Orientacao, Orientacao.id == Marco.orientacao_id)
        .options(joinedload(Marco.orientacao).joinedload(Orientacao.orientando))
        .filter(
            Orientacao.status == "ativa",
            Marco.status != "concluido",
            Marco.data_prevista < hoje,
        )
        .order_by(Marco.data_prevista)
        .all()
    )
    for m in itens:
        dias = (hoje - m.data_prevista).days
        _acumular(
            destino,
            m.orientacao.orientando,
            "marcos_vencidos",
            m.titulo,
            f"Previsto para {m.data_prevista.strftime('%d/%m/%Y')} — "
            f"{dias} {'dia' if dias == 1 else 'dias'} de atraso · "
            f"{m.orientacao.titulo_projeto}",
        )


def marcos_a_confirmar(destino: dict) -> None:
    """Ao orientador: o orientando sinalizou conclusão e ninguém confirmou."""
    itens = (
        Marco.query.join(Orientacao, Orientacao.id == Marco.orientacao_id)
        .options(
            joinedload(Marco.orientacao).joinedload(Orientacao.orientador),
            joinedload(Marco.orientacao).joinedload(Orientacao.orientando),
        )
        .filter(
            Orientacao.status == "ativa",
            Marco.conclusao_sinalizada.is_(True),
            Marco.status != "concluido",
        )
        .order_by(Marco.data_prevista)
        .all()
    )
    for m in itens:
        _acumular(
            destino,
            m.orientacao.orientador,
            "a_confirmar",
            m.titulo,
            f"Sinalizado por {m.orientacao.orientando.nome} · "
            f"{m.orientacao.titulo_projeto}",
        )


def versoes_sem_parecer(destino: dict) -> None:
    """Ao orientador: versão corrente entregue e ainda sem parecer.

    Só a versão corrente conta — versão superada por outra deixou de ser
    pendência, mesmo critério de `services/painel.py`."""
    com_parecer = select(Parecer.versao_documento_id).where(
        Parecer.versao_documento_id.isnot(None)
    )
    versao_corrente = (
        select(db.func.max(VersaoDocumento.numero_versao))
        .where(VersaoDocumento.documento_id == Documento.id)
        .correlate(Documento)
        .scalar_subquery()
    )
    itens = (
        VersaoDocumento.query.join(
            Documento, Documento.id == VersaoDocumento.documento_id
        )
        .join(Orientacao, Orientacao.id == Documento.orientacao_id)
        .options(
            joinedload(VersaoDocumento.documento)
            .joinedload(Documento.orientacao)
            .joinedload(Orientacao.orientador),
            joinedload(VersaoDocumento.documento)
            .joinedload(Documento.orientacao)
            .joinedload(Orientacao.orientando),
        )
        .filter(
            Orientacao.status == "ativa",
            VersaoDocumento.numero_versao == versao_corrente,
            VersaoDocumento.id.notin_(com_parecer),
        )
        .order_by(VersaoDocumento.enviado_em)
        .all()
    )
    for v in itens:
        orientacao = v.documento.orientacao
        _acumular(
            destino,
            orientacao.orientador,
            "sem_parecer",
            f"{v.documento.titulo} (versão {v.numero_versao})",
            f"Enviado por {orientacao.orientando.nome} em "
            f"{v.enviado_em.strftime('%d/%m/%Y')} · {orientacao.titulo_projeto}",
        )


def atas_em_rascunho(destino: dict) -> None:
    """Ao orientador: reunião registrada e nunca formalizada."""
    limite = date.today() - timedelta(days=DIAS_RASCUNHO_VELHO)
    itens = (
        Ata.query.options(
            joinedload(Ata.orientador),
            joinedload(Ata.participacoes)
            .joinedload(AtaParticipacao.orientacao)
            .joinedload(Orientacao.orientando),
        )
        .filter(Ata.status == "rascunho", Ata.data_reuniao < limite)
        .order_by(Ata.data_reuniao)
        .all()
    )
    for a in itens:
        dias = (date.today() - a.data_reuniao).days
        participantes = ", ".join(
            sorted(p.orientacao.orientando.nome for p in a.participacoes)
        )
        _acumular(
            destino,
            a.orientador,
            "atas_rascunho",
            f"Reunião de {a.data_reuniao.strftime('%d/%m/%Y')}",
            f"{dias} dias sem finalização"
            + (f" · com {participantes}" if participantes else ""),
        )


CATEGORIAS = (
    marcos_atrasados,
    marcos_a_confirmar,
    versoes_sem_parecer,
    atas_em_rascunho,
)


# ---------------------------------------------------------------------------


def coletar() -> dict:
    """{Usuario: {"Título da seção": [linha, ...]}} para todos os pendentes."""
    destino: dict = {}
    for categoria in CATEGORIAS:
        categoria(destino)
    return destino


ACRONIMO = (
    "Ambiente de Revisão, Integração, Acompanhamento Discente e "
    "Normatização de Estudos"
)
RODAPE = (
    "Mensagem automática do ARIADNE, enviada no máximo uma vez por dia e "
    "somente quando há pendências. Não é necessário respondê-la."
)


def endereco_do_sistema() -> str:
    """Endereço para o destinatário chegar ao sistema.

    Sem isto o aviso é inútil: informa a pendência e não dá como tratá-la — foi
    o defeito da primeira versão. Preferência ao valor configurado; na falta
    dele, o host da requisição que disparou o envio, que é o correto por
    construção."""
    configurado = current_app.config.get("URL_BASE")
    if configurado:
        return configurado.rstrip("/")
    if has_request_context():
        return request.url_root.rstrip("/")
    return ""


def _contar(secoes: dict) -> int:
    return sum(len(itens) for itens in secoes.values())


def assunto(secoes: dict) -> str:
    """Assunto com a quantidade: quem recebe decide abrir agora ou depois sem
    precisar abrir para saber o tamanho."""
    total = _contar(secoes)
    return (
        f"ARIADNE — {total} pendência{'s' if total != 1 else ''} "
        "no seu acompanhamento"
    )


def _providencias(secoes: dict) -> list:
    """Providências das seções presentes, sem repetição e em ordem estável."""
    vistas, saida = set(), []
    for chave in secoes:
        acao = SECOES[chave][1]
        if acao not in vistas:
            vistas.add(acao)
            saida.append(acao)
    return saida


def _contexto(pessoa, secoes: dict, url: str) -> dict:
    """Tudo o que os templates precisam. Reunido num ponto para que as duas
    versões da mensagem não possam divergir no que dizem — só no como."""
    return {
        "pessoa": pessoa,
        "secoes": secoes,
        "SECOES": SECOES,
        "total": _contar(secoes),
        "providencias": _providencias(secoes),
        "url": url,
        "acronimo": ACRONIMO,
        "rodape": RODAPE,
    }


def corpo_texto(pessoa, secoes: dict, url: str) -> str:
    """Renderiza `emails/pendencias.txt`. A redação está lá, não aqui."""
    return render_template("emails/pendencias.txt", **_contexto(pessoa, secoes, url))


def corpo_html(pessoa, secoes: dict, url: str) -> str:
    """Renderiza `emails/pendencias.html`. O Jinja escapa os dados do usuário."""
    return render_template("emails/pendencias.html", **_contexto(pessoa, secoes, url))


def _agora() -> datetime:
    """UTC ingênuo, como o restante das colunas de data e hora do banco."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reservar_tentativa() -> bool:
    """Trava atômica: devolve True apenas a quem obteve o direito de tentar.

    Um único UPDATE condicional grava o instante da tentativa. Duas requisições
    simultâneas executam a mesma instrução, mas só uma encontra a linha
    elegível e altera algo — a outra recebe rowcount 0 e não envia.

    O que se reserva é a **tentativa**, não o dia: a marca de sucesso é gravada
    depois, e só havendo entrega. Assim um lote perdido por rede indisponível não
    consome o aviso do dia, e a requisição seguinte, passado o intervalo, tenta
    de novo. É o que torna o mecanismo tolerável numa rede intermitente — e a
    desta hospedagem é."""
    agora = _agora()
    resultado = db.session.execute(
        db.text(
            "UPDATE configuracao_email SET avisos_tentados_em = :agora "
            "WHERE id = 1 "
            "  AND (avisos_enviados_em IS NULL OR avisos_enviados_em < :hoje) "
            "  AND (avisos_tentados_em IS NULL OR avisos_tentados_em < :limite)"
        ),
        {
            "agora": agora,
            "hoje": date.today(),
            "limite": agora - INTERVALO_ENTRE_TENTATIVAS,
        },
    )
    return resultado.rowcount == 1


def marcar_dia_como_enviado() -> None:
    """Encerra os disparos do dia. Chamado só após entrega efetiva."""
    db.session.execute(
        db.text(
            "UPDATE configuracao_email SET avisos_enviados_em = :hoje WHERE id = 1"
        ),
        {"hoje": date.today()},
    )


def disparar_se_devido() -> dict | None:
    """Tenta o envio do dia, respeitando trava e intervalo.

    Devolve o resumo quando houve tentativa, ou None quando não era hora. O
    chamador não precisa conhecer as regras — só repassar o resumo à auditoria."""
    if not reservar_tentativa():
        return None
    resumo = enviar_pendentes()
    # sem destinatário algum, o dia está resolvido: não há o que reenviar
    if resumo["enviados"] or resumo["destinatarios"] == 0:
        marcar_dia_como_enviado()
    return resumo


def enviar_pendentes() -> dict:
    """Monta e envia as mensagens do dia. Uma conexão SMTP para todas — abrir uma
    por destinatário multiplicaria a espera da requisição que disparou."""
    destinatarios = coletar()
    if not destinatarios:
        return {"destinatarios": 0, "itens": 0, "enviados": [], "falhas": []}

    url = endereco_do_sistema()
    mensagens = [
        (
            pessoa.email,
            assunto(secoes),
            corpo_texto(pessoa, secoes, url),
            corpo_html(pessoa, secoes, url),
        )
        for pessoa, secoes in destinatarios.items()
    ]
    enviados, falhas = email_service.enviar_lote(mensagens)
    return {
        "destinatarios": len(destinatarios),
        "itens": sum(len(i) for s in destinatarios.values() for i in s.values()),
        "enviados": enviados,
        "falhas": falhas,
    }
