"""Exclusão de versão de documento enviada por engano.

**Por que existe.** Versões eram permanentes sem exceção, e um envio duplicado
(o mesmo texto cadastrado de novo, num documento paralelo) ficava para sempre no
histórico, poluindo a tarefa e o Painel. A exclusão é a válvula para o engano —
não uma edição do histórico: por isso as travas abaixo.

**As travas, e por quê.**
- Só quem enviou, ou o administrador: ninguém apaga o trabalho de outra pessoa.
- Só a versão mais recente: apagar uma do meio deixaria lacuna (v1, v3) e
  reescreveria o passado de versões já lidas. O próximo envio reutiliza o número;
  a auditoria guarda o id, que desambigua.
- Nunca com parecer: o parecer avalia aquela versão, e o SQLite não impõe a chave
  estrangeira — a checagem é aqui.
- Nunca a versão-devolução: ela é parte do ato de devolver, registrado na tarefa.
- Nunca em tarefa concluída, nem a entrega da orientanda sob sinalização: apagar a
  entrega enquanto o orientador decide deixaria o ciclo sem objeto.
"""
from app.extensions import db
from app.models import Marco, Parecer, VersaoDocumento
from app.services import auditoria


def _tarefa(versao: VersaoDocumento):
    return versao.documento.marco


def motivo_bloqueio_exclusao(versao: VersaoDocumento, usuario) -> str | None:
    """`None` quando a exclusão é admitida; senão, o motivo em português, pronto
    para o usuário. Ponto único: decide o link na tela e a recusa na rota."""
    if versao.enviado_por != usuario.id and usuario.papel != "admin":
        return "Só quem enviou a versão (ou o administrador) pode excluí-la."
    atual = versao.documento.versao_atual
    if atual is None or atual.id != versao.id:
        return (
            "Só a versão mais recente pode ser excluída — as anteriores já fazem "
            "parte do histórico."
        )
    if db.session.query(
        Parecer.query.filter_by(versao_documento_id=versao.id).exists()
    ).scalar():
        return "Esta versão já recebeu parecer e não pode ser excluída."
    if versao.eh_devolucao:
        return (
            "Esta versão é a devolução registrada na tarefa e não pode ser excluída."
        )
    if apaga_o_documento(versao) and db.session.query(
        Marco.query.filter_by(documento_base_id=versao.documento_id).exists()
    ).scalar():
        return (
            "Este documento é o texto a revisar de uma tarefa; a única versão dele "
            "não pode ser excluída."
        )
    marco = _tarefa(versao)
    if marco is not None:
        if marco.status == "concluido":
            return "A tarefa desta versão já foi concluída."
        if marco.conclusao_sinalizada and versao.enviada_pela_orientanda:
            return (
                "A tarefa está sinalizada e aguarda o orientador conferir esta "
                "entrega. Para trocar o arquivo, envie uma nova versão."
            )
    return None


def apaga_o_documento(versao: VersaoDocumento) -> bool:
    """Excluir esta versão leva o documento junto? Sim, quando ela é a única."""
    return versao.documento.versoes.count() == 1


def excluir_versao(versao: VersaoDocumento, usuario) -> list[str]:
    """Exclui a versão (e o documento, se era a única) e devolve os nomes físicos
    a remover do disco — pelo chamador, DEPOIS do commit (`remover_do_disco`).
    Não faz commit. Levanta `ValueError` com o motivo se a exclusão é vedada."""
    motivo = motivo_bloqueio_exclusao(versao, usuario)
    if motivo:
        raise ValueError(motivo)
    documento = versao.documento
    arquivos = [versao.nome_fisico] if versao.nome_fisico else []
    arquivos += [anexo.nome_fisico for anexo in versao.anexos]
    leva_documento = apaga_o_documento(versao)
    auditoria.registrar(
        "exclusao_versao_documento",
        "documento",
        documento.id,
        {
            "titulo": documento.titulo,
            "versao": versao.numero_versao,
            "versao_id": versao.id,
            "arquivos": len(arquivos),
            "documento_apagado": leva_documento,
        },
    )
    db.session.delete(versao)  # os anexos saem pelo cascade
    if leva_documento:
        db.session.flush()
        db.session.delete(documento)
    return arquivos


def registrar_recusa(versao: VersaoDocumento, motivo: str) -> None:
    auditoria.registrar(
        "exclusao_versao_recusada",
        "versao_documento",
        versao.id,
        {"documento_id": versao.documento_id, "motivo": motivo},
    )
