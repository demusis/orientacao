"""Markdown dos campos longos de ata e parecer, renderizado na tela e no PDF.

O PDF vai à assinatura eletrônica externa e o hash certifica sua correspondência
com o registro interno. Se a tela interpretasse a marcação e o papel imprimisse
os asteriscos crus, o orientando aprovaria uma coisa e assinaria outra. Daí o
desenho: **um parse, dois emissores** — o texto é convertido uma única vez em
árvore sintática, e a mesma árvore alimenta `para_html` e `para_flowables`. Dois
interpretadores independentes divergiriam com o tempo, e a divergência apareceria
justamente no documento assinado.

Segurança por construção, não por sanitização: os emissores percorrem a árvore e
produzem apenas o repertório que conhecem, escapando todo nó de texto. Os tokens
de HTML cru (`block_html`, `inline_html`) nunca são repassados como marcação —
saem como texto literal. Nada que venha do usuário chega à saída sem atravessar
um emissor de vocabulário fechado, de modo que não é preciso `bleach` nem `nh3`.
"""
from xml.sax.saxutils import escape as escapar_xml

import mistune
from markupsafe import Markup
from markupsafe import escape as escapar_html
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

# Largura útil do A4 com as margens de `exportacao._documento_base`
LARGURA_UTIL = 170 * mm
# Acima disto a fonte da tabela cai, para que a última coluna não saia da página
COLUNAS_ANTES_DE_REDUZIR = 6

_analisador = mistune.create_markdown(renderer=None, plugins=["table"])


def analisar(texto: str) -> list:
    """Parse único. Ambos os emissores partem daqui — nunca do texto."""
    return _analisador(texto or "")


# ---------------------------------------------------------------------------
# Emissor de HTML (tela)


def _link_visivel(no: dict) -> str:
    """Âncora que esconde o destino é vetor de fraude em documento que vai a
    assinatura. Link e imagem saem como `texto (url)` nos dois emissores, de modo
    que a tela e o papel mostrem exatamente a mesma coisa e nada fique oculto."""
    url = (no.get("attrs") or {}).get("url", "")
    return f"{_texto_dos_filhos(no)} ({url})" if url else _texto_dos_filhos(no)


def _texto_dos_filhos(no: dict) -> str:
    """Texto de toda a subárvore, e não apenas dos filhos imediatos.

    A versão anterior lia só a chave `raw` dos filhos diretos. Nós de ênfase
    (`strong`, `emphasis`, `codespan`) guardam o texto em `children`, não em
    `raw`, de modo que `[**o edital** aqui](url)` produzia " aqui (url)" — as
    palavras dentro do negrito sumiam do rótulo, na tela e no documento
    assinado, sem erro algum. Daí a recursão."""
    partes = []
    for filho in no.get("children", []):
        if filho.get("children"):
            partes.append(_texto_dos_filhos(filho))
        else:
            partes.append(filho.get("raw", ""))
    return "".join(partes)


def _html_inline(nos: list) -> str:
    partes = []
    for no in nos or []:
        tipo = no["type"]
        if tipo == "text":
            partes.append(str(escapar_html(no["raw"])))
        elif tipo == "strong":
            partes.append(f"<strong>{_html_inline(no['children'])}</strong>")
        elif tipo == "emphasis":
            partes.append(f"<em>{_html_inline(no['children'])}</em>")
        elif tipo == "codespan":
            partes.append(f"<code>{escapar_html(no['raw'])}</code>")
        elif tipo in ("link", "image"):
            partes.append(str(escapar_html(_link_visivel(no))))
        elif tipo in ("softbreak", "linebreak"):
            # Markdown estrito juntaria as linhas num parágrafo só. Aqui a quebra
            # é preservada: quem redige a ata digita em campo de texto e espera
            # que o que vê seja o que sai — e é o que o PDF sempre fez.
            partes.append("<br>")
        elif tipo in ("inline_html", "block_html"):
            partes.append(str(escapar_html(no["raw"])))
        elif no.get("children"):
            partes.append(_html_inline(no["children"]))
        elif no.get("raw"):
            partes.append(str(escapar_html(no["raw"])))
    return "".join(partes)


def _html_tabela(no: dict) -> str:
    linhas = []
    for secao in no["children"]:
        celulas = (
            [secao] if secao["type"] == "table_row" else secao.get("children", [])
        )
        if secao["type"] == "table_head":
            conteudo = "".join(
                f"<th>{_html_inline(c['children'])}</th>" for c in secao["children"]
            )
            linhas.append(f"<thead><tr>{conteudo}</tr></thead>")
        else:
            corpo = "".join(
                "<tr>"
                + "".join(
                    f"<td>{_html_inline(c['children'])}</td>" for c in lin["children"]
                )
                + "</tr>"
                for lin in celulas
            )
            linhas.append(f"<tbody>{corpo}</tbody>")
    return "<table>" + "".join(linhas) + "</table>"


def _html_lista(no: dict) -> str:
    ordenada = (no.get("attrs") or {}).get("ordered", False)
    tag = "ol" if ordenada else "ul"
    itens = []
    for item in no["children"]:
        itens.append(f"<li>{_html_blocos(item.get('children', []))}</li>")
    return f"<{tag}>" + "".join(itens) + f"</{tag}>"


def _html_blocos(nos: list) -> str:
    partes = []
    for no in nos or []:
        tipo = no["type"]
        if tipo == "heading":
            # o conteúdo é exibido dentro de um card que já tem h1/h2
            nivel = min((no.get("attrs") or {}).get("level", 1) + 2, 6)
            partes.append(f"<h{nivel}>{_html_inline(no['children'])}</h{nivel}>")
        elif tipo == "paragraph":
            partes.append(f"<p>{_html_inline(no['children'])}</p>")
        elif tipo == "block_text":  # item de lista compacta
            partes.append(_html_inline(no["children"]))
        elif tipo == "list":
            partes.append(_html_lista(no))
        elif tipo == "block_quote":
            partes.append(f"<blockquote>{_html_blocos(no['children'])}</blockquote>")
        elif tipo == "block_code":
            partes.append(f"<pre><code>{escapar_html(no['raw'])}</code></pre>")
        elif tipo == "thematic_break":
            partes.append("<hr>")
        elif tipo == "table":
            partes.append(_html_tabela(no))
        elif tipo == "block_html":
            partes.append(f"<p>{escapar_html(no['raw'])}</p>")
        elif tipo == "blank_line":
            continue
        elif no.get("children"):
            partes.append(_html_blocos(no["children"]))
    return "".join(partes)


def para_html(texto: str, formato: str = "markdown") -> Markup:
    """Para a tela. `formato` vem do snapshot congelado: documento assinado antes
    da adoção do markdown continua sendo exibido como texto literal."""
    if formato != "markdown":
        return Markup(f"<p>{escapar_html(texto or '')}</p>".replace("\n", "<br>"))
    return Markup(_html_blocos(analisar(texto)))


# ---------------------------------------------------------------------------
# Emissor de flowables (PDF)
#
# O Paragraph do reportlab aceita um subconjunto de marcação própria; o texto do
# usuário precisa de escape XML porque o paraparser interpreta '&' e '<'.


def _pdf_inline(nos: list) -> str:
    partes = []
    for no in nos or []:
        tipo = no["type"]
        if tipo == "text":
            partes.append(escapar_xml(no["raw"]))
        elif tipo == "strong":
            partes.append(f"<b>{_pdf_inline(no['children'])}</b>")
        elif tipo == "emphasis":
            partes.append(f"<i>{_pdf_inline(no['children'])}</i>")
        elif tipo == "codespan":
            partes.append(
                f'<font face="Courier">{escapar_xml(no["raw"])}</font>'
            )
        elif tipo in ("link", "image"):
            partes.append(escapar_xml(_link_visivel(no)))
        elif tipo in ("softbreak", "linebreak"):
            partes.append("<br/>")
        elif tipo in ("inline_html", "block_html"):
            partes.append(escapar_xml(no["raw"]))
        elif no.get("children"):
            partes.append(_pdf_inline(no["children"]))
        elif no.get("raw"):
            partes.append(escapar_xml(no["raw"]))
    return "".join(partes)


def _estilo_derivado(estilos, base: str, nome: str, **ajustes) -> ParagraphStyle:
    return ParagraphStyle(nome, parent=estilos[base], **ajustes)


def _pdf_tabela(no: dict, estilos) -> Table:
    cabecalho, corpo = [], []
    for secao in no["children"]:
        if secao["type"] == "table_head":
            cabecalho = [c for c in secao["children"]]
        else:
            corpo = [lin["children"] for lin in secao["children"]]

    colunas = max(len(cabecalho), max((len(lin) for lin in corpo), default=0), 1)
    # estouro de margem no reportlab é silencioso: a coluna sai da página sem erro
    fonte = 8 if colunas <= COLUNAS_ANTES_DE_REDUZIR else 7
    estilo_celula = _estilo_derivado(
        estilos, "BodyText", f"CelulaMd{fonte}", fontSize=fonte, leading=fonte + 2
    )

    def linha(celulas):
        return [
            Paragraph(_pdf_inline(c["children"]), estilo_celula) for c in celulas
        ] + [""] * (colunas - len(celulas))

    dados = ([linha(cabecalho)] if cabecalho else []) + [linha(lin) for lin in corpo]
    largura = LARGURA_UTIL / colunas
    tabela = Table(dados, colWidths=[largura] * colunas, hAlign="LEFT")
    tabela.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6ebf1")),
                ("FONTSIZE", (0, 0), (-1, -1), fonte),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return tabela


def _pdf_lista(no: dict, estilos, recuo: float) -> list:
    ordenada = (no.get("attrs") or {}).get("ordered", False)
    estilo = _estilo_derivado(
        estilos,
        "BodyText",
        f"ItemMd{int(recuo)}",
        leftIndent=recuo + 6 * mm,
        bulletIndent=recuo + 2 * mm,
        spaceAfter=2,
    )
    saida = []
    for i, item in enumerate(no["children"], start=1):
        marca = f"{i}." if ordenada else "•"
        for filho in item.get("children", []):
            if filho["type"] in ("block_text", "paragraph"):
                saida.append(
                    Paragraph(_pdf_inline(filho["children"]), estilo, bulletText=marca)
                )
                marca = ""  # só o primeiro bloco do item recebe a marca
            elif filho["type"] == "list":
                saida += _pdf_lista(filho, estilos, recuo + 6 * mm)
            else:
                # Qualquer outro bloco dentro do item — citação, código, título,
                # tabela — segue pelo caminho geral. Sem este ramo o conteúdo era
                # DESCARTADO em silêncio, aparecendo na tela e faltando no PDF
                # assinado: exatamente a divergência que este módulo promete
                # impedir. Nenhum tipo de nó pode terminar sem tratamento.
                saida += _pdf_blocos([filho], estilos, recuo + 6 * mm)
    return saida


def _pdf_blocos(nos: list, estilos, recuo: float = 0) -> list:
    saida = []
    for no in nos or []:
        tipo = no["type"]
        if tipo == "heading":
            nivel = min((no.get("attrs") or {}).get("level", 1) + 1, 4)
            estilo = estilos[f"Heading{nivel}"]
            if recuo:
                estilo = _estilo_derivado(
                    estilos, f"Heading{nivel}", f"H{nivel}Md{int(recuo)}",
                    leftIndent=recuo,
                )
            saida.append(Paragraph(_pdf_inline(no["children"]), estilo))
        elif tipo == "paragraph":
            estilo = (
                _estilo_derivado(estilos, "BodyText", f"PMd{int(recuo)}", leftIndent=recuo)
                if recuo
                else estilos["BodyText"]
            )
            saida.append(Paragraph(_pdf_inline(no["children"]), estilo))
        elif tipo == "block_text":
            saida.append(Paragraph(_pdf_inline(no["children"]), estilos["BodyText"]))
        elif tipo == "list":
            saida += _pdf_lista(no, estilos, recuo)
        elif tipo == "block_quote":
            saida += _pdf_blocos(no["children"], estilos, recuo + 8 * mm)
        elif tipo == "block_code":
            saida.append(
                Paragraph(
                    f'<font face="Courier">'
                    f'{escapar_xml(no["raw"]).replace(chr(10), "<br/>")}</font>',
                    _estilo_derivado(
                        estilos, "BodyText", "CodigoMd", leftIndent=recuo + 4 * mm
                    ),
                )
            )
        elif tipo == "thematic_break":
            saida += [Spacer(1, 2 * mm), HRFlowable(width="100%", color=colors.grey)]
        elif tipo == "table":
            saida += [Spacer(1, 2 * mm), _pdf_tabela(no, estilos), Spacer(1, 2 * mm)]
        elif tipo == "block_html":
            saida.append(Paragraph(escapar_xml(no["raw"]), estilos["BodyText"]))
        elif tipo == "blank_line":
            continue
        elif no.get("children"):
            saida += _pdf_blocos(no["children"], estilos, recuo)
    return saida


def para_flowables(texto: str, estilos, formato: str = "markdown") -> list:
    """Para o PDF. `formato` vem do snapshot: documento congelado antes da adoção
    do markdown continua sendo impresso como texto literal, preservando a
    aparência do que já foi assinado."""
    if formato != "markdown":
        literal = escapar_xml(texto or "").replace("\n", "<br/>")
        return [Paragraph(literal, estilos["BodyText"])]
    blocos = _pdf_blocos(analisar(texto), estilos)
    return blocos or [Paragraph("", estilos["BodyText"])]
