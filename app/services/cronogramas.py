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


def recado_da_devolucao(
    marco: Marco | None, devolvida: bool, com_versao: bool = True
) -> tuple[str, str]:
    """Mensagem e categoria de flash do desfecho de uma devolução — dita num
    ponto só, porque as quatro rotas que devolvem a exibem.

    Declarar devolução e nada acontecer é o silêncio que confunde: o rótulo da
    opção promete que a tarefa volta ao orientando. `com_versao` distingue o
    upload (gravou um arquivo) do botão da tarefa (não gravou nada)."""
    if devolvida:
        return (
            "Marcada como devolução: a tarefa voltou para revisão do orientando."
            if com_versao
            else "Entrega devolvida para revisão do orientando.",
            "info",
        )
    inicio = "A versão foi gravada como devolução, mas a" if com_versao else "A"
    if marco is None:
        return (
            "A versão foi gravada como devolução, mas o documento não está "
            "ligado a tarefa alguma — nada foi devolvido ao orientando, e ele "
            "não será avisado. Ligue o documento a um marco para devolver.",
            "warning",
        )
    if marco.status == "concluido":
        return (
            f'{inicio} tarefa "{marco.titulo}" já está concluída e não foi '
            "reaberta.",
            "warning",
        )
    return (
        f'{inicio} tarefa "{marco.titulo}" não tem entrega alguma — nada foi '
        "devolvido ao orientando, e ele não será avisado.",
        "warning",
    )


def devolver_para_revisao(marco: Marco, nota: str | None = None) -> bool:
    """Devolve a entrega ao orientando corrigir — a volta que faltava ao ciclo.
    Espelha `confirmar_conclusao`: **não faz commit** (a transação é do
    chamador) e devolve False, sem efeito, quando não há o que devolver.

    Zera `conclusao_sinalizada` (a vez volta ao orientando), mantém o marco em
    andamento e carimba `devolvido_em`/`nota_devolucao` — que distinguem
    "devolvido, aguardando o aluno" de "nunca iniciado" e dizem o que corrigir.

    **Precisa haver o que devolver**: entrega sinalizada, ou ao menos um arquivo
    entregue. Devolver marco vazio anunciaria ao orientando, por e-mail, a
    devolução de algo que ele nunca entregou; exigir a sinalização, porém,
    trancava o caso comum de quem envia o arquivo e esquece de sinalizar — e a
    tela não oferece outro caminho. A guarda mora aqui porque quatro rotas
    chamam esta função.

    Sobre a nota: texto substitui; vazio ou `None` deixa como está. Quem a
    apaga é o **reenvio do orientando** (`sinalizar_conclusao`), que fecha o
    ciclo: assim a nota nunca descreve um ciclo anterior já resolvido, sem que
    cada chamador precise adivinhar quando limpar.

    **Não mexe em versão alguma.** Classificar a versão é ato do documento
    (`natureza`), declarado no upload ou no seletor; aqui só se move o estado do
    marco. Enquanto esta função marcava `eh_devolucao`, carimbava a versão
    corrente de *todos* os documentos do marco — a ata da reunião virava
    "devolução"."""
    if marco.status == "concluido":
        return False
    if not marco.conclusao_sinalizada and not any(
        v is not None for _, v in marco.entregas
    ):
        return False
    marco.conclusao_sinalizada = False
    marco.status = "em_andamento"
    marco.devolvido_em = agora()
    if (nota or "").strip():
        marco.nota_devolucao = nota.strip()
    auditoria.registrar(
        "devolucao_revisao_marco", "marco", marco.id, {"com_nota": bool(marco.nota_devolucao)}
    )
    return True
