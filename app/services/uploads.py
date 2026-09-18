"""Validação e armazenamento de arquivos enviados (riscos R2 e R6)."""
import os
import uuid

from flask import current_app
from sqlalchemy import event, func
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


def remover_do_disco(caminhos) -> list[str]:
    """Remove arquivos DEPOIS de o banco confirmar a exclusão dos registros, e
    devolve os nomes dos que resistiram (presos em download, sem permissão).

    Política única do pós-commit, num só lugar: a falha não levanta (o banco
    já foi confirmado — um 500 aqui mentiria que nada aconteceu), não fica só
    no log (o chamador EXIBE os que sobraram: arquivo com dado pessoal
    remanescente depois de remoção certificada é retenção silenciosa), e o já
    ausente conta como removido."""
    presos: list[str] = []
    for caminho in caminhos:
        try:
            os.remove(caminho)
        except FileNotFoundError:
            continue
        except OSError:
            current_app.logger.warning("arquivo não removido: %s", caminho)
            presos.append(os.path.basename(caminho))
    return presos


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


def salvar_versao(
    documento: Documento, storage, usuario, comentario: str | None = None,
    eh_devolucao: bool = False,
):
    """Grava o arquivo em disco sob UUID e cria a próxima versão do documento.
    A constraint UNIQUE(documento_id, numero_versao) é a salvaguarda final
    contra numeração concorrente."""
    ext = validar_arquivo(storage)
    nome_fisico = f"{uuid.uuid4().hex}.{ext}"

    pasta = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome_fisico)
    storage.save(caminho)
    # O arquivo vai a disco antes de a linha ser confirmada. Rastreia-o na sessão
    # para que um rollback posterior — colisão de numeração na UNIQUE ao dar
    # flush, ou "database is locked" no commit — não o deixe órfão na pasta de
    # uploads (que o backup ainda incluiria). A remoção fica nos eventos de
    # sessão abaixo, que cobrem todos os chamadores de salvar_versao.
    db.session.info.setdefault("uploads_novos", []).append(caminho)
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
        eh_devolucao=eh_devolucao,
    )
    db.session.add(versao)
    return versao


# Confirmada a transação, os arquivos rastreados estão referenciados por uma
# linha e devem permanecer; só se descarta o rastreio.
@event.listens_for(db.session, "after_commit")
def _uploads_confirmados(session):
    session.info.pop("uploads_novos", None)


# Revertida a transação (falha no flush/commit, ou o rollback do teardown da
# requisição), o arquivo gravado não tem linha que o referencie: remove-o.
@event.listens_for(db.session, "after_rollback")
def _uploads_descartados(session):
    # aqui não há tela a avisar (é o desfazer de uma falha); o retorno do
    # helper é dispensado e a sobra fica registrada no log por ele mesmo
    remover_do_disco(session.info.pop("uploads_novos", []))
