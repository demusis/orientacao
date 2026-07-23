"""Aviso de reunião aos convidados, enviado no ato.

**Por que no ato, e não no lote diário.** O lote de `avisos.py` comunica
pendência, que é estado: pode esperar o dia seguinte sem prejuízo. Convite é
evento, e um convite que chega depois da reunião não é convite. O preço é a
sessão SMTP dentro da requisição, de 1 a 3 segundos, o mesmo que a recuperação de
senha já paga.

**Sempre depois do commit.** `enviar_lote` conversa com a rede; chamá-lo com a
transação aberta seguraria a trava de escrita do SQLite e faria qualquer outra
requisição que gravasse receber `database is locked`. O raciocínio completo está
em `avisos.reservar_tentativa`.

**Nunca derruba a operação.** `enviar_lote` não levanta exceção: a reunião fica
agendada mesmo com o servidor de e-mail fora do ar, e quem convocou é informado
de que o aviso não saiu.
"""
from flask import render_template

from app.services import auditoria
from app.services import email as email_service
from app.services.avisos import endereco_do_sistema

# Cada evento traz o verbo da linha de assunto e a frase que abre a mensagem. O
# destinatário precisa saber, na primeira linha, o que mudou na agenda dele.
EVENTOS = {
    "agendada": {
        "assunto": "Reunião de orientação agendada",
        "abertura": "Uma reunião de orientação foi agendada.",
    },
    "remarcada": {
        "assunto": "Reunião de orientação remarcada",
        "abertura": "A data da reunião de orientação mudou. Anote a nova.",
    },
    "cancelada": {
        "assunto": "Reunião de orientação cancelada",
        "abertura": "A reunião de orientação foi cancelada e não vai ocorrer.",
    },
    "convidados_alterados": {
        "assunto": "Reunião de orientação: participantes alterados",
        "abertura": (
            "A lista de participantes da reunião de orientação foi alterada."
        ),
    },
}


def destinatarios(ata, retirados=None) -> list:
    """Quem vai à reunião: orientandos dos vínculos convidados, coorientadores
    desses vínculos e o orientador que convocou.

    Difere da convenção de `avisos.py`, onde o coorientador não recebe. Lá o
    assunto é pendência de terceiro; aqui, a agenda de quem participa.

    `retirados` (vínculos que acabaram de sair da reunião) entra na lista: quem
    foi desconvidado é justamente quem mais precisa saber, e como já não consta
    de `ata.orientacoes` no instante do envio, teria de ser informado à parte ou
    seguiria acreditando que a reunião está de pé.

    Conta desativada é excluída, como em `avisos.coletar`: quem perdeu o acesso
    não segue recebendo nome de orientando e título de projeto. A deduplicação é
    por e-mail, e não por id, porque a mesma pessoa pode entrar por dois vínculos
    e receberia a mensagem duas vezes."""
    pessoas = [ata.orientador]
    for orientacao in list(ata.orientacoes) + list(retirados or []):
        pessoas.append(orientacao.orientando)
        pessoas.extend(orientacao.coorientadores)

    vistos, unicos = set(), []
    for pessoa in pessoas:
        if pessoa is None or not pessoa.ativo or not pessoa.email:
            continue
        if pessoa.email in vistos:
            continue
        vistos.add(pessoa.email)
        unicos.append(pessoa)
    return unicos


def _contexto(ata, evento: str, url: str) -> dict:
    """Reunido num ponto para que as duas versões da mensagem não divirjam no
    que dizem, apenas no como."""
    return {
        "ata": ata,
        "evento": evento,
        "rotulos": EVENTOS[evento],
        "participantes": [o.orientando.nome for o in ata.orientacoes],
        "url": url,
        "aviso_automatico": (
            "Esta é uma mensagem automática, enviada por um sistema. "
            "Não responda a este e-mail: ninguém lê as respostas enviadas a "
            "este endereço."
        ),
    }


def assunto(ata, evento: str) -> str:
    quando = ata.data_reuniao.strftime("%d/%m/%Y")
    if ata.hora_reuniao:
        quando += ata.hora_reuniao.strftime(" às %H:%M")
    return f"ARIADNE: {EVENTOS[evento]['assunto']} ({quando})"


def notificar(ata, evento: str, retirados=None) -> tuple[list, list]:
    """Avisa os convidados e devolve (entregues, falhas) por endereço.

    `retirados` são vínculos que acabaram de deixar a reunião; recebem o aviso
    junto com quem ficou.

    Chamar **depois** do commit. Registra o resultado em auditoria, mas não dá
    commit desse registro: quem chama o faz, para que um erro no envio não
    arraste a operação já concluída."""
    if evento not in EVENTOS:
        raise ValueError(f"Evento de convite desconhecido: {evento}")

    pessoas = destinatarios(ata, retirados)
    if not pessoas:
        return [], []

    url = endereco_do_sistema()
    contexto = _contexto(ata, evento, url)
    corpo_texto = render_template("emails/convite.txt", **contexto)
    corpo_html = render_template("emails/convite.html", **contexto)
    linha = assunto(ata, evento)

    entregues, falhas = email_service.enviar_lote(
        [(p.email, linha, corpo_texto, corpo_html) for p in pessoas]
    )
    auditoria.registrar(
        "envio_convite",
        "ata",
        ata.id,
        {"evento": evento, "enviados": entregues, "falhas": falhas},
    )
    return entregues, falhas


def mensagem_de_resultado(entregues: list, falhas: list) -> tuple[str, str]:
    """Frase e categoria do flash. O usuário precisa saber se o convite saiu:
    dizer apenas "reunião agendada" esconderia que ninguém foi avisado."""
    if not entregues and not falhas:
        return "Nenhum convidado ativo para avisar.", "warning"
    if not falhas:
        return f"Aviso enviado a {len(entregues)} participante(s).", "success"
    if not entregues:
        return (
            "O aviso não pôde ser enviado a nenhum participante. Confira a "
            "configuração de e-mail; a reunião ficou registrada.",
            "warning",
        )
    return (
        f"Aviso enviado a {len(entregues)} participante(s); "
        f"{len(falhas)} não receberam.",
        "warning",
    )
