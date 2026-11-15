"""Extrato estruturado do orientando (relatório consolidado do vínculo em PDF).

Reúne num só documento o retrato completo do acompanhamento: ficha cadastral
e resumo executivo, cronograma e situação das tarefas, histórico completo de
versões de documentos e pareceres, pareceres integrais, quadro de reuniões e
presenças, eventos formais do vínculo e linha do tempo cronológica.

**Não leva hash de verificação, deliberadamente.** Ata e parecer são atos:
congelados na finalização/emissão e conferíveis por rota pública. Este extrato
é um *retrato de momento*, que muda a cada geração conforme o vínculo evolui.
Dar-lhe hash sugeriria uma imutabilidade que ele não tem e enfraqueceria o
significado do hash onde ele de fato vale. Leva, em vez disso, a data e a hora
de geração — que é o que um retrato honesto declara.
"""
from io import BytesIO

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from app.models import Ata, Documento, Parecer
from app.models.ata import RESULTADO_LABEL
from app.models.cronograma import (
    ENTREGA_ESPERADA_LABEL,
    ETAPA_MARCO_LABEL,
    TIPO_MARCO_LABEL,
)
from app.models.orientacao import MODALIDADE_LABEL, TIPO_EVENTO_LABEL
from app.services import linha_tempo, marcacao, painel
from app.services.exportacao import _documento_base, _tabela, _texto
from app.services.tempo import agora

STATUS_MARCO_LABEL = {
    "pendente": "Pendente",
    "em_andamento": "Em andamento",
    "concluido": "Concluído",
}
PRESENCA_LABEL = {"pendente": "Pendente", "presente": "Presente", "ausente": "Ausente"}
NATUREZA_LABEL = {
    "devolucao": "devolução",
    "entrega": "entrega da orientanda",
    "registro": "registro",
}


def _secao(estilos, titulo: str) -> list:
    return [Spacer(1, 5 * mm), Paragraph(titulo, estilos["Heading2"])]


def _estilo_celula(estilos) -> ParagraphStyle:
    if "CelulaExtrato" not in estilos:
        estilos.add(
            ParagraphStyle(
                "CelulaExtrato",
                parent=estilos["BodyText"],
                fontSize=8,
                leading=10,
                spaceBefore=0,
                spaceAfter=0,
            )
        )
    return estilos["CelulaExtrato"]


def _situacao_reuniao(ata: Ata) -> str:
    if ata.status == "finalizada":
        return "Finalizada"
    if ata.status == "cancelada":
        return "Cancelada"
    if ata.agendada:
        return "Agendada"
    return "Rascunho"


def _cabecalho_e_resumo(
    orientacao, marcos, docs, versoes_por_doc, pareceres, atas, estilos, cel
) -> list:
    coorientadores = ", ".join(u.nome for u in orientacao.coorientadores) or "nenhum"
    orientando = orientacao.orientando
    contato = f"{orientando.nome} ({orientando.email})"
    if orientando.telefone:
        contato += f" · Tel.: {orientando.telefone}"

    fim_txt = (
        orientacao.data_fim_prevista.strftime("%d/%m/%Y")
        if orientacao.data_fim_prevista
        else "não definido"
    )
    rel = painel.relogio(orientacao)
    relogio_txt = f"{rel['rotulo']} (risco {rel['risco']})"
    if rel["dias_restantes"] is not None:
        if rel["dias_restantes"] >= 0:
            relogio_txt += f" · {rel['dias_restantes']} dia(s) restante(s)"
        else:
            relogio_txt += f" · vencido há {-rel['dias_restantes']} dia(s)"
    if rel["marco_critico_vencido"]:
        relogio_txt += " · marco crítico vencido"

    modalidade = MODALIDADE_LABEL.get(orientacao.modalidade, orientacao.modalidade)

    total_m = len(marcos)
    concluidos_m = sum(1 for m in marcos if m.status == "concluido")
    em_aberto_m = total_m - concluidos_m
    atrasados_m = sum(1 for m in marcos if m.atrasado)
    resumo_marcos = (
        f"{total_m} total ({concluidos_m} concluído(s), "
        f"{em_aberto_m} em aberto, {atrasados_m} atrasado(s))"
    )

    total_versoes = sum(len(versoes_por_doc[d.id]) for d in docs)
    resumo_docs = f"{len(docs)} documento(s), {total_versoes} versão(ões)"
    resumo_pareceres = f"{len(pareceres)} emitido(s)"

    presentes = ausencias = 0
    for a in atas:
        part = a.participacao_de(orientacao.id)
        if part is not None:
            if part.presenca == "presente":
                presentes += 1
            elif part.presenca == "ausente":
                ausencias += 1
    resumo_reunioes = (
        f"{len(atas)} registrada(s) ({presentes} presença(s), {ausencias} ausência(s))"
    )

    return [
        Paragraph("ARIADNE · Extrato de acompanhamento do orientando", estilos["Title"]),
        _tabela(
            [
                ["Orientando", Paragraph(_texto(contato), cel)],
                ["Projeto", Paragraph(_texto(orientacao.titulo_projeto), cel)],
                ["Modalidade / Situação", f"{modalidade} · {orientacao.status.capitalize()}"],
                ["Orientador", Paragraph(_texto(orientacao.orientador.nome), cel)],
                ["Coorientadores", Paragraph(_texto(coorientadores), cel)],
                [
                    "Período",
                    f"Início: {orientacao.data_inicio:%d/%m/%Y} · Fim previsto: {fim_txt}",
                ],
                ["Relógio do vínculo", Paragraph(_texto(relogio_txt), cel)],
            ],
            larguras=[45 * mm, 125 * mm],
        ),
        Spacer(1, 3 * mm),
        _tabela(
            [
                [
                    Paragraph("<b>Marcos do cronograma</b>", cel),
                    Paragraph("<b>Documentos e versões</b>", cel),
                    Paragraph("<b>Pareceres emitidos</b>", cel),
                    Paragraph("<b>Reuniões e presença</b>", cel),
                ],
                [
                    Paragraph(_texto(resumo_marcos), cel),
                    Paragraph(_texto(resumo_docs), cel),
                    Paragraph(_texto(resumo_pareceres), cel),
                    Paragraph(_texto(resumo_reunioes), cel),
                ],
            ],
            larguras=[42 * mm, 43 * mm, 42 * mm, 43 * mm],
        ),
    ]


def _cronograma(marcos, estilos, cel) -> list:
    blocos = _secao(estilos, "Cronograma e entregas por tarefa")
    if not marcos:
        return blocos + [Paragraph("Nenhum marco cadastrado.", estilos["BodyText"])]

    linhas = [["Etapa / Tipo", "Marco / Tarefa", "Prazo / Conclusão", "Situação e detalhes"]]
    for m in marcos:
        etapa = ETAPA_MARCO_LABEL.get(m.etapa, "Não classificada")
        tipo = TIPO_MARCO_LABEL.get(m.tipo, m.tipo)
        if m.grupo_id:
            tipo += " · grupo"

        col_tarefa = [f"<b>{_texto(m.titulo)}</b>"]
        if m.descricao:
            col_tarefa.append(f"<font size=7 color='#333333'>{_texto(m.descricao)}</font>")
        if m.entrega_esperada:
            rotulo_esp = ENTREGA_ESPERADA_LABEL.get(
                m.entrega_esperada, m.entrega_esperada
            )
            col_tarefa.append(
                f"<font size=7 color='#5a6570'>Espera: {_texto(rotulo_esp)}</font>"
            )

        prazos = f"Prev.: {m.data_prevista:%d/%m/%Y}"
        if m.data_conclusao:
            prazos += f"<br/>Concl.: {m.data_conclusao:%d/%m/%Y}"

        if m.status == "concluido":
            situacao = "Concluído"
        elif m.aguardando == "orientador":
            situacao = "Aguardando orientador"
        elif m.aguardando == "orientando_revisao":
            situacao = "Devolvido para revisão"
        else:
            situacao = STATUS_MARCO_LABEL.get(m.status, m.status)
        if m.atrasado:
            situacao += " (atrasado)"

        detalhes = [f"<b>{_texto(situacao)}</b>"]
        docs_tarefa = m.documentos_da_tarefa
        if docs_tarefa:
            nomes_docs = ", ".join(d.titulo for d in docs_tarefa)
            detalhes.append(f"<font size=7>Docs: {_texto(nomes_docs)}</font>")
        if m.nota_conclusao:
            detalhes.append(
                f"<font size=7>Nota do orientando: {_texto(m.nota_conclusao)}</font>"
            )
        if m.nota_devolucao:
            detalhes.append(
                f"<font size=7>Devolução: {_texto(m.nota_devolucao)}</font>"
            )

        linhas.append([
            Paragraph(
                f"{_texto(etapa)}<br/><font size=7 color='#5a6570'>{_texto(tipo)}</font>",
                cel,
            ),
            Paragraph("<br/>".join(col_tarefa), cel),
            Paragraph(prazos, cel),
            Paragraph("<br/>".join(detalhes), cel),
        ])
    return blocos + [_tabela(linhas, larguras=[35 * mm, 55 * mm, 28 * mm, 52 * mm])]


def _entregas(
    docs, versoes_por_doc, pareceres_por_versao, revisoes_por_doc, estilos, cel
) -> list:
    blocos = _secao(estilos, "Documentos entregues e histórico de versões")
    if not docs:
        return blocos + [Paragraph("Nenhum documento enviado.", estilos["BodyText"])]

    for d in docs:
        partes_titulo = [f"<b>{_texto(d.titulo)}</b>"]
        if d.marco:
            partes_titulo.append(f"Tarefa: {_texto(d.marco.titulo)}")
        revs = revisoes_por_doc.get(d.id, [])
        if revs:
            partes_titulo.append(
                "Revisão em: " + ", ".join(_texto(r.titulo) for r in revs)
            )
        blocos.append(Paragraph(" · ".join(partes_titulo), estilos["BodyText"]))

        versoes = versoes_por_doc[d.id]
        if not versoes:
            blocos.append(Paragraph("Sem versões enviadas.", cel))
            blocos.append(Spacer(1, 3 * mm))
            continue

        linhas = [["Versão", "Data (UTC)", "Autor / Tipo", "Arquivos", "Comentário / Parecer"]]
        for v in versoes:
            nat = NATUREZA_LABEL.get(v.natureza, v.natureza)
            autor = v.remetente.nome
            if v.em_nome_do_orientando:
                autor += " (em nome da orientanda)"

            if v.tem_arquivo:
                arqs = [f"Principal: {_texto(v.nome_original)}"]
                for a in v.anexos:
                    arqs.append(f"Anexo: {_texto(a.nome_original)}")
            else:
                arqs = ["só comentário"]

            obs = []
            if v.comentario:
                obs.append(_texto(v.comentario))
            for p in pareceres_por_versao.get(v.id, []):
                obs.append(
                    f"<b>Parecer:</b> {_texto(RESULTADO_LABEL[p.resultado])} "
                    f"({p.emitido_em:%d/%m/%Y})"
                )

            linhas.append([
                f"v{v.numero_versao}",
                v.enviado_em.strftime("%d/%m/%Y %H:%M"),
                Paragraph(
                    f"{_texto(autor)}<br/><font size=7 color='#5a6570'>{_texto(nat)}</font>",
                    cel,
                ),
                Paragraph("<br/>".join(arqs), cel),
                Paragraph("<br/>".join(obs) if obs else "—", cel),
            ])
        blocos.append(
            _tabela(linhas, larguras=[14 * mm, 26 * mm, 35 * mm, 42 * mm, 53 * mm])
        )
        blocos.append(Spacer(1, 3 * mm))
    return blocos


def _pareceres(pareceres, estilos) -> list:
    blocos = _secao(estilos, "Pareceres emitidos")
    if not pareceres:
        return blocos + [Paragraph("Nenhum parecer emitido.", estilos["BodyText"])]

    for p in pareceres:
        alvo = ""
        if p.versao_documento:
            doc = p.versao_documento.documento
            alvo = f" · {doc.titulo} (v{p.versao_documento.numero_versao})"
            if doc.marco:
                alvo += f" · marco: {doc.marco.titulo}"
        blocos.append(
            Paragraph(
                f"<b>{p.tipo.capitalize()}</b>: {RESULTADO_LABEL[p.resultado]}"
                f"{_texto(alvo)}<br/>"
                f"<font size=7 color='#5a6570'>Emitido por {_texto(p.emissor.nome)} "
                f"em {p.emitido_em.strftime('%d/%m/%Y')}</font>",
                estilos["BodyText"],
            )
        )
        blocos += marcacao.para_flowables(p.conteudo, estilos, p.formato_conteudo)
        blocos.append(Spacer(1, 3 * mm))
    return blocos


def _reunioes(orientacao, atas, estilos, cel) -> list:
    blocos = _secao(estilos, "Reuniões de orientação")
    if not atas:
        return blocos + [Paragraph("Nenhuma reunião registrada.", estilos["BodyText"])]

    linhas = [["Data", "Tipo", "Situação", "Presença", "Marcos discutidos"]]
    for a in atas:
        part = a.participacao_de(orientacao.id)
        presenca = PRESENCA_LABEL[part.presenca] if part else "Pendente"
        marcos_txt = (
            linha_tempo.marcos_discutidos_do_vinculo(a, orientacao.id) or "—"
        )
        data_txt = a.data_reuniao.strftime("%d/%m/%Y") + (
            f" {a.hora_reuniao.strftime('%H:%M')}" if a.hora_reuniao else ""
        )
        linhas.append([
            data_txt,
            a.tipo,
            _situacao_reuniao(a),
            presenca,
            Paragraph(_texto(marcos_txt), cel),
        ])
    blocos.append(
        _tabela(linhas, larguras=[28 * mm, 22 * mm, 25 * mm, 25 * mm, 70 * mm])
    )
    blocos.append(Spacer(1, 3 * mm))
    return blocos


def _eventos_vinculo(orientacao, estilos, cel) -> list:
    if not orientacao.eventos:
        return []
    linhas = [["Evento", "Alteração", "Fundamentação", "Data (UTC)"]]
    for e in orientacao.eventos:
        if e.tipo == "prorrogacao":
            ant = e.data_anterior.strftime("%d/%m/%Y") if e.data_anterior else "não definida"
            nov = e.data_nova.strftime("%d/%m/%Y") if e.data_nova else ""
            alt = f"{ant} → {nov}"
        elif e.tipo == "mudanca_titulo":
            alt = f"{e.texto_anterior or ''} → {e.texto_novo or ''}"
        else:
            alt = "não se aplica"
        linhas.append([
            Paragraph(_texto(TIPO_EVENTO_LABEL.get(e.tipo, e.tipo)), cel),
            Paragraph(_texto(alt), cel),
            Paragraph(_texto(e.fundamentacao), cel),
            e.registrado_em.strftime("%d/%m/%Y %H:%M"),
        ])
    return _secao(estilos, "Eventos formais do vínculo") + [
        _tabela(linhas, larguras=[35 * mm, 45 * mm, 65 * mm, 25 * mm])
    ]


def _linha_do_tempo(orientacao, estilos, cel) -> list:
    """Cronologia completa do vínculo do mais recente ao mais antigo."""
    eventos = linha_tempo.eventos(orientacao)
    if not eventos:
        return []
    linhas = [["Data", "Evento", "Descrição"]]
    for e in eventos:
        desc = e["titulo"]
        if e.get("detalhe"):
            desc += f": {e['detalhe']}"
        if e.get("relacionado"):
            desc += f" · {e['relacionado']}"
        linhas.append([
            e["data"].strftime("%d/%m/%Y"),
            linha_tempo.TIPOS[e["tipo"]],
            Paragraph(_texto(desc), cel),
        ])
    return _secao(estilos, "Linha do tempo consolidada") + [
        _tabela(linhas, larguras=[25 * mm, 35 * mm, 110 * mm])
    ]


def gerar_pdf_relatorio(orientacao) -> bytes:
    buffer = BytesIO()
    doc, estilos = _documento_base(
        buffer, f"ARIADNE · Extrato do orientando ({orientacao.orientando.nome})"
    )
    cel = _estilo_celula(estilos)

    marcos = orientacao.marcos.all()
    docs = orientacao.documentos.order_by(Documento.criado_em.desc()).all()
    versoes_por_doc = {
        d.id: (d.versoes.all() if hasattr(d.versoes, "all") else list(d.versoes))
        for d in docs
    }
    pareceres = orientacao.pareceres.order_by(
        Parecer.emitido_em.desc(), Parecer.id.desc()
    ).all()
    pareceres_por_versao: dict[int, list[Parecer]] = {}
    for p in pareceres:
        if p.versao_documento_id is not None:
            pareceres_por_versao.setdefault(p.versao_documento_id, []).append(p)
    revisoes_por_doc: dict[int, list] = {}
    for m in marcos:
        if m.entrega_esperada == "revisao" and m.documento_base_id is not None:
            revisoes_por_doc.setdefault(m.documento_base_id, []).append(m)
    atas = orientacao.atas.order_by(Ata.data_reuniao.desc(), Ata.id.desc()).all()

    fluxo = _cabecalho_e_resumo(
        orientacao, marcos, docs, versoes_por_doc, pareceres, atas, estilos, cel
    )
    fluxo += _cronograma(marcos, estilos, cel)
    fluxo += _entregas(
        docs, versoes_por_doc, pareceres_por_versao, revisoes_por_doc, estilos, cel
    )
    fluxo += _pareceres(pareceres, estilos)
    fluxo += _reunioes(orientacao, atas, estilos, cel)
    fluxo += _eventos_vinculo(orientacao, estilos, cel)
    fluxo += _linha_do_tempo(orientacao, estilos, cel)
    fluxo += [
        Spacer(1, 6 * mm),
        Paragraph(
            "Extrato de momento gerado pelo ARIADNE em "
            f"{agora().strftime('%d/%m/%Y às %H:%M')} (UTC). Diferentemente de "
            "atas e pareceres, este extrato não é um ato imutável e não carrega "
            "hash de verificação: reflete o estado do vínculo na data acima.",
            estilos["Rodape"],
        ),
    ]
    doc.build(fluxo)
    return buffer.getvalue()
