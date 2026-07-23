"""Exportação assinável: PDF de atas finalizadas e pareceres, com identificador
e hash de integridade verificável por rota pública. O PDF destina-se à
assinatura eletrônica externa (gov.br/SEI); o hash permite conferir que o
documento impresso corresponde ao registro interno.

O conteúdo impresso é congelado (JSON canônico em `conteudo_congelado`) na
finalização da ata e na emissão do parecer: PDF e hash derivam desse snapshot,
de modo que alterações externas posteriores (mudança de título do projeto,
correção de nome) não invalidam documentos já assinados. A enumeração dos
campos existe em um único ponto (dados_ata/dados_parecer)."""
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
from app.services import marcacao

# Formato dos campos longos gravado no snapshot dos documentos novos. Registro
# anterior à adoção do markdown não traz a chave e é lido como "texto".
FORMATO_CORRENTE = "markdown"


def _texto(valor: str) -> str:
    """Texto de usuário para Paragraph: escape XML (o paraparser do reportlab
    interpreta '&'/'<' como marcação) e quebras de linha preservadas. Células
    planas de Table não passam por paraparser e recebem o texto sem escape.

    Vale para os campos curtos; os longos passam por `marcacao.para_flowables`."""
    return escape(valor or "").replace("\n", "<br/>")


def _canonico(obj) -> str:
    """Serialização canônica por JSON: delimitação inequívoca de campos
    (imune a caracteres de controle no conteúdo) e estrutura aninhada estável."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _sha256(obj) -> str:
    return hashlib.sha256(_canonico(obj).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Enumeração única dos campos impressos


def dados_ata(ata: Ata) -> dict:
    """Todo o conteúdo impresso no PDF da ata, em estrutura serializável."""
    return {
        "registro": "ata",
        "id": ata.id,
        # Formato dos campos longos, congelado junto do conteúdo: um documento
        # assinado declara como deve ser lido, de modo que mudança futura no
        # repertório de marcação não altere a aparência do que já foi assinado.
        "formato": FORMATO_CORRENTE,
        "tipo": ata.tipo,
        "data_reuniao": str(ata.data_reuniao),
        "hora_reuniao": ata.hora_reuniao.strftime("%H:%M") if ata.hora_reuniao else "",
        "orientador": ata.orientador.nome,
        "redator": ata.redator.nome,
        "pauta": ata.pauta,
        "deliberacoes": ata.deliberacoes,
        "finalizada_em": (
            ata.finalizada_em.strftime("%Y-%m-%d %H:%M") if ata.finalizada_em else ""
        ),
        "participacoes": [
            {
                "orientacao_id": p.orientacao_id,
                "orientando": p.orientacao.orientando.nome,
                "projeto": p.orientacao.titulo_projeto,
                "presenca": p.presenca,
            }
            for p in sorted(ata.participacoes, key=lambda x: x.orientacao_id)
        ],
        "reagendamentos": [
            {
                "de": str(r.data_anterior),
                "para": str(r.data_nova),
                "motivo": r.motivo or "",
                "registrado_em": r.registrado_em.strftime("%Y-%m-%d %H:%M"),
            }
            for r in ata.reagendamentos
        ],
    }


def dados_parecer(parecer: Parecer) -> dict:
    versao = parecer.versao_documento
    return {
        "registro": "parecer",
        "id": parecer.id,
        "formato": FORMATO_CORRENTE,
        "tipo": parecer.tipo,
        "resultado": parecer.resultado,
        "orientacao_id": parecer.orientacao_id,
        "projeto": parecer.orientacao.titulo_projeto,
        "orientando": parecer.orientacao.orientando.nome,
        "documento_avaliado": (
            f"{versao.documento.titulo} (v{versao.numero_versao})" if versao else ""
        ),
        "emissor": parecer.emissor.nome,
        "emitido_em": parecer.emitido_em.strftime("%Y-%m-%d %H:%M"),
        "conteudo": parecer.conteudo,
    }


# ---------------------------------------------------------------------------
# Congelamento e hash


def congelar_ata(ata: Ata) -> None:
    """Chamado na finalização: fixa o conteúdo que o PDF e o hash usarão."""
    ata.conteudo_congelado = _canonico(dados_ata(ata))


def congelar_parecer(parecer: Parecer) -> None:
    """Chamado na emissão (o parecer é imutável desde a criação)."""
    parecer.conteudo_congelado = _canonico(dados_parecer(parecer))


def _dados_vigentes_ata(ata: Ata) -> dict:
    if ata.conteudo_congelado:
        return json.loads(ata.conteudo_congelado)
    return dados_ata(ata)


def _dados_vigentes_parecer(parecer: Parecer) -> dict:
    if parecer.conteudo_congelado:
        return json.loads(parecer.conteudo_congelado)
    return dados_parecer(parecer)


def hash_ata(ata: Ata) -> str:
    """Hash do conteúdo congelado: cobre tudo o que o PDF imprime e permanece
    estável a alterações externas posteriores à finalização."""
    if ata.conteudo_congelado:
        return hashlib.sha256(ata.conteudo_congelado.encode("utf-8")).hexdigest()
    return _sha256(dados_ata(ata))


def hash_parecer(parecer: Parecer) -> str:
    if parecer.conteudo_congelado:
        return hashlib.sha256(parecer.conteudo_congelado.encode("utf-8")).hexdigest()
    return _sha256(dados_parecer(parecer))


# ---------------------------------------------------------------------------
# Geração dos PDFs (renderiza o snapshot; escape apenas dentro de Paragraph)


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
    doc, estilos = _documento_base(buffer, f"ARIADNE · Ata {ata.id}")
    d = _dados_vigentes_ata(ata)
    h = hash_ata(ata)

    fluxo = [
        Paragraph("ARIADNE · Ata de reunião de orientação", estilos["Title"]),
        _tabela(
            [
                ["Identificador", f"ata-{d['id']}"],
                ["Tipo de reunião", d["tipo"]],
                [
                    "Data e hora",
                    d["data_reuniao"]
                    + (f" às {d['hora_reuniao']}" if d["hora_reuniao"] else ""),
                ],
                ["Orientador responsável", d["orientador"]],
                ["Redigida por", d["redator"]],
                ["Finalizada em (UTC)", d["finalizada_em"] or "—"],
            ],
            larguras=[45 * mm, 115 * mm],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Participantes e presenças", estilos["Heading2"]),
        _tabela(
            [["Orientando", "Projeto", "Presença"]]
            + [
                [
                    p["orientando"],
                    Paragraph(_texto(p["projeto"]), estilos["BodyText"]),
                    p["presenca"],
                ]
                for p in d["participacoes"]
            ],
            larguras=[50 * mm, 80 * mm, 30 * mm],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Pauta", estilos["Heading2"]),
        *marcacao.para_flowables(d["pauta"], estilos, d.get("formato", "texto")),
        Spacer(1, 3 * mm),
        Paragraph("Deliberações", estilos["Heading2"]),
        *marcacao.para_flowables(
            d["deliberacoes"], estilos, d.get("formato", "texto")
        ),
    ]
    if d["reagendamentos"]:
        fluxo += [
            Spacer(1, 5 * mm),
            Paragraph("Histórico de reagendamentos", estilos["Heading2"]),
            _tabela(
                [["De", "Para", "Motivo", "Registrado em (UTC)"]]
                + [
                    [
                        r["de"],
                        r["para"],
                        Paragraph(_texto(r["motivo"] or "—"), estilos["BodyText"]),
                        r["registrado_em"],
                    ]
                    for r in d["reagendamentos"]
                ],
                larguras=[25 * mm, 25 * mm, 75 * mm, 35 * mm],
            ),
        ]
    fluxo += _rodape_verificacao(estilos, "ata", d["id"], h, url_verificacao)
    doc.build(fluxo)
    return buffer.getvalue()


def gerar_pdf_parecer(parecer: Parecer, url_verificacao: str) -> bytes:
    buffer = BytesIO()
    doc, estilos = _documento_base(buffer, f"ARIADNE · Parecer {parecer.id}")
    d = _dados_vigentes_parecer(parecer)
    h = hash_parecer(parecer)

    fluxo = [
        Paragraph("ARIADNE · Parecer técnico", estilos["Title"]),
        _tabela(
            [
                ["Identificador", f"parecer-{d['id']}"],
                ["Tipo", d["tipo"]],
                ["Resultado", RESULTADO_LABEL[d["resultado"]]],
                ["Projeto", Paragraph(_texto(d["projeto"]), estilos["BodyText"])],
                ["Orientando", d["orientando"]],
                [
                    "Documento avaliado",
                    Paragraph(
                        _texto(d["documento_avaliado"] or "—"), estilos["BodyText"]
                    ),
                ],
                ["Emitido por", d["emissor"]],
                ["Emitido em (UTC)", d["emitido_em"]],
            ],
            larguras=[45 * mm, 115 * mm],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Parecer", estilos["Heading2"]),
        *marcacao.para_flowables(d["conteudo"], estilos, d.get("formato", "texto")),
    ]
    fluxo += _rodape_verificacao(estilos, "parecer", d["id"], h, url_verificacao)
    doc.build(fluxo)
    return buffer.getvalue()
