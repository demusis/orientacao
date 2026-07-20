"""Exportação assinável: PDF de atas finalizadas e pareceres, com identificador
e hash de integridade verificável por rota pública. O PDF destina-se à
assinatura eletrônica externa (gov.br/SEI); o hash permite conferir que o
documento impresso corresponde ao registro interno."""
import hashlib
import json
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import Ata, Parecer
from app.models.ata import RESULTADO_LABEL

def _texto(valor: str) -> "str":
    """Texto de usuário para Paragraph: escape XML (o paraparser do reportlab
    interpreta '&'/'<' como marcação) e quebras de linha preservadas."""
    return escape(valor or "").replace("\n", "<br/>")


def _sha256(partes) -> str:
    """Serialização canônica por JSON: delimitação inequívoca de campos
    (imune a caracteres de controle no conteúdo) e estrutura aninhada estável."""
    canonico = json.dumps(partes, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def hash_ata(ata: Ata) -> str:
    """Cobre TODO o conteúdo impresso no PDF: qualquer diferença visual entre
    dois PDFs do mesmo registro implica hashes distintos."""
    partes = [
        "ata",
        str(ata.id),
        ata.tipo,
        str(ata.data_reuniao),
        str(ata.hora_reuniao or ""),
        ata.orientador.nome,
        ata.redator.nome,
        ata.pauta,
        ata.deliberacoes,
        str(ata.finalizada_em or ""),
        [
            [
                str(p.orientacao_id),
                p.orientacao.orientando.nome,
                p.orientacao.titulo_projeto,
                p.presenca,
            ]
            for p in sorted(ata.participacoes, key=lambda x: x.orientacao_id)
        ],
        [
            [str(r.data_anterior), str(r.data_nova), r.motivo or "", str(r.registrado_em)]
            for r in ata.reagendamentos
        ],
    ]
    return _sha256(partes)


def hash_parecer(parecer: Parecer) -> str:
    versao = parecer.versao_documento
    return _sha256(
        [
            "parecer",
            str(parecer.id),
            parecer.tipo,
            parecer.resultado,
            parecer.conteudo,
            str(parecer.emitido_em),
            str(parecer.orientacao_id),
            parecer.orientacao.titulo_projeto,
            parecer.orientacao.orientando.nome,
            parecer.emissor.nome,
            f"{versao.documento.titulo}|v{versao.numero_versao}" if versao else "",
        ]
    )


def _documento_base(buffer: BytesIO, titulo: str):
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=titulo,
    )
    estilos = getSampleStyleSheet()
    estilos.add(
        ParagraphStyle(
            "Rodape", parent=estilos["Normal"], fontSize=7, textColor=colors.grey
        )
    )
    return doc, estilos


def _tabela(dados, larguras=None):
    t = Table(dados, colWidths=larguras, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6ebf1")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def _rodape_verificacao(estilos, tipo: str, reg_id: int, hash_hex: str, url_verificacao: str):
    return [
        Spacer(1, 8 * mm),
        Paragraph(
            f"Documento gerado pelo ARIADNE. Identificador: {tipo}-{reg_id}. "
            f"Hash de integridade (SHA-256): {hash_hex}",
            estilos["Rodape"],
        ),
        Paragraph(
            f"Verificação de correspondência com o registro interno: {url_verificacao}",
            estilos["Rodape"],
        ),
        Paragraph(
            "Este documento destina-se à assinatura eletrônica externa; a "
            "integridade do conteúdo é conferível pelo hash acima.",
            estilos["Rodape"],
        ),
    ]


def gerar_pdf_ata(ata: Ata, url_verificacao: str) -> bytes:
    buffer = BytesIO()
    doc, estilos = _documento_base(buffer, f"ARIADNE — Ata {ata.id}")
    h = hash_ata(ata)

    fluxo = [
        Paragraph("ARIADNE — Ata de reunião de orientação", estilos["Title"]),
        _tabela(
            [
                ["Identificador", f"ata-{ata.id}"],
                ["Tipo de reunião", ata.tipo],
                [
                    "Data e hora",
                    f"{ata.data_reuniao}"
                    + (
                        f" às {ata.hora_reuniao.strftime('%H:%M')}"
                        if ata.hora_reuniao
                        else ""
                    ),
                ],
                ["Orientador responsável", _texto(ata.orientador.nome)],
                ["Redigida por", _texto(ata.redator.nome)],
                [
                    "Finalizada em (UTC)",
                    ata.finalizada_em.strftime("%Y-%m-%d %H:%M") if ata.finalizada_em else "—",
                ],
            ],
            larguras=[45 * mm, 115 * mm],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Participantes e presenças", estilos["Heading2"]),
        _tabela(
            [["Orientando", "Projeto", "Presença"]]
            + [
                [
                    _texto(p.orientacao.orientando.nome),
                    Paragraph(_texto(p.orientacao.titulo_projeto), estilos["BodyText"]),
                    p.presenca,
                ]
                for p in sorted(ata.participacoes, key=lambda x: x.orientacao_id)
            ],
            larguras=[50 * mm, 80 * mm, 30 * mm],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Pauta", estilos["Heading2"]),
        Paragraph(_texto(ata.pauta), estilos["BodyText"]),
        Spacer(1, 3 * mm),
        Paragraph("Deliberações", estilos["Heading2"]),
        Paragraph(_texto(ata.deliberacoes), estilos["BodyText"]),
    ]
    if ata.reagendamentos:
        fluxo += [
            Spacer(1, 5 * mm),
            Paragraph("Histórico de reagendamentos", estilos["Heading2"]),
            _tabela(
                [["De", "Para", "Motivo", "Registrado em (UTC)"]]
                + [
                    [
                        str(r.data_anterior),
                        str(r.data_nova),
                        Paragraph(_texto(r.motivo or "—"), estilos["BodyText"]),
                        r.registrado_em.strftime("%Y-%m-%d %H:%M"),
                    ]
                    for r in ata.reagendamentos
                ],
                larguras=[25 * mm, 25 * mm, 75 * mm, 35 * mm],
            ),
        ]
    fluxo += _rodape_verificacao(estilos, "ata", ata.id, h, url_verificacao)
    doc.build(fluxo)
    return buffer.getvalue()


def gerar_pdf_parecer(parecer: Parecer, url_verificacao: str) -> bytes:
    buffer = BytesIO()
    doc, estilos = _documento_base(buffer, f"ARIADNE — Parecer {parecer.id}")
    h = hash_parecer(parecer)

    versao = parecer.versao_documento
    fluxo = [
        Paragraph("ARIADNE — Parecer técnico", estilos["Title"]),
        _tabela(
            [
                ["Identificador", f"parecer-{parecer.id}"],
                ["Tipo", parecer.tipo],
                ["Resultado", RESULTADO_LABEL[parecer.resultado]],
                ["Projeto", _texto(parecer.orientacao.titulo_projeto)],
                ["Orientando", _texto(parecer.orientacao.orientando.nome)],
                [
                    "Documento avaliado",
                    _texto(f"{versao.documento.titulo} (v{versao.numero_versao})") if versao else "—",
                ],
                ["Emitido por", _texto(parecer.emissor.nome)],
                ["Emitido em (UTC)", parecer.emitido_em.strftime("%Y-%m-%d %H:%M")],
            ],
            larguras=[45 * mm, 115 * mm],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Parecer", estilos["Heading2"]),
        Paragraph(_texto(parecer.conteudo), estilos["BodyText"]),
    ]
    fluxo += _rodape_verificacao(estilos, "parecer", parecer.id, h, url_verificacao)
    doc.build(fluxo)
    return buffer.getvalue()
