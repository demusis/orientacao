"""Criação de tarefas em lote: um marco idêntico no cronograma de cada
orientando selecionado.

Ponto único porque há dois caminhos até aqui: a tela de Reuniões e a página da
própria reunião, que deriva a tarefa do que foi decidido. Duplicar a regra faria
os dois divergirem no que gravam e no que auditam.

O acompanhamento permanece **individual**: `grupo_id` marca a origem comum, mas
status, sinalização e atraso de cada marco seguem por conta de cada orientando.
"""
import uuid

from app.extensions import db
from app.models import Marco
from app.services import auditoria


def criar_tarefa(vinculos, *, titulo, tipo, descricao, data_prevista, etapa, ata=None):
    """Cria um marco por vínculo e devolve a lista.

    `ata`, quando informada, liga cada marco à reunião que o originou: a tarefa
    derivada passa a figurar entre os marcos discutidos, e a ligação aparece no
    cronograma e na linha do tempo.

    Não dá commit: quem chama decide o momento."""
    # identificador de origem comum apenas quando a tarefa é coletiva
    grupo_id = uuid.uuid4().hex if len(vinculos) > 1 else None
    criados = []
    for orientacao in vinculos:
        marco = Marco(
            orientacao_id=orientacao.id,
            titulo=titulo,
            tipo=tipo,
            descricao=descricao,
            data_prevista=data_prevista,
            etapa=etapa,
            grupo_id=grupo_id,
        )
        db.session.add(marco)
        criados.append(marco)
    if ata is not None:
        ata.marcos = list(ata.marcos) + criados

    # um registro para N marcos: entidade_id fica no primeiro e a lista completa
    # nos dados, para que o log seja correlacionável
    db.session.flush()
    dados = {
        "grupo_id": grupo_id,
        "titulo": titulo,
        "marcos": [m.id for m in criados],
        "orientacoes": [o.id for o in vinculos],
    }
    if ata is not None:
        dados["ata_id"] = ata.id
    auditoria.registrar(
        "criacao_marco_grupo" if grupo_id else "criacao_marco",
        "marco",
        criados[0].id if criados else None,
        dados,
    )
    return criados
