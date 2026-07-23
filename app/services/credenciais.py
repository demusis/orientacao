"""Envio das credenciais de acesso ao titular da conta.

**Por que a senha vai no corpo da mensagem.** O sistema já tem recuperação por
link expirável (`services/recuperacao.py`), que é a via preferível quando o
titular pede. Aqui o caso é outro: a conta acaba de ser criada, ou o
administrador repôs o acesso de quem não consegue mais entrar. Mandar apenas um
link deixaria a conta inacessível se a mensagem se perdesse, e o titular sem
nada a apresentar ao administrador. A senha no corpo é o que torna o primeiro
acesso autossuficiente.

**O que compensa a exposição.** A senha é gerada, não escolhida, de modo que não
se repete em outro serviço; e nasce marcada como provisória, o que prende a
conta à tela de troca até que o titular escolha a sua. Quem a obtiver não navega
pelo sistema: só consegue trocá-la, e a troca é o que a invalida.

**O que não se promete.** A senha provisória **não expira sozinha**: vale até
ser trocada. Uma conta criada e nunca acessada mantém viva a senha que está na
caixa de e-mail, e é por isso que a reposição existe. Dar-lhe prazo exigiria
guardar o instante da geração e recusá-la no login depois de N dias, com um
caminho de volta para quem perdesse o prazo.

**Nunca derruba a operação.** `enviar_lote` não levanta exceção. A conta fica
criada mesmo com o servidor de e-mail fora do ar, e quem executou recebe a senha
na tela para entregá-la por outro meio; do contrário, uma falha de rede deixaria
uma conta cadastrada e inacessível.
"""
from flask import render_template

from app.services import auditoria
from app.services import email as email_service
from app.services.avisos import endereco_do_sistema

EVENTOS = {
    "criacao": {
        "assunto": "Seu acesso ao ARIADNE",
        "abertura": (
            "Sua conta no ARIADNE foi criada. Abaixo estão os dados de acesso."
        ),
    },
    "reposicao": {
        "assunto": "Nova senha de acesso ao ARIADNE",
        "abertura": (
            "O administrador gerou uma senha temporária para a sua conta no "
            "ARIADNE. A senha anterior deixou de valer."
        ),
    },
}


def assunto(evento: str) -> str:
    return f"ARIADNE: {EVENTOS[evento]['assunto']}"


def envio_configurado() -> bool:
    """Se há conta de envio habilitada.

    Distingue "não configurado" de "falhou": no primeiro caso não houve
    tentativa alguma, e a ação certa é ir à tela de E-mail, não repetir a
    operação. `enviar_lote` devolve a mesma lista de falhas nos dois casos."""
    from app.models import ConfiguracaoEmail

    return bool(ConfiguracaoEmail.vigente().ativo)


def enviar(usuario, senha: str, evento: str) -> bool:
    """Entrega as credenciais e devolve se a mensagem saiu.

    Chamar **depois** do commit: `enviar_lote` fala com a rede, e mantê-la
    aberta dentro da transação seguraria a trava de escrita do SQLite. O
    raciocínio completo está em `avisos.reservar_tentativa`.

    Registra o resultado em auditoria **sem a senha**, que jamais entra na
    trilha: ela é legível pelo administrador na tela de auditoria, e o ponto de
    marcá-la como provisória é justamente encurtar quem pode usá-la."""
    if evento not in EVENTOS:
        raise ValueError(f"Evento de credencial desconhecido: {evento}")

    contexto = {
        "usuario": usuario,
        "senha": senha,
        "evento": evento,
        "rotulos": EVENTOS[evento],
        "url": endereco_do_sistema(),
        "aviso_automatico": (
            "Esta é uma mensagem automática, enviada por um sistema. "
            "Não responda a este e-mail: ninguém lê as respostas enviadas a "
            "este endereço."
        ),
    }
    entregues, _ = email_service.enviar_lote(
        [
            (
                usuario.email,
                assunto(evento),
                render_template("emails/credenciais.txt", **contexto),
                render_template("emails/credenciais.html", **contexto),
            )
        ]
    )
    enviado = bool(entregues)
    auditoria.registrar(
        "envio_credenciais",
        "usuario",
        usuario.id,
        {"evento": evento, "enviado": enviado},
    )
    return enviado


def mensagem_de_sucesso(usuario) -> str:
    return (
        f"Credenciais enviadas para {usuario.email}. "
        "A troca da senha será exigida no primeiro acesso."
    )


def motivo_de_falha() -> str:
    """Por que o e-mail não saiu, na linguagem da ação corretiva.

    Sem envio configurado, "não pôde ser enviado" soaria como problema
    transitório e induziria a tentar de novo, quando o que falta é configurar a
    conta de envio. Num sistema recém-implantado esse é o caso normal, não o
    excepcional."""
    if not envio_configurado():
        return (
            "O envio de e-mail não está configurado (menu E-mail), de modo que "
            "nenhuma mensagem foi enviada."
        )
    return (
        "O e-mail não pôde ser enviado. Confira a configuração de envio, no "
        "menu E-mail."
    )
