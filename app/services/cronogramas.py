"""Regras de cronograma: modelo-padrão de marcos por modalidade.

Os marcos-padrão dão um ponto de partida ao cronograma, que de outro modo nasce
vazio — e, vazio, o ciclo de sinalização/confirmação (o núcleo do acompanhamento)
não chega a ser percorrido. As datas são sugestões, contadas a partir do início
do vínculo, e ficam livremente ajustáveis depois de semeadas.
"""
from datetime import date, timedelta

from app.extensions import db
from app.models import Marco
from app.services import auditoria
from app.services.tempo import agora, hoje_local

# Modelo por modalidade: (título, tipo, etapa, mês a partir de data_inicio). É o
# único ponto a editar para mudar o que se semeia. Tipos válidos: TIPOS_MARCO em
# models/cronograma.py; etapas: ETAPA_MARCO_LABEL (10 a 60).
CRONOGRAMAS_PADRAO = {
    "ic": [  # ~12 meses
        ("Plano de trabalho", "projeto", 10, 1),
        ("Relatório parcial", "relatorio", 30, 6),
        ("Relatório final", "relatorio", 60, 12),
    ],
    "mestrado": [  # ~24 meses
        ("Projeto de pesquisa", "projeto", 10, 3),
        ("Submissão ao Comitê de Ética", "comite_etica", 10, 4),
        ("Exame de qualificação", "qualificacao", 40, 14),
        ("Defesa da dissertação", "defesa", 60, 22),
    ],
    "doutorado": [  # ~48 meses
        ("Projeto de pesquisa", "projeto", 10, 4),
        ("Submissão ao Comitê de Ética", "comite_etica", 10, 5),
        ("Exame de qualificação", "qualificacao", 40, 24),
        ("Publicação de artigo", "publicacao", 50, 36),
        ("Defesa da tese", "defesa", 60, 46),
    ],
}


def _add_meses(data: date, meses: int) -> date:
    """Soma `meses` a uma data, sem depender de dateutil. Se o dia de origem não
    existe no mês de destino (31 de janeiro + 1 mês), recua para o último dia
    daquele mês, em vez de estourar."""
    total = data.month - 1 + meses
    ano = data.year + total // 12
    mes = total % 12 + 1
    proximo_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    ultimo_dia = (proximo_mes - timedelta(days=1)).day
    return date(ano, mes, min(data.day, ultimo_dia))


def semear_cronograma(orientacao) -> list[Marco]:
    """Cria os marcos-padrão da modalidade do vínculo, com data prevista sugerida
    a partir de `data_inicio`. Adiciona-os à sessão e os devolve; o commit e a
    auditoria ficam a cargo do chamador. Modalidade sem modelo devolve lista
    vazia."""
    criados = []
    for titulo, tipo, etapa, meses in CRONOGRAMAS_PADRAO.get(orientacao.modalidade, []):
        marco = Marco(
            orientacao_id=orientacao.id,
            titulo=titulo,
            tipo=tipo,
            etapa=etapa,
            data_prevista=_add_meses(orientacao.data_inicio, meses),
        )
        db.session.add(marco)
        criados.append(marco)
    return criados


def confirmar_conclusao(marco: Marco) -> bool:
    """Confirma a conclusão do marco (o segundo passo do ciclo, a cargo do
    orientador): marca-o como concluído na data de hoje e registra na trilha.
    Devolve False, sem efeito, se já estava concluído. **Não faz commit** — a
    transação é do chamador, para que a confirmação participe do mesmo commit da
    operação que a acompanha (a rota de confirmação, ou a emissão de um parecer
    que fecha o marco)."""
    if marco.status == "concluido":
        return False
    marco.status = "concluido"
    # data de parede local, como toda data exibida ao lado das digitadas
    marco.data_conclusao = hoje_local()
    auditoria.registrar("conclusao_marco", "marco", marco.id)
    return True


def pode_devolver(marco: Marco) -> bool:
    """Há o que devolver? Só quando o marco não está concluído E existe entrega
    da **orientanda** (sinalizada, ou ao menos uma versão dela). O upload do
    próprio orientador NÃO conta — era a precondição vazia que deixava devolver
    um marco que a aluna nunca entregou, disparando e-mail sobre algo inexistente.
    Checado antes de gravar arquivo, para não deixar versão órfã numa recusa."""
    return marco.status != "concluido" and (
        marco.conclusao_sinalizada or marco.tem_entrega_do_orientando
    )


def recado_da_devolucao(marco: Marco) -> tuple[str, str]:
    """Mensagem e categoria de flash quando a devolução é RECUSADA (a rota já
    tratou o sucesso). Diz por que nada foi devolvido — o silêncio é o que
    confunde."""
    if marco.status == "concluido":
        return (
            f'A tarefa "{marco.titulo}" já está concluída e não foi reaberta.',
            "warning",
        )
    return (
        f'A tarefa "{marco.titulo}" ainda não tem entrega da orientanda — não há '
        "o que devolver, e ela não será avisada.",
        "warning",
    )


def devolver_entrega(marco: Marco, nota: str | None = None, versao=None) -> bool:
    """Devolve a entrega ao orientando corrigir — o **ponto único** do ciclo.
    Não faz commit (a transação é do chamador); devolve False, sem efeito,
    quando `not pode_devolver`.

    Faz, num só ato, o que antes estava espalhado por cinco portas:
    - move o estado do marco: zera `conclusao_sinalizada` (a vez volta ao
      orientando), mantém em andamento e carimba `devolvido_em`;
    - grava a nota do ATO (o crux anti-oscilação): `nota_devolucao` recebe
      **sempre** exatamente a nota desta devolução — texto, ou None se vazia.
      Nunca "preserva a anterior"; um novo ato sobrescreve nota e data juntas,
      então nunca se vê nota velha sob data nova. `sinalizar_conclusao` NÃO a
      apaga (ela é o registro da última devolução; a relevância na tela vem de
      `aguardando`, não de mutar o dado);
    - se veio a `versao` (o arquivo corrigido do orientador), carimba-a como
      devolução — a classificação da versão passa a nascer daqui, e não de uma
      escolha à mão no upload."""
    if not pode_devolver(marco):
        return False
    marco.conclusao_sinalizada = False
    marco.status = "em_andamento"
    marco.devolvido_em = agora()
    marco.nota_devolucao = (nota or "").strip() or None
    if versao is not None:
        versao.eh_devolucao = True
    auditoria.registrar(
        "devolucao_revisao_marco", "marco", marco.id, {"com_nota": bool(marco.nota_devolucao)}
    )
    return True
