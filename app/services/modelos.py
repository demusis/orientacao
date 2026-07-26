"""Modelos de documento: acervo global de arquivos-modelo gerido pelo admin.

Reaproveita a validação e o esquema de armazenamento das versões de documento
(services/uploads.py): valida antes de gravar, gera nome físico UUID e mede o
tamanho no disco. O commit fica a cargo da rota, como em salvar_versao."""
import os
import uuid

from flask import current_app
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import ModeloDocumento
from app.services.uploads import UploadInvalido, validar_arquivo  # noqa: F401


def salvar_modelo(storage, *, titulo: str, descricao: str | None, autor) -> ModeloDocumento:
    """Valida e grava o arquivo-modelo sob UUID, criando o registro (sem commit)."""
    ext = validar_arquivo(storage)
    nome_fisico = f"{uuid.uuid4().hex}.{ext}"

    pasta = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome_fisico)
    storage.save(caminho)
    # rastreia para o rollback remover o arquivo órfão, como em salvar_versao —
    # os eventos de sessão em services/uploads.py cuidam da remoção
    db.session.info.setdefault("uploads_novos", []).append(caminho)
    tamanho = os.path.getsize(caminho)

    modelo = ModeloDocumento(
        titulo=titulo,
        descricao=descricao or None,
        nome_original=secure_filename(storage.filename),
        nome_fisico=nome_fisico,
        tamanho_bytes=tamanho,
        mimetype=storage.mimetype or "application/octet-stream",
        enviado_por=autor.id if autor else None,
    )
    db.session.add(modelo)
    return modelo


def excluir_modelo(modelo: ModeloDocumento) -> str:
    """Remove o registro e devolve o caminho do arquivo físico, que o chamador
    apaga **depois** do commit. Modelos não são referenciados por outros
    registros, logo a exclusão física é segura (sem regra de histórico).

    A ordem importa: apagar o arquivo antes do commit deixaria, numa falha do
    commit (`database is locked`), o registro restaurado pelo rollback apontando
    para um arquivo já perdido — modelo listado para todos, download quebrado
    para sempre. Banco primeiro, disco depois, como na eliminação LGPD."""
    caminho = os.path.join(current_app.config["UPLOAD_FOLDER"], modelo.nome_fisico)
    db.session.delete(modelo)
    return caminho
