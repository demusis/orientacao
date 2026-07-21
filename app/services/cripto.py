"""Cifragem de segredos guardados no banco (hoje, a senha de app do SMTP).

**O que isto protege e o que não protege.** A aplicação precisa da senha em
claro para autenticar no servidor de e-mail, logo precisa saber decifrá-la, logo
a chave tem de estar ao seu alcance. Daí decorre o limite: **quem obtiver o
servidor inteiro obtém também a chave** e nada aqui o detém. Cifrar o campo não
substitui as duas defesas que de fato reduzem o estrago — usar conta de e-mail
dedicada, e não a pessoal, e poder revogar a senha de app isoladamente.

O que a cifragem resolve é a ameaça mais provável, e ela não é a invasão: é o
**vazamento do banco separado do servidor**. O pacote de backup gerado em
`/admin/backup` é levado para fora e guardado em outro lugar; uma cópia do
`.sqlite` circula para diagnóstico; alguém com leitura da base a inspeciona. Em
todos esses casos o segredo viaja sem a chave, que fica na variável de ambiente
do servidor. Por isso a tabela de configuração também **não entra no backup**
(ver `services/backup.py`): defesa em profundidade, não substituto.

A chave deriva de SECRET_KEY. Trocar SECRET_KEY torna o que estava cifrado
ilegível — situação tratada como "não configurado", jamais como falha: o
administrador reinsere a senha.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

# Rótulo de domínio: garante que a chave derivada aqui não coincida com nenhuma
# outra derivada de SECRET_KEY para outra finalidade.
CONTEXTO = b"ariadne.cripto.v1"


class SegredoIlegivel(Exception):
    """Cifrado com outra SECRET_KEY, ou corrompido."""


def _fernet() -> Fernet:
    semente = current_app.config["SECRET_KEY"]
    if isinstance(semente, str):
        semente = semente.encode("utf-8")
    # PBKDF2 com salt fixo: o objetivo é derivar uma chave estável de 32 bytes a
    # partir de SECRET_KEY, não resistir a ataque de dicionário sobre senha de
    # usuário — SECRET_KEY já é material de alta entropia.
    bruto = hashlib.pbkdf2_hmac("sha256", semente, CONTEXTO, 100_000, dklen=32)
    return Fernet(base64.urlsafe_b64encode(bruto))


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def decifrar(cifrado: str) -> str:
    try:
        return _fernet().decrypt(cifrado.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise SegredoIlegivel(
            "Segredo ilegível: provavelmente cifrado sob outra SECRET_KEY. "
            "Reinsira a senha na tela de configuração."
        ) from exc
