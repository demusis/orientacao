"""Relatório consolidado de um vínculo de orientação, em PDF.

Reúne num só documento o que hoje só existe em PDFs isolados de ata e parecer:
cronograma, reuniões, pareceres e entregas. Serve à banca, à coordenação e ao
relatório institucional.

**Não leva hash de verificação, deliberadamente.** Ata e parecer são atos:
congelados na finalização/emissão e conferíveis por rota pública. Este relatório
é um *retrato de momento*, que muda a cada geração conforme o vínculo evolui.
Dar-lhe hash sugeriria uma imutabilidade que ele não tem e enfraqueceria o
significado do hash onde ele de fato vale. Leva, em vez disso, a data e a hora
de geração — que é o que um retrato honesto declara.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.platypus import Paragraph, Spacer

from app.models import Ata, Parecer
from app.models.ata import RESULTADO_LABEL
from app.models.cronograma import ETAPA_MARCO_LABEL, TIPO_MARCO_LABEL
from app.models.orientacao import MODALIDADE_LABEL
from app.services import linha_tempo, marcacao
from app.services.exportacao import _documento_base, _tabela, _texto
from app.services.tempo import agora

STATUS_MARCO_LABEL = {
    "pendente": "Pendente",
    "em_andamento": "Em andamento",
    "concluido": "Concluído",
}
PRESENCA_LABEL = {"pendente": "—", "presente": "Presente", "ausente": "Ausente"}


def _secao(estilos, titulo: str) -> list:
    return [Spacer(1, 5), Paragraph(titulo, estilos["Heading2"])]


def _linha_do_tempo(orientacao, estilos) -> list:
    """Seção inicial: a cronologia do vínculo. A banca lê a história antes do
    detalhe por tipo que vem nas seções seguintes."""
    eventos = linha_tempo.eventos(orientacao)
    if not eventos:
        return []
    linhas = [["Data", "Evento", "Descrição"]]
    for e in eventos:
        desc = e["titulo"]
        if e.get("detalhe"):
            desc += f" — {e['detalhe']}"
        if e.get("relacionado"):
            desc += f" · {e['relacionado']}"
        linhas.append([
            e["data"].strftime("%d/%m/%Y"),
            linha_tempo.TIPOS[e["tipo"]],
            Paragraph(_texto(desc), estilos["BodyText"]),
        ])
    return _secao(estilos, "Linha do tempo") + [_tabela(linhas)]


def _cronograma(orientacao, estilos) -> list:
    marcos = orientacao.marcos.all()
    if not marcos:
        return _secao(estilos, "Cronograma") + [
            Paragraph("Nenhum marco cadastrado.", estilos["BodyText"])
        ]
    linhas = [["Etapa / Tipo", "Marco", "Prazo", "Situação"]]
    for m in marcos:
        situacao = STATUS_MARCO_LABEL[m.status]
        if m.atrasado:
            situacao += " (atrasado)"
        linhas.append([
            Paragraph(
                f"{ETAPA_MARCO_LABEL.get(m.etapa, '—')}<br/>"
                f"<font size=7 color='#5a6570'>{TIPO_MARCO_LABEL.get(m.tipo, '')}</font>",
                estilos["BodyText"],
            ),
            Paragraph(_texto(m.titulo), estilos["BodyText"]),
            m.data_prevista.strftime("%d/%m/%Y"),
            situacao,
        ])
    return _secao(estilos, "Cronograma") + [_tabela(linhas)]


def _reunioes(orientacao, estilos) -> list:
    atas = orientacao.atas.order_by(Ata.data_reuniao.desc()).all()
    if not atas:
        return _secao(estilos, "Reuniões") + [
            Paragraph("Nenhuma reunião registrada.", estilos["BodyText"])
        ]
    linhas = [["Data", "Situação", "Presença do orientando"]]
    for a in atas:
        # o orientando deste vínculo, dentre os participantes da ata
        part = next(
            (p for p in a.participacoes if p.orientacao_id == orientacao.id), None
        )
        presenca = PRESENCA_LABEL[part.presenca] if part else "—"
        situacao = "Finalizada" if a.status == "finalizada" else "Rascunho"
        linhas.append([
            a.data_reuniao.strftime("%d/%m/%Y")
            + (f" {a.hora_reuniao.strftime('%H:%M')}" if a.hora_reuniao else ""),
            situacao,
            presenca,
        ])
    return _secao(estilos, "Reuniões") + [_tabela(linhas)]


def _pareceres(orientacao, estilos) -> list:
    pareceres = orientacao.pareceres.order_by(Parecer.emitido_em.desc()).all()
    if not pareceres:
        return _secao(estilos, "Pareceres") + [
            Paragraph("Nenhum parecer emitido.", estilos["BodyText"])
        ]
    blocos = _secao(estilos, "Pareceres")
    for p in pareceres:
        alvo = ""
        if p.versao_documento:
            alvo = (f" · {p.versao_documento.documento.titulo} "
                    f"(v{p.versao_documento.numero_versao})")
        blocos.append(Paragraph(
            f"<b>{p.tipo.capitalize()}</b> — {RESULTADO_LABEL[p.resultado]}"
            f"{_texto(alvo)}<br/>"
            f"<font size=7 color='#5a6570'>Emitido por {_texto(p.emissor.nome)} "
            f"em {p.emitido_em.strftime('%d/%m/%Y')}</font>",
            estilos["BodyText"],
        ))
        blocos += marcacao.para_flowables(
            p.conteudo, estilos, p.formato_conteudo
        )
        blocos.append(Spacer(1, 4))
    return blocos


def _entregas(orientacao, estilos) -> list:
    docs = orientacao.documentos.all()
    if not docs:
        return _secao(estilos, "Documentos entregues") + [
            Paragraph("Nenhum documento enviado.", estilos["BodyText"])
        ]
    linhas = [["Documento", "Versões", "Última versão"]]
    for d in docs:
        versoes = d.versoes.all() if hasattr(d.versoes, "all") else list(d.versoes)
        ultima = max(versoes, key=lambda v: v.numero_versao) if versoes else None
        linhas.append([
            Paragraph(_texto(d.titulo), estilos["BodyText"]),
            str(len(versoes)),
            (f"v{ultima.numero_versao} — "
             f"{ultima.enviado_em.strftime('%d/%m/%Y')}") if ultima else "—",
        ])
    return _secao(estilos, "Documentos entregues") + [_tabela(linhas)]


def gerar_pdf_relatorio(orientacao) -> bytes:
    buffer = BytesIO()
    doc, estilos = _documento_base(
        buffer, f"ARIADNE — Relatório do vínculo {orientacao.id}"
    )
    coorientadores = ", ".join(u.nome for u in orientacao.coorientadores) or "—"

    fluxo = [
        Paragraph("ARIADNE — Relatório de acompanhamento", estilos["Title"]),
        _tabela([
            ["Projeto", Paragraph(_texto(orientacao.titulo_projeto), estilos["BodyText"])],
            ["Modalidade", MODALIDADE_LABEL.get(orientacao.modalidade, orientacao.modalidade)],
            ["Orientando", orientacao.orientando.nome],
            ["Orientador", orientacao.orientador.nome],
            ["Coorientadores", Paragraph(_texto(coorientadores), estilos["BodyText"])],
            ["Início", orientacao.data_inicio.strftime("%d/%m/%Y")],
            ["Fim previsto",
             orientacao.data_fim_prevista.strftime("%d/%m/%Y")
             if orientacao.data_fim_prevista else "—"],
            ["Situação", orientacao.status.capitalize()],
        ]),
    ]
    fluxo += _linha_do_tempo(orientacao, estilos)
    fluxo += _cronograma(orientacao, estilos)
    fluxo += _reunioes(orientacao, estilos)
    fluxo += _entregas(orientacao, estilos)
    fluxo += _pareceres(orientacao, estilos)
    fluxo += [
        Spacer(1, 8),
        Paragraph(
            "Retrato de momento gerado pelo ARIADNE em "
            f"{agora().strftime('%d/%m/%Y às %H:%M')} (UTC). Diferentemente de "
            "atas e pareceres, este relatório não é um ato imutável e não carrega "
            "hash de verificação: reflete o estado do vínculo na data acima.",
            estilos["Rodape"],
        ),
    ]
    doc.build(fluxo)
    return buffer.getvalue()
