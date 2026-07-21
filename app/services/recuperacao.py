"""Recuperação de senha por token assinado, sem tabela nem estado no banco.

O token não guarda segredo: leva apenas o id do usuário, assinado com
`SECRET_KEY` por um `URLSafeTimedSerializer` que carimba o instante. A validade
vem do `max_age` na leitura; a autenticidade, da assinatura.

**Uso único sem coluna de controle.** O salt da assinatura inclui um trecho do
hash da senha vigente. Redefinida a senha, o hash muda, o salt muda, e o token
emitido antes deixa de validar — sem precisar marcá-lo como usado. É o mesmo
princípio do `get_session_auth_hash` do Django. Como efeito, um segundo pedido
de recuperação também invalida o link do primeiro.
"""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app

from app.models import Usuario

VALIDADE_SEGUNDOS = 3600  # uma hora
_SALT = "ariadne.recuperacao.v1"


def _serializador() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def _assinatura_da_senha(usuario: Usuario) -> str:
    """Trecho estável do hash da senha. Muda quando a senha muda, o que é o que
    torna o token de uso único; não expõe o hash inteiro."""
    return (usuario.senha_hash or "")[-16:]


def gerar_token(usuario: Usuario) -> str:
    return _serializador().dumps(
        {"uid": usuario.id, "sh": _assinatura_da_senha(usuario)}
    )


def usuario_do_token(token: str) -> Usuario | None:
    """Devolve o usuário se o token é autêntico, não expirou e ainda casa com a
    senha vigente; None em qualquer outro caso. Nunca distingue os motivos para
    quem chama — a tela não deve revelar por que um link falhou."""
    try:
        dados = _serializador().loads(token, max_age=VALIDADE_SEGUNDOS)
    except (SignatureExpired, BadSignature, TypeError, ValueError):
        return None
    usuario = current_app and Usuario.query.get(dados.get("uid"))
    if usuario is None or not usuario.ativo:
        return None
    if dados.get("sh") != _assinatura_da_senha(usuario):
        return None  # senha já foi trocada desde a emissão
    return usuario
