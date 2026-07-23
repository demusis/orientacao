"""Envio de e-mail por SMTP, com a configuração mantida pelo administrador.

Medição de 21/07/2026 no servidor de homologação: `smtp.gmail.com:587` conecta e
aceita STARTTLS; `smtp.office365.com:587` é bloqueado pela política de saída do
plano gratuito. Daí o Gmail ser o remetente previsto.

**O envio nunca derruba a operação que o disparou.** `enviar` devolve verdadeiro
ou falso e regista a falha no log; quem chama decide o que dizer ao usuário. Uma
troca de senha não pode falhar porque o servidor de e-mail estava fora do ar, e
uma tarefa de lembretes não pode abortar no primeiro destinatário inválido.
"""
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

from app.models import ConfiguracaoEmail
from app.services.cripto import SegredoIlegivel, decifrar

TEMPO_LIMITE = 15


class EnvioIndisponivel(Exception):
    """Configuração ausente, desabilitada ou ilegível — distinta de falha de
    rede, porque a correção é outra: configurar, não repetir."""


def _credenciais(config: ConfiguracaoEmail) -> tuple:
    """Exige apenas que haja credencial, e não que o envio esteja habilitado.

    A distinção não é sutil: o administrador precisa **testar antes de ligar**.
    Exigir `operante` aqui tornava impossível conferir a configuração sem antes
    habilitá-la às cegas — foi o defeito que produziu erro 500 em 21/07/2026. O
    interruptor `ativo` governa o envio automático, verificado em `enviar`."""
    if not config.configurado:
        raise EnvioIndisponivel(
            "Informe a conta de envio e a senha de app antes de enviar."
        )
    return config.usuario, decifrar(config.senha_cifrada)


def _entregar(config: ConfiguracaoEmail, mensagem: EmailMessage) -> None:
    """Conecta, autentica e entrega. Isolado para que o teste de configuração e
    o envio comum percorram exatamente o mesmo caminho — um teste que exercitasse
    outro código não provaria nada sobre o envio real."""
    usuario, senha = _credenciais(config)
    mensagem["From"] = f"{config.remetente_nome} <{usuario}>"

    contexto = ssl.create_default_context()
    if config.porta == 465:
        with smtplib.SMTP_SSL(
            config.servidor, config.porta, timeout=TEMPO_LIMITE, context=contexto
        ) as s:
            s.login(usuario, senha)
            s.send_message(mensagem)
    else:
        with smtplib.SMTP(config.servidor, config.porta, timeout=TEMPO_LIMITE) as s:
            s.starttls(context=contexto)
            s.login(usuario, senha)
            s.send_message(mensagem)


def montar(
    destinatario: str, assunto: str, corpo: str, corpo_html: str | None = None
) -> EmailMessage:
    """Mensagem em texto simples; havendo `corpo_html`, vira multipart/alternative.

    O texto é sempre a primeira parte, e não um resumo do HTML: é o que aparece
    em cliente que não exibe HTML, em leitor de tela e na pré-visualização da
    caixa de entrada. Uma mensagem cujo texto diga "veja a versão HTML" é uma
    mensagem quebrada para parte dos destinatários."""
    mensagem = EmailMessage()
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(corpo)
    if corpo_html:
        mensagem.add_alternative(corpo_html, subtype="html")
    return mensagem


def enviar(destinatario: str, assunto: str, corpo: str) -> bool:
    """Devolve True se entregou ao servidor SMTP. Nunca levanta exceção por
    falha de rede ou de autenticação: a operação que disparou o envio segue seu
    curso, e o motivo fica no log."""
    config = ConfiguracaoEmail.vigente()
    if not config.ativo:
        # o interruptor vale para o envio automático; o teste manual o ignora
        current_app.logger.info("E-mail não enviado: envio desabilitado.")
        return False
    try:
        _entregar(config, montar(destinatario, assunto, corpo))
        return True
    except (EnvioIndisponivel, SegredoIlegivel) as exc:
        current_app.logger.warning("E-mail não enviado (configuração): %s", exc)
    except (smtplib.SMTPException, OSError) as exc:
        current_app.logger.warning(
            "E-mail não enviado para %s: %s", destinatario, exc
        )
    return False


def _conectar(config: ConfiguracaoEmail):
    """Abre e autentica a sessão SMTP. Devolve o objeto para uso em `with`."""
    usuario, senha = _credenciais(config)
    contexto = ssl.create_default_context()
    if config.porta == 465:
        sessao = smtplib.SMTP_SSL(
            config.servidor, config.porta, timeout=TEMPO_LIMITE, context=contexto
        )
    else:
        sessao = smtplib.SMTP(config.servidor, config.porta, timeout=TEMPO_LIMITE)
        sessao.starttls(context=contexto)
    sessao.login(usuario, senha)
    return sessao, usuario


def enviar_lote(mensagens: list[tuple]) -> tuple[list, list]:
    """Entrega várias mensagens por **uma única conexão**, devolvendo
    (entregues, falhas) por endereço. Cada item é
    `(destinatario, assunto, corpo[, corpo_html])`.

    Abrir uma conexão por destinatário multiplicaria a espera de quem disparou o
    envio — e quem dispara, aqui, é uma requisição comum de usuário. Falha em um
    destinatário não interrompe os demais; falha de conexão perde o lote inteiro,
    e é isso que a lista de falhas informa."""
    config = ConfiguracaoEmail.vigente()
    if not config.ativo:
        return [], [m[0] for m in mensagens]

    entregues, falhas = [], []
    try:
        sessao, usuario = _conectar(config)
    except (EnvioIndisponivel, SegredoIlegivel, smtplib.SMTPException, OSError) as exc:
        current_app.logger.warning("Lote não enviado (conexão): %s", exc)
        return [], [m[0] for m in mensagens]

    try:
        for destinatario, assunto, corpo, *html in mensagens:
            mensagem = montar(destinatario, assunto, corpo, html[0] if html else None)
            mensagem["From"] = f"{config.remetente_nome} <{usuario}>"
            try:
                sessao.send_message(mensagem)
                entregues.append(destinatario)
            except (smtplib.SMTPException, OSError) as exc:
                current_app.logger.warning(
                    "Aviso não entregue a %s: %s", destinatario, exc
                )
                falhas.append(destinatario)
    finally:
        try:
            sessao.quit()
        except (smtplib.SMTPException, OSError):
            pass
    return entregues, falhas


def testar(destinatario: str) -> str:
    """Envia mensagem de conferência e devolve a causa em linguagem clara quando
    falha. Diferente de `enviar`, aqui o erro **deve** chegar ao administrador:
    ele está justamente tentando descobrir se a configuração funciona."""
    config = ConfiguracaoEmail.vigente()
    try:
        _entregar(
            config,
            montar(
                destinatario,
                "ARIADNE: teste de configuração",
                "Se você recebeu esta mensagem, o envio de e-mail do ARIADNE "
                "está funcionando.\n\nNenhuma ação é necessária.",
            ),
        )
        return ""
    except EnvioIndisponivel as exc:
        # captura indispensável: sem ela a exceção escapava como erro 500
        return str(exc)
    except SegredoIlegivel:
        return (
            "A senha guardada não pôde ser decifrada; provavelmente a chave do "
            "servidor (SECRET_KEY) mudou. Digite a senha de app novamente."
        )
    except smtplib.SMTPAuthenticationError:
        return (
            "O servidor recusou as credenciais. Com o Gmail, é preciso usar uma "
            "senha de app (16 caracteres, gerada em myaccount.google.com com a "
            "verificação em duas etapas ativa). A senha comum da conta não "
            "funciona."
        )
    except (smtplib.SMTPException, OSError) as exc:
        return f"Não foi possível falar com {config.servidor}:{config.porta}. {exc}"
