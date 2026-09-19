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


def devolver_para_revisao(marco: Marco, nota: str | None = None) -> bool:
    """Devolve a entrega ao orientando corrigir — a volta que faltava ao ciclo.
    Espelha `confirmar_conclusao`: **não faz commit** (a transação é do
    chamador) e devolve False, sem efeito, quando não há o que devolver.

    Zera `conclusao_sinalizada` (a vez volta ao orientando), mantém o marco em
    andamento e carimba `devolvido_em`/`nota_devolucao` — que distinguem
    "devolvido, aguardando o aluno" de "nunca iniciado" e dizem o que corrigir.

    Só age sobre entrega **sinalizada**: devolver o que o orientando ainda nem
    declarou concluído anunciaria a ele, por e-mail, a devolução de algo que não
    entregou. A guarda mora aqui, e não só no botão, porque três rotas chamam
    esta função (o botão e os dois caminhos de upload).

    `nota=None` **preserva** a nota anterior: o upload de uma versão-devolução
    não pode apagar as correções que o orientador já escreveu no marco."""
    if marco.status == "concluido" or not marco.conclusao_sinalizada:
        return False
    marco.conclusao_sinalizada = False
    marco.status = "em_andamento"
    marco.devolvido_em = agora()
    if nota is not None:
        marco.nota_devolucao = nota.strip() or None
    # O registro do orientador vira a devolução, saindo de "aguardando parecer".
    # A entrega da orientanda NÃO é tocada — nem a que ela enviou, nem a que o
    # orientador registrou em nome dela: essa espera parecer, não é devolução.
    for doc in marco.documentos:
        v = doc.versao_atual
        if (
            v is not None
            and v.enviado_por != marco.orientacao.orientando_id
            and not v.em_nome_do_orientando
        ):
            v.eh_devolucao = True
    auditoria.registrar(
        "devolucao_revisao_marco", "marco", marco.id, {"com_nota": bool(marco.nota_devolucao)}
    )
    return True
