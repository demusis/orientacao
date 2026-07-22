"""Avisos de pendência por e-mail, disparados uma vez por dia.

**Por que o gatilho é o próprio tráfego.** Tarefas agendadas são exclusivas de
conta paga no PythonAnywhere (verificado em 21/07/2026, aba Tasks). A
alternativa seria expor rota chamável de fora, protegida só por token — porta
nova que não se justifica nesta escala. Aqui, a cada requisição verifica-se se
os avisos do dia já saíram; em caso negativo, saem.

O que isso promete e o que não promete: **no máximo um envio por dia, havendo ao
menos uma visita**. Um dia sem nenhum acesso não gera envio, e a pendência é
comunicada no dia seguinte. Não é "todo dia às 8h".

Três marcas coordenam o disparo, e a distinção entre elas é o que evita tanto o
aviso perdido quanto o aviso repetido:

- `avisos_tentados_em` reserva a tentativa e impõe o intervalo entre repetições.
  É confirmada **antes** de falar com a rede, para não segurar a trava de escrita
  do SQLite durante a sessão SMTP — do contrário, qualquer outra requisição que
  gravasse esperaria pela rede e poderia receber `database is locked`.
- `avisos_entregues` guarda quem já recebeu no dia, de modo que repetir uma
  tentativa parcialmente falha atinja apenas quem faltou.
- `avisos_enviados_em` encerra o dia, e só avança quando nada ficou pendente.

Cada pessoa recebe **uma** mensagem reunindo suas pendências, e não uma por
categoria — quatro e-mails no mesmo minuto seriam ignorados como ruído.
"""
import json
from datetime import date, datetime, timedelta

from flask import current_app, render_template
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
from app.services.tempo import agora as tempo_agora

# uma reunião registrada e não formalizada por mais de duas semanas
DIAS_RASCUNHO_VELHO = 15
# antecedência dos avisos preventivos
DIAS_ANTECEDENCIA = 7
HORAS_ANTECEDENCIA_REUNIAO = 48
# Espera entre tentativas quando o envio falha. A saída de rede desta
# hospedagem é intermitente — em 21/07/2026 o mesmo destino conectou e, minutos
# depois, devolveu ENETUNREACH. Repetir de meia em meia hora dá dezenas de
# chances ao longo do dia; repetir a cada requisição castigaria os usuários.
INTERVALO_ENTRE_TENTATIVAS = timedelta(minutes=30)


# ---------------------------------------------------------------------------
# Categorias. Cada uma devolve {Usuario destinatário: [linha, ...]}.
# Acrescentar categoria = escrever a função e incluí-la em CATEGORIAS.


# Cada seção declara rótulo, uma frase que explica o que aquilo significa e o
# passo a passo de como resolver. As instruções ficam **junto dos itens a que se
# referem**, e não reunidas no fim: quem lê já está olhando a pendência, e é ali
# que a dúvida "e agora, o que faço?" aparece.
#
# O passo a passo cita os nomes exatos dos menus e botões da interface. Ao mudar
# um rótulo na tela, mude aqui também — instrução que manda clicar num botão
# inexistente é pior que instrução nenhuma.
SECOES = {
    "marcos_vencidos": {
        "titulo": "Marcos com prazo vencido",
        "explicacao": (
            "São tarefas do seu cronograma cuja data prevista já passou e que "
            "ainda não constam como concluídas."
        ),
        "passos": [
            "Abra o sistema e clique em Painel; a orientação aparece na lista.",
            "Dentro dela, vá em Cronograma.",
            "No marco já concluído, clique em Sinalizar conclusão. Seu "
            "orientador recebe o aviso e faz a confirmação — só então o marco "
            "passa a concluído.",
            "Se o prazo não for mais viável, converse com seu orientador: ele "
            "pode alterar a data prevista.",
        ],
    },
    "a_confirmar": {
        "titulo": "Entregas aguardando sua confirmação",
        "explicacao": (
            "Seus orientandos sinalizaram que concluíram estes marcos. A "
            "conclusão só se efetiva depois que você confirma."
        ),
        "passos": [
            "Abra a orientação pelo Painel e vá em Cronograma.",
            "Examine a entrega e clique em Confirmar conclusão.",
            "A data de conclusão fica registrada no histórico do vínculo.",
        ],
    },
    "sem_parecer": {
        "titulo": "Entregas aguardando parecer",
        "explicacao": (
            "São as versões mais recentes de documentos enviados pelos "
            "orientandos que ainda não receberam apreciação sua. Versões "
            "substituídas por outras mais novas não entram nesta lista."
        ),
        "passos": [
            "Abra a orientação pelo Painel e vá em Documentos.",
            "Baixe a versão enviada e faça a leitura.",
            "Em Pareceres, clique em Emitir parecer, escolha o resultado "
            "(aprovado, aprovado com ressalvas ou reprovado) e escreva sua "
            "apreciação.",
            "O parecer emitido é imutável e pode ser exportado em PDF para "
            "assinatura eletrônica.",
        ],
    },
    "atas_rascunho": {
        "titulo": "Atas em rascunho",
        "explicacao": (
            "São reuniões registradas cuja ata nunca foi formalizada. "
            "Enquanto está em rascunho, a ata pode ser editada livremente e "
            "não vale como registro."
        ),
        "passos": [
            "Abra a orientação pelo Painel e vá em Atas.",
            "Revise a pauta e as deliberações.",
            "Clique em Finalizar ata. A partir daí ela se torna imutável e "
            "pode ser exportada em PDF para assinatura.",
        ],
    },
    "marcos_a_vencer": {
        "titulo": "Marcos com prazo próximo",
        "explicacao": (
            "São tarefas do seu cronograma cujo prazo vence nos próximos dias e "
            "ainda não constam como concluídas. Aviso preventivo — nada está "
            "atrasado ainda."
        ),
        "passos": [
            "Abra o sistema, vá em Painel e depois em Cronograma da orientação.",
            "Ao concluir a tarefa, clique em Sinalizar conclusão.",
            "Prevendo que o prazo não será cumprido, avise seu orientador com "
            "antecedência — ele pode ajustar a data prevista.",
        ],
    },
    "reunioes_proximas": {
        "titulo": "Reuniões nas próximas 48 horas",
        "explicacao": (
            "São reuniões de orientação já agendadas cuja data se aproxima."
        ),
        "passos": [
            "Confirme a data e a hora na página da orientação, em Atas.",
            "Precisando remarcar, use Reagendar enquanto a ata está em rascunho — "
            "a nova data fica registrada no histórico.",
        ],
    },
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


def marcos_a_vencer(destino: dict) -> None:
    """Ao orientando: prazo nos próximos DIAS_ANTECEDENCIA dias, sem conclusão.

    Janela `[hoje, hoje + antecedência]`, aberta no passado: o `>= hoje` não se
    sobrepõe a `marcos_atrasados`, que cobre `< hoje`. Um marco de hoje entra
    aqui, não lá."""
    hoje = date.today()
    limite = hoje + timedelta(days=DIAS_ANTECEDENCIA)
    itens = (
        Marco.query.join(Orientacao, Orientacao.id == Marco.orientacao_id)
        .options(joinedload(Marco.orientacao).joinedload(Orientacao.orientando))
        .filter(
            Orientacao.status == "ativa",
            Marco.status != "concluido",
            Marco.data_prevista >= hoje,
            Marco.data_prevista <= limite,
        )
        .order_by(Marco.data_prevista)
        .all()
    )
    for m in itens:
        dias = (m.data_prevista - hoje).days
        quando = "hoje" if dias == 0 else (
            "amanhã" if dias == 1 else f"em {dias} dias"
        )
        _acumular(
            destino,
            m.orientacao.orientando,
            "marcos_a_vencer",
            m.titulo,
            f"Vence {quando} ({m.data_prevista.strftime('%d/%m/%Y')}) · "
            f"{m.orientacao.titulo_projeto}",
        )


def reunioes_proximas(destino: dict) -> None:
    """Ao orientador e a cada orientando participante: reunião nas próximas 48 h.

    A ata em rascunho é o registro da reunião agendada; finalizada, a reunião já
    ocorreu e não é lembrete.

    Reunião **com hora** é comparada por data e hora, para não lembrar de uma
    cuja hora já passou hoje. **Sem hora**, vale pela data: tratá-la como 00:00
    faria toda reunião de hoje (e, na virada da meia-noite UTC, a de amanhã)
    cair no passado e desaparecer — a hora é desconhecida, não zero."""
    agora = tempo_agora()
    limite = agora + timedelta(hours=HORAS_ANTECEDENCIA_REUNIAO)
    atas = (
        Ata.query.options(
            joinedload(Ata.orientador),
            joinedload(Ata.participacoes)
            .joinedload(AtaParticipacao.orientacao)
            .joinedload(Orientacao.orientando),
            joinedload(Ata.participacoes)
            .joinedload(AtaParticipacao.orientacao),
        )
        .filter(
            Ata.status == "rascunho",
            Ata.data_reuniao >= agora.date(),
            Ata.data_reuniao <= limite.date(),
        )
        .order_by(Ata.data_reuniao)
        .all()
    )
    for a in atas:
        if a.hora_reuniao is not None:
            # com hora: exclui a que já passou hoje
            quando = datetime.combine(a.data_reuniao, a.hora_reuniao)
            if not (agora <= quando <= limite):
                continue
        elif a.data_reuniao < agora.date():
            # sem hora: vale pela data. O filtro SQL já a manteve na janela;
            # só descarta a de data estritamente passada (defesa redundante).
            continue
        # só participantes de vínculo ativo
        participantes = [
            p.orientacao.orientando
            for p in a.participacoes
            if p.orientacao.status == "ativa"
        ]
        if not participantes:
            continue
        rotulo_hora = (
            f" às {a.hora_reuniao.strftime('%H:%M')}" if a.hora_reuniao else ""
        )
        detalhe = f"{a.data_reuniao.strftime('%d/%m/%Y')}{rotulo_hora}"
        for pessoa in [a.orientador, *participantes]:
            _acumular(destino, pessoa, "reunioes_proximas", "Reunião de orientação",
                     detalhe)


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
    # O filtro de vínculo ativo, presente nas outras três categorias, faltava
    # aqui: ata em rascunho de vínculo encerrado gerava aviso diário perpétuo,
    # mandando finalizar algo cuja tela já não oferece caminho.
    ativas = (
        select(AtaParticipacao.ata_id)
        .join(Orientacao, Orientacao.id == AtaParticipacao.orientacao_id)
        .where(Orientacao.status == "ativa")
    )
    itens = (
        Ata.query.options(
            joinedload(Ata.orientador),
            joinedload(Ata.participacoes)
            .joinedload(AtaParticipacao.orientacao)
            .joinedload(Orientacao.orientando),
        )
        .filter(
            Ata.status == "rascunho",
            Ata.data_reuniao < limite,
            Ata.id.in_(ativas),
        )
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
    marcos_a_vencer,
    reunioes_proximas,
    marcos_a_confirmar,
    versoes_sem_parecer,
    atas_em_rascunho,
)


# ---------------------------------------------------------------------------


def coletar() -> dict:
    """{Usuario: {chave_da_seção: [item, ...]}} para todos os pendentes.

    Conta desativada é excluída aqui, num ponto só, valendo para toda categoria:
    quem perdeu o acesso ao sistema não pode seguir recebendo nomes de
    orientandos, títulos de projeto e datas de reunião — é dado pessoal
    trafegando para fora, e sem meio de o titular fazer parar."""
    destino: dict = {}
    for categoria in CATEGORIAS:
        categoria(destino)
    return {
        pessoa: secoes for pessoa, secoes in destino.items() if pessoa.ativo
    }


ACRONIMO = (
    "Ambiente de Revisão, Integração, Acompanhamento Discente e "
    "Normatização de Estudos"
)
# O aviso de mensagem automática aparece duas vezes: uma linha logo após a
# saudação, para quem lê só o começo, e a explicação completa no rodapé. O
# remetente é uma caixa de e-mail real, então quem responder não recebe erro de
# entrega algum — a resposta simplesmente fica sem leitura. Dizer isso com todas
# as letras evita que alguém escreva esperando retorno.
AVISO_AUTOMATICO = (
    "Esta é uma mensagem automática, enviada por um sistema. "
    "Não responda a este e-mail: ninguém lê as respostas enviadas a "
    "este endereço."
)
RODAPE_QUEM_PROCURAR = (
    "Para tratar de assuntos da orientação, escreva diretamente ao seu "
    "orientador. Para problemas de acesso ao sistema — senha esquecida, por "
    "exemplo —, procure o administrador."
)
RODAPE_FREQUENCIA = (
    "Você recebe este aviso no máximo uma vez por dia, e somente quando há "
    "pendências registradas em seu nome. Resolvidas as pendências, os avisos "
    "cessam."
)


def endereco_do_sistema() -> str:
    """Endereço para o destinatário chegar ao sistema, **apenas** de `URL_BASE`.

    Deduzir do `request.url_root` era vulnerabilidade, não conveniência: o
    cabeçalho `Host` vem do cliente, e como o disparo é acionado por tráfego
    qualquer, bastava uma requisição com `Host: sitio-falso` no instante certo
    para que o botão "Abrir o ARIADNE" de todos os e-mails do dia apontasse ao
    domínio do atacante — página de captura de senha entregue por mensagem
    legítima, com o remetente institucional, à hora escolhida por ele.

    Sem `URL_BASE` configurado, a mensagem sai sem link. Perde-se conveniência;
    não se entrega ninguém."""
    configurado = current_app.config.get("URL_BASE")
    if configurado:
        return configurado.rstrip("/")
    current_app.logger.warning(
        "URL_BASE não configurado: os avisos sairão sem link para o sistema."
    )
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




def _contexto(pessoa, secoes: dict, url: str) -> dict:
    """Tudo o que os templates precisam. Reunido num ponto para que as duas
    versões da mensagem não possam divergir no que dizem — só no como."""
    return {
        "pessoa": pessoa,
        "secoes": secoes,
        "SECOES": SECOES,
        "total": _contar(secoes),
        "url": url,
        "acronimo": ACRONIMO,
        "aviso_automatico": AVISO_AUTOMATICO,
        "rodape_quem_procurar": RODAPE_QUEM_PROCURAR,
        "rodape_frequencia": RODAPE_FREQUENCIA,
    }


def corpo_texto(pessoa, secoes: dict, url: str) -> str:
    """Renderiza `emails/pendencias.txt`. A redação está lá, não aqui."""
    return render_template("emails/pendencias.txt", **_contexto(pessoa, secoes, url))


def corpo_html(pessoa, secoes: dict, url: str) -> str:
    """Renderiza `emails/pendencias.html`. O Jinja escapa os dados do usuário."""
    return render_template("emails/pendencias.html", **_contexto(pessoa, secoes, url))


def _agora() -> datetime:
    """UTC ingênuo, como o restante das colunas de data e hora do banco.
    Delega ao utilitário compartilhado; mantido como alias local porque os
    testes referenciam `avisos._agora`."""
    return tempo_agora()


def reservar_tentativa() -> bool:
    """Trava atômica: devolve True apenas a quem obteve o direito de tentar.

    Um único UPDATE condicional grava o instante da tentativa. Duas requisições
    simultâneas executam a mesma instrução, mas só uma encontra a linha
    elegível e altera algo — a outra recebe rowcount 0 e não envia.

    O que se reserva é a **tentativa**, não o dia: a marca de sucesso é gravada
    depois, e só havendo entrega. Assim um lote perdido por rede indisponível não
    consome o aviso do dia, e a requisição seguinte, passado o intervalo, tenta
    de novo. É o que torna o mecanismo tolerável numa rede intermitente — e a
    desta hospedagem é.

    **Confirma a própria transação antes de devolver.** No SQLite o UPDATE toma
    trava de escrita sobre o arquivo inteiro; mantê-la aberta durante a sessão
    SMTP faria qualquer outra requisição que gravasse — salvar rascunho, enviar
    documento, registrar login — esperar pela rede e, esgotado o tempo, receber
    `database is locked` e devolver erro 500. Quem dispara o envio não pode
    penalizar quem apenas usa o sistema. Confirmada a reserva, a trava fica com
    quem a obteve mesmo que o processo caia no meio do lote."""
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


def entregues_hoje() -> set:
    """Endereços já atendidos hoje. Registro de outro dia é descartado."""
    bruto = ConfiguracaoEmail.vigente().avisos_entregues
    if not bruto:
        return set()
    try:
        guardado = json.loads(bruto)
    except ValueError:
        return set()
    if guardado.get("dia") != date.today().isoformat():
        return set()
    return set(guardado.get("emails", []))


def registrar_entregues(enderecos: list) -> None:
    config = ConfiguracaoEmail.vigente()
    config.avisos_entregues = json.dumps(
        {
            "dia": date.today().isoformat(),
            "emails": sorted(entregues_hoje() | set(enderecos)),
        },
        ensure_ascii=False,
    )


def marcar_dia_como_enviado() -> None:
    """Encerra os disparos do dia. Chamado só quando nada ficou pendente."""
    db.session.execute(
        db.text(
            "UPDATE configuracao_email SET avisos_enviados_em = :hoje WHERE id = 1"
        ),
        {"hoje": date.today()},
    )


def disparar_se_devido() -> dict | None:
    """Tenta o envio do dia, respeitando trava, intervalo e quem já recebeu.

    Devolve o resumo quando houve tentativa, ou None quando não era hora.

    A ordem das confirmações é o que torna isto seguro. A reserva é confirmada
    **antes** do SMTP, para não segurar a trava de escrita do SQLite durante a
    rede. O registro de quem recebeu é confirmado **logo após** o envio, e antes
    de qualquer outra coisa: se a auditoria falhasse depois e arrastasse tudo num
    rollback, o lote inteiro seria reenviado na janela seguinte."""
    if not reservar_tentativa():
        return None
    db.session.commit()  # libera a trava de escrita antes de falar com a rede

    resumo = enviar_pendentes(ja_atendidos=entregues_hoje())

    if resumo["enviados"]:
        registrar_entregues(resumo["enviados"])
    # o dia se encerra quando nada ficou por entregar; havendo falha, a próxima
    # janela repete apenas para quem faltou
    if not resumo["falhas"]:
        marcar_dia_como_enviado()
    db.session.commit()
    return resumo


def enviar_pendentes(ja_atendidos: set | None = None) -> dict:
    """Monta e envia as mensagens do dia. Uma conexão SMTP para todas — abrir uma
    por destinatário multiplicaria a espera da requisição que disparou.

    `ja_atendidos` exclui quem já recebeu hoje, de modo que repetir uma tentativa
    parcialmente falha não duplique mensagem."""
    atendidos = ja_atendidos or set()
    destinatarios = {
        pessoa: secoes
        for pessoa, secoes in coletar().items()
        if pessoa.email not in atendidos
    }
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
