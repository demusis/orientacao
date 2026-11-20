"""Entrega pela tarefa: nova versão de um documento da tarefa ou documento novo
ligado a ela e, para a orientanda, a opção de já avisar o orientador
(sinalizar) no mesmo ato.

Ponto único usado pela página da tarefa (web) e pela API do aplicativo móvel,
para que as duas portas apliquem as mesmas regras. Não faz commit."""
from dataclasses import dataclass

from app.extensions import db
from app.models import Documento, Marco
from app.services import auditoria
from app.services import cronogramas as servico_cronograma
from app.services.uploads import salvar_versao


@dataclass
class ResultadoEntrega:
    documento: Documento
    versao: object
    novo: bool
    sinalizou: bool

    def mensagem(self) -> str:
        if self.novo:
            msg = f'Documento "{self.documento.titulo}" criado (versão 1).'
        else:
            msg = (
                f'Versão {self.versao.numero_versao} de '
                f'"{self.documento.titulo}" enviada.'
            )
        if self.sinalizou:
            msg += " O orientador foi avisado para conferir."
        return msg


def registrar_entrega(
    marco: Marco,
    usuario,
    *,
    documento: Documento | None = None,
    titulo: str | None = None,
    arquivo=None,
    anexos=None,
    comentario: str | None = None,
    em_nome_do_orientando: bool = False,
    sinalizar: bool = False,
) -> ResultadoEntrega:
    """`documento=None` cria um documento novo (exige `titulo`); senão grava a
    próxima versão do documento informado, que deve pertencer à tarefa.
    `sinalizar` só tem efeito quando `pode_sinalizar` permite. Levanta
    `UploadInvalido` (arquivo recusado) ou `ValueError` (dados incoerentes)."""
    novo = documento is None
    if novo:
        titulo = (titulo or "").strip()
        if not titulo:
            raise ValueError("Informe o título do documento novo.")
        documento = Documento(
            orientacao_id=marco.orientacao_id,
            marco_id=marco.id,
            titulo=titulo,
            criado_por=usuario.id,
        )
        db.session.add(documento)
        db.session.flush()
    elif documento not in marco.documentos_da_tarefa:
        raise ValueError("O documento escolhido não pertence a esta tarefa.")

    versao = salvar_versao(
        documento, arquivo or None, usuario, comentario,
        em_nome_do_orientando=em_nome_do_orientando, anexos=anexos,
    )
    db.session.flush()
    dados = {"anexos": len(versao.anexos), "origem": "marco", "marco_id": marco.id,
             "natureza": versao.natureza}
    if novo:
        auditoria.registrar(
            "criacao_documento", "documento", documento.id,
            {"titulo": documento.titulo, "arquivo": versao.nome_original, **dados},
        )
    else:
        auditoria.registrar(
            "nova_versao_documento", "versao_documento", versao.id,
            {"documento_id": documento.id, "versao": versao.numero_versao, **dados},
        )
    sinalizou = bool(sinalizar) and servico_cronograma.pode_sinalizar(marco, usuario)
    if sinalizou:
        servico_cronograma.sinalizar_conclusao(marco)
    return ResultadoEntrega(documento, versao, novo, sinalizou)
