"""Validação e armazenamento de arquivos enviados (riscos R2 e R6)."""
import os
import uuid

from flask import current_app
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Documento, VersaoDocumento

# Assinaturas mínimas por extensão. .docx/.odt/.zip são contêineres ZIP ("PK").
ASSINATURAS = {
    "pdf": [b"%PDF"],
    "docx": [b"PK\x03\x04"],
    "odt": [b"PK\x03\x04"],
    "zip": [b"PK\x03\x04"],
    "doc": [b"\xd0\xcf\x11\xe0"],  # OLE2
    "txt": None,  # texto plano: sem assinatura verificável
}


class UploadInvalido(Exception):
    pass


def _extensao(nome: str) -> str:
    return nome.rsplit(".", 1)[-1].lower() if "." in nome else ""


def validar_arquivo(storage) -> str:
    """Valida nome, extensão e assinatura. Retorna a extensão normalizada."""
    nome = secure_filename(storage.filename or "")
    if not nome:
        raise UploadInvalido("Nome de arquivo inválido.")

    ext = _extensao(nome)
    permitidas = current_app.config["ALLOWED_EXTENSIONS"]
    if ext not in permitidas:
        raise UploadInvalido(
            f"Extensão .{ext or '?'} não permitida. Aceitas: {', '.join(sorted(permitidas))}."
        )

    assinaturas = ASSINATURAS.get(ext)
    if assinaturas is not None:
        cabecalho = storage.stream.read(8)
        storage.stream.seek(0)
        if not any(cabecalho.startswith(a) for a in assinaturas):
            raise UploadInvalido(
                "Conteúdo do arquivo não corresponde à extensão declarada."
            )
    return ext


def salvar_versao(documento: Documento, storage, usuario, comentario: str | None = None):
    """Grava o arquivo em disco sob UUID e cria a próxima versão do documento.
    A constraint UNIQUE(documento_id, numero_versao) é a salvaguarda final
    contra numeração concorrente."""
    ext = validar_arquivo(storage)
    nome_fisico = f"{uuid.uuid4().hex}.{ext}"

    pasta = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome_fisico)
    storage.save(caminho)
    tamanho = os.path.getsize(caminho)

    proxima = (
        db.session.query(func.coalesce(func.max(VersaoDocumento.numero_versao), 0))
        .filter_by(documento_id=documento.id)
        .scalar()
        + 1
    )
    versao = VersaoDocumento(
        documento_id=documento.id,
        numero_versao=proxima,
        nome_original=secure_filename(storage.filename),
        nome_fisico=nome_fisico,
        tamanho_bytes=tamanho,
        mimetype=storage.mimetype or "application/octet-stream",
        enviado_por=usuario.id,
        comentario=comentario,
    )
    db.session.add(versao)
    return versao
