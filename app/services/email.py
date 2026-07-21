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
    if not config.operante:
        raise EnvioIndisponivel(
            "Envio de e-mail não está configurado ou está desabilitado."
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


def montar(destinatario: str, assunto: str, corpo: str) -> EmailMessage:
    mensagem = EmailMessage()
    mensagem["To"] = destinatario
    mensagem["Subject"] = assunto
    mensagem.set_content(corpo)
    return mensagem


def enviar(destinatario: str, assunto: str, corpo: str) -> bool:
    """Devolve True se entregou ao servidor SMTP. Nunca levanta exceção por
    falha de rede ou de autenticação: a operação que disparou o envio segue seu
    curso, e o motivo fica no log."""
    config = ConfiguracaoEmail.vigente()
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


def testar(destinatario: str) -> str:
    """Envia mensagem de conferência e devolve a causa em linguagem clara quando
    falha. Diferente de `enviar`, aqui o erro **deve** chegar ao administrador:
    ele está justamente tentando descobrir se a configuração funciona."""
    config = ConfiguracaoEmail.vigente()
    if not config.configurado:
        return "Informe usuário e senha de app antes de testar."
    try:
        _entregar(
            config,
            montar(
                destinatario,
                "ARIADNE — teste de configuração",
                "Se você recebeu esta mensagem, o envio de e-mail do ARIADNE "
                "está funcionando.\n\nNenhuma ação é necessária.",
            ),
        )
        return ""
    except SegredoIlegivel:
        return (
            "A senha guardada não pôde ser decifrada — provavelmente a chave do "
            "servidor (SECRET_KEY) mudou. Digite a senha de app novamente."
        )
    except smtplib.SMTPAuthenticationError:
        return (
            "O servidor recusou as credenciais. Com o Gmail, é preciso usar uma "
            "senha de app (16 caracteres, gerada em myaccount.google.com com a "
            "verificação em duas etapas ativa) — a senha comum da conta não "
            "funciona."
        )
    except (smtplib.SMTPException, OSError) as exc:
        return f"Não foi possível falar com {config.servidor}:{config.porta} — {exc}"
