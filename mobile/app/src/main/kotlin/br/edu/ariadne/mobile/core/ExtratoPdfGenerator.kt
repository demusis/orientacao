package br.edu.ariadne.mobile.core

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.time.LocalDate
import java.time.ZoneOffset
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

data class ResultadoExportacaoPdf(
    val nomeArquivo: String,
    val localDescricao: String,
    val uri: Uri?,
)

object ExtratoPdfGenerator {

    private const val LARGURA_A4 = 595
    private const val ALTURA_A4 = 842
    private const val MARGEM_H = 40f
    private const val MARGEM_SUP = 44f
    private const val MARGEM_INF = 46f
    private const val LARGURA_UTIL = LARGURA_A4 - 2 * MARGEM_H

    fun gerarESalvarExtrato(
        context: Context,
        orientacao: Orientacao,
        marcos: List<Marco>,
        documentos: List<Documento>,
        atas: List<Ata>,
        pareceres: List<Parecer>,
    ): Result<ResultadoExportacaoPdf> = runCatching {
        val bytes = gerarBytesPdf(
            orientacao = orientacao,
            marcos = marcos,
            documentos = documentos,
            atas = atas,
            pareceres = pareceres,
        )
        val nomeArquivo = "ariadne-extrato-${orientacao.id}.pdf"
        salvarNosDownloads(context, nomeArquivo, bytes)
    }

    fun abrirPdf(context: Context, uri: Uri?) {
        if (uri == null) return
        runCatching {
            val intent = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/pdf")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            context.startActivity(intent)
        }
    }

    private fun gerarBytesPdf(
        orientacao: Orientacao,
        marcos: List<Marco>,
        documentos: List<Documento>,
        atas: List<Ata>,
        pareceres: List<Parecer>,
    ): ByteArray {
        val doc = PdfDocument()
        val escritor = EscritorPdfA4(doc)
        val hoje = hojeIso()

        val marcosDoVinculo = marcos
            .filter { it.orientacaoId == orientacao.id }
            .sortedWith(compareBy<Marco> { it.etapa }.thenBy { it.dataPrevista }.thenBy { it.id })
        val docsDoVinculo = documentos.filter { it.orientacaoId == orientacao.id }
        val atasDoVinculo = atas
            .filter { it.orientacaoIds.contains(orientacao.id) }
            .sortedByDescending { it.dataReuniao }
        val pareceresDoVinculo = pareceres.filter { it.orientacaoId == orientacao.id }
        val marcosPorId = marcosDoVinculo.associateBy { it.id }

        val versaoInfoPorId = mutableMapOf<Long, Pair<Documento, VersaoDocumento>>()
        val pareceresPorVersao = mutableMapOf<Long, MutableList<Parecer>>()
        docsDoVinculo.forEach { d ->
            d.versoes.forEach { v -> versaoInfoPorId[v.id] = d to v }
        }
        pareceresDoVinculo.forEach { p ->
            p.versaoDocumentoId?.let { vid ->
                pareceresPorVersao.getOrPut(vid) { mutableListOf() }.add(p)
            }
        }

        // Título principal
        escritor.titulo("ARIADNE · Extrato de acompanhamento do orientando")

        // Ficha cadastral
        val fimTxt = orientacao.dataFimPrevista?.let(::formatarDataBr) ?: "não definido"
        val prazoResumo = calcularTextoPrazo(orientacao.dataInicio, orientacao.dataFimPrevista, hoje)
        escritor.tabela(
            linhas = listOf(
                listOf("Orientando", orientacao.orientandoNome),
                listOf("Projeto", orientacao.tituloProjeto),
                listOf(
                    "Modalidade / Situação",
                    "${AriadneCatalogos.rotuloModalidade(orientacao.modalidade)} · ${orientacao.status.replaceFirstChar { it.uppercase() }}",
                ),
                listOf("Orientador", orientacao.orientadorNome),
                listOf("Período", "Início: ${formatarDataBr(orientacao.dataInicio)} · Fim previsto: $fimTxt"),
                listOf("Relógio do vínculo", prazoResumo),
            ),
            larguras = listOf(140f, LARGURA_UTIL - 140f),
            primeiraLinhaCabecalho = false,
        )

        escritor.espaco(10f)

        // Quadro resumo 4 colunas (equivalente ao relatorio.py web)
        val concluidasM = marcosDoVinculo.count { it.status == "concluido" }
        val emAbertoM = marcosDoVinculo.size - concluidasM
        val atrasadasM = marcosDoVinculo.count { it.estaAtrasado(hoje) }
        val resumoMarcos = "${marcosDoVinculo.size} total ($concluidasM concluído(s), $emAbertoM em aberto, $atrasadasM atrasado(s))"

        val totalVersoes = docsDoVinculo.sumOf { it.versoes.size }
        val resumoDocs = "${docsDoVinculo.size} documento(s), $totalVersoes versão(ões)"
        val resumoPareceres = "${pareceresDoVinculo.size} emitido(s)"
        val presentes = atasDoVinculo.count { a ->
            a.participacoes.any { it.orientacaoId == orientacao.id && it.presenca == "presente" }
        }
        val ausentes = atasDoVinculo.count { a ->
            a.participacoes.any { it.orientacaoId == orientacao.id && it.presenca == "ausente" }
        }
        val resumoReunioes = "${atasDoVinculo.size} registrada(s) ($presentes presença(s), $ausentes ausência(s))"

        escritor.tabela(
            linhas = listOf(
                listOf("Marcos do cronograma", "Documentos e versões", "Pareceres emitidos", "Reuniões e presença"),
                listOf(resumoMarcos, resumoDocs, resumoPareceres, resumoReunioes),
            ),
            larguras = listOf(LARGURA_UTIL * 0.25f, LARGURA_UTIL * 0.25f, LARGURA_UTIL * 0.23f, LARGURA_UTIL * 0.27f),
            primeiraLinhaCabecalho = true,
        )

        // Cronograma
        escritor.secao("Cronograma e entregas por tarefa")
        if (marcosDoVinculo.isEmpty()) {
            escritor.paragrafo("Nenhum marco cadastrado.")
        } else {
            val linhasCrono = mutableListOf(
                listOf("Etapa / Tipo", "Marco / Tarefa", "Prazo / Conclusão", "Situação e detalhes")
            )
            marcosDoVinculo.forEach { m ->
                val etapaTxt = AriadneCatalogos.rotuloEtapa(m.etapa)
                val tipoTxt = AriadneCatalogos.rotuloTipoMarco(m.tipo) + if (m.grupoId != null) " · grupo" else ""

                val colTarefa = buildList {
                    add(m.titulo)
                    m.descricao?.takeIf { it.isNotBlank() }?.let { add(it) }
                    AriadneCatalogos.rotuloEntregaEsperada(m.entregaEsperada)?.let { add("Espera: $it") }
                }.joinToString("\n")

                val prazosTxt = buildString {
                    append("Prev.: ${formatarDataBr(m.dataPrevista)}")
                    m.dataConclusao?.takeIf { it.isNotBlank() }?.let {
                        append("\nConcl.: ${formatarDataBr(it)}")
                    }
                }

                val sitBase = when {
                    m.status == "concluido" -> "Concluído"
                    m.aguardando == "orientador" -> "Aguardando orientador"
                    m.aguardando == "orientando_revisao" -> "Devolvido para revisão"
                    else -> AriadneCatalogos.rotuloAguardando(m.aguardando)
                }
                val situacao = if (m.estaAtrasado(hoje)) "$sitBase (atrasado)" else sitBase
                val docsMarco = docsDoVinculo.filter { it.marcoId == m.id }
                val colDetalhes = buildList {
                    add(situacao)
                    if (docsMarco.isNotEmpty()) {
                        add("Docs: ${docsMarco.joinToString(", ") { it.titulo }}")
                    }
                    m.notaConclusao?.takeIf { it.isNotBlank() }?.let { add("Nota do orientando: $it") }
                    m.notaDevolucao?.takeIf { it.isNotBlank() }?.let { add("Devolução: $it") }
                }.joinToString("\n")

                linhasCrono.add(listOf("$etapaTxt\n$tipoTxt", colTarefa, prazosTxt, colDetalhes))
            }
            escritor.tabela(
                linhas = linhasCrono,
                larguras = listOf(LARGURA_UTIL * 0.21f, LARGURA_UTIL * 0.32f, LARGURA_UTIL * 0.17f, LARGURA_UTIL * 0.30f),
                primeiraLinhaCabecalho = true,
            )
        }

        // Documentos entregues e histórico de versões
        escritor.secao("Documentos entregues e histórico de versões")
        if (docsDoVinculo.isEmpty()) {
            escritor.paragrafo("Nenhum documento enviado.")
        } else {
            docsDoVinculo.forEach { d ->
                val cabDoc = buildList {
                    add(d.titulo)
                    d.marcoTitulo?.takeIf { it.isNotBlank() }?.let { add("Tarefa: $it") }
                }.joinToString(" · ")
                escritor.subtituloItem(cabDoc)
                if (d.versoes.isEmpty()) {
                    escritor.paragrafo("Sem versões enviadas.")
                } else {
                    val linhasDoc = mutableListOf(
                        listOf("Versão", "Data (UTC)", "Autor / Tipo", "Arquivo", "Comentário / Parecer")
                    )
                    d.versoes.forEach { v ->
                        val dataTxt = v.enviadoEm?.let(::formatarDataHoraBr) ?: "—"
                        val natRotulo = when (v.natureza) {
                            "devolucao" -> "devolução"
                            "entrega" -> "entrega do orientando"
                            else -> "registro"
                        }
                        val arquivoTxt = v.nomeOriginal ?: if (v.temArquivo) "Arquivo anexado" else "só comentário"
                        val obs = buildList {
                            v.comentario?.takeIf { it.isNotBlank() }?.let { add(it) }
                            pareceresPorVersao[v.id].orEmpty().forEach { p ->
                                add(
                                    "Parecer: ${AriadneCatalogos.rotuloResultadoParecer(p.resultado)} (${formatarDataBr(p.emitidoEm)})"
                                )
                            }
                        }.ifEmpty { listOf("—") }.joinToString("\n")
                        linhasDoc.add(
                            listOf(
                                "v${v.numeroVersao}",
                                dataTxt,
                                "${v.remetenteNome.ifBlank { "Participante" }}\n$natRotulo",
                                arquivoTxt,
                                obs,
                            )
                        )
                    }
                    escritor.tabela(
                        linhas = linhasDoc,
                        larguras = listOf(
                            LARGURA_UTIL * 0.10f,
                            LARGURA_UTIL * 0.17f,
                            LARGURA_UTIL * 0.21f,
                            LARGURA_UTIL * 0.24f,
                            LARGURA_UTIL * 0.28f,
                        ),
                        primeiraLinhaCabecalho = true,
                    )
                    escritor.espaco(6f)
                }
            }
        }

        // Pareceres emitidos
        escritor.secao("Pareceres emitidos")
        if (pareceresDoVinculo.isEmpty()) {
            escritor.paragrafo("Nenhum parecer emitido.")
        } else {
            pareceresDoVinculo.forEach { p ->
                val infoLocal = p.versaoDocumentoId?.let { versaoInfoPorId[it] }
                val docTitulo = p.documentoTitulo ?: infoLocal?.first?.titulo
                val numVersao = p.numeroVersao ?: infoLocal?.second?.numeroVersao
                val marcoTitulo = p.marcoTitulo
                    ?: infoLocal?.first?.marcoTitulo
                    ?: infoLocal?.second?.marcoAbertoTitulo
                val nomeArq = p.nomeArquivo ?: infoLocal?.second?.nomeOriginal

                val alvo = buildString {
                    if (!docTitulo.isNullOrBlank()) {
                        append(" · $docTitulo")
                        if (numVersao != null) append(" (v$numVersao)")
                    }
                    if (!marcoTitulo.isNullOrBlank()) {
                        append(" · marco: $marcoTitulo")
                    }
                }
                val cab = "${p.tipo.replaceFirstChar { it.uppercase() }}: " +
                    "${AriadneCatalogos.rotuloResultadoParecer(p.resultado)}$alvo"
                val meta = buildList {
                    p.emissorNome?.takeIf { it.isNotBlank() }?.let { add("Emitido por $it") }
                    add("Em ${formatarDataHoraBr(p.emitidoEm)} (UTC)")
                    nomeArq?.takeIf { it.isNotBlank() }?.let { add("Arquivo: $it") }
                }.joinToString(" · ")

                escritor.blocoParecer(cabecalho = cab, metadados = meta, conteudo = p.conteudo)
            }
        }

        // Reuniões de orientação
        escritor.secao("Reuniões de orientação")
        if (atasDoVinculo.isEmpty()) {
            escritor.paragrafo("Nenhuma reunião registrada.")
        } else {
            val linhasAta = mutableListOf(
                listOf("Data", "Tipo", "Situação", "Presença", "Pauta / Marcos discutidos")
            )
            atasDoVinculo.forEach { a ->
                val part = a.participacoes.firstOrNull { it.orientacaoId == orientacao.id }
                val presenca = when (part?.presenca) {
                    "presente" -> "Presente"
                    "ausente" -> "Ausente"
                    else -> "Pendente"
                }
                val situacao = when (a.status) {
                    "finalizada" -> "Finalizada"
                    "cancelada" -> "Cancelada"
                    else -> if (a.ehPassadaOuHoje(hoje)) "Rascunho" else "Agendada"
                }
                val dataTxt = formatarDataBr(a.dataReuniao) + (a.horaReuniao?.let { " $it" } ?: "")
                val marcosDiscutidos = a.marcoIds.mapNotNull { marcosPorId[it]?.titulo }
                val detalhesReuniao = buildList {
                    if (a.pauta.isNotBlank()) add("Pauta: ${a.pauta}")
                    if (marcosDiscutidos.isNotEmpty()) add("Marcos: ${marcosDiscutidos.joinToString(", ")}")
                    if (a.deliberacoes.isNotBlank()) add("Deliberações: ${a.deliberacoes}")
                }.ifEmpty { listOf("—") }.joinToString("\n")
                linhasAta.add(listOf(dataTxt, a.tipo, situacao, presenca, detalhesReuniao))
            }
            escritor.tabela(
                linhas = linhasAta,
                larguras = listOf(
                    LARGURA_UTIL * 0.17f,
                    LARGURA_UTIL * 0.13f,
                    LARGURA_UTIL * 0.14f,
                    LARGURA_UTIL * 0.14f,
                    LARGURA_UTIL * 0.42f,
                ),
                primeiraLinhaCabecalho = true,
            )
        }

        // Rodapé honesto equivalente ao web
        val agoraUtc = ZonedDateTime.now(ZoneOffset.UTC)
            .format(DateTimeFormatter.ofPattern("dd/MM/yyyy 'às' HH:mm"))
        escritor.espaco(14f)
        escritor.rodape(
            "Extrato de momento gerado pelo ARIADNE em $agoraUtc (UTC). " +
                "Diferentemente de atas e pareceres, este extrato não é um ato imutável e não carrega " +
                "hash de verificação: reflete os dados sincronizados do vínculo nesta data."
        )

        escritor.fechar()
        val saida = ByteArrayOutputStream()
        doc.writeTo(saida)
        doc.close()
        return saida.toByteArray()
    }

    private fun calcularTextoPrazo(dataInicio: String, dataFimPrevista: String?, hoje: String): String {
        val inicio = runCatching { LocalDate.parse(dataInicio) }.getOrNull()
        val hojeDt = runCatching { LocalDate.parse(hoje) }.getOrNull()
        val mesesDecorridos = if (inicio != null && hojeDt != null) {
            maxOf(ChronoUnit.DAYS.between(inicio, hojeDt).toInt(), 0) / 30
        } else {
            0
        }
        val fimDt = dataFimPrevista?.takeIf { it.isNotBlank() }?.let {
            runCatching { LocalDate.parse(it) }.getOrNull()
        }
        if (inicio == null || hojeDt == null || fimDt == null || !fimDt.isAfter(inicio)) {
            return "$mesesDecorridos mês(es) · prazo não definido"
        }
        val mesesTotal = maxOf(kotlin.math.round(ChronoUnit.DAYS.between(inicio, fimDt) / 30.0).toInt(), 1)
        val diasRestantes = ChronoUnit.DAYS.between(hojeDt, fimDt)
        val base = "mês ${minOf(mesesDecorridos, mesesTotal)} de $mesesTotal"
        return when {
            diasRestantes >= 0 -> "$base · $diasRestantes dia(s) restante(s)"
            else -> "$base · vencido há ${-diasRestantes} dia(s)"
        }
    }

    private fun salvarNosDownloads(
        context: Context,
        nomeArquivo: String,
        bytes: ByteArray,
    ): ResultadoExportacaoPdf {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, nomeArquivo)
                put(MediaStore.Downloads.MIME_TYPE, "application/pdf")
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val resolver = context.contentResolver
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: error("Não foi possível criar arquivo em Downloads.")
            resolver.openOutputStream(uri)?.use { out ->
                out.write(bytes)
            } ?: error("Não foi possível gravar PDF em Downloads.")
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            return ResultadoExportacaoPdf(
                nomeArquivo = nomeArquivo,
                localDescricao = "Downloads/$nomeArquivo",
                uri = uri,
            )
        }

        @Suppress("DEPRECATION")
        val pastaPublica = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
        val destinoPublico = runCatching {
            pastaPublica.mkdirs()
            val arq = File(pastaPublica, nomeArquivo)
            FileOutputStream(arq).use { it.write(bytes) }
            arq
        }.getOrNull()
        if (destinoPublico != null) {
            return ResultadoExportacaoPdf(
                nomeArquivo = nomeArquivo,
                localDescricao = destinoPublico.absolutePath,
                uri = null,
            )
        }
        val pastaApp = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS) ?: context.filesDir
        pastaApp.mkdirs()
        val arqApp = File(pastaApp, nomeArquivo)
        FileOutputStream(arqApp).use { it.write(bytes) }
        return ResultadoExportacaoPdf(
            nomeArquivo = nomeArquivo,
            localDescricao = arqApp.absolutePath,
            uri = null,
        )
    }

    private class EscritorPdfA4(private val doc: PdfDocument) {
        private var numPagina = 0
        private var pagina: PdfDocument.Page? = null
        private var y = MARGEM_SUP

        private val paintTitulo = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(20, 50, 90)
            textSize = 15f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        }
        private val paintSecao = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(20, 50, 90)
            textSize = 11.5f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        }
        private val paintSub = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(32, 41, 52)
            textSize = 9.5f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        }
        private val paintCorpo = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(32, 41, 52)
            textSize = 8.5f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
        }
        private val paintMeta = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(90, 101, 112)
            textSize = 7.8f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
        }
        private val paintCelula = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(30, 35, 42)
            textSize = 7.8f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
        }
        private val paintCabTabela = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(20, 40, 68)
            textSize = 7.8f
            typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
        }
        private val paintBorda = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.rgb(160, 170, 182)
            style = Paint.Style.STROKE
            strokeWidth = 0.5f
        }
        private val paintFundoCab = Paint().apply {
            color = Color.rgb(230, 235, 241)
            style = Paint.Style.FILL
        }

        private fun novaPagina(): Canvas {
            pagina?.let { doc.finishPage(it) }
            numPagina += 1
            val info = PdfDocument.PageInfo.Builder(LARGURA_A4, ALTURA_A4, numPagina).create()
            val p = doc.startPage(info)
            pagina = p
            y = MARGEM_SUP
            return p.canvas
        }

        private fun canvasAtual(alturaNecessaria: Float): Canvas {
            val atual = pagina
            if (atual == null || y + alturaNecessaria > ALTURA_A4 - MARGEM_INF) {
                return novaPagina()
            }
            return atual.canvas
        }

        private fun layoutTexto(texto: String, paint: TextPaint, largura: Float): StaticLayout {
            val seguro = texto.ifEmpty { " " }
            return StaticLayout.Builder
                .obtain(seguro, 0, seguro.length, paint, largura.toInt().coerceAtLeast(10))
                .setAlignment(Layout.Alignment.ALIGN_NORMAL)
                .setLineSpacing(0f, 1.15f)
                .build()
        }

        fun espaco(dp: Float) {
            y += dp
        }

        fun titulo(texto: String) {
            val l = layoutTexto(texto, paintTitulo, LARGURA_UTIL)
            val c = canvasAtual(l.height + 10f)
            c.save()
            c.translate(MARGEM_H, y)
            l.draw(c)
            c.restore()
            y += l.height + 10f
        }

        fun secao(texto: String) {
            val l = layoutTexto(texto, paintSecao, LARGURA_UTIL)
            val c = canvasAtual(l.height + 24f)
            y += 10f
            c.save()
            c.translate(MARGEM_H, y)
            l.draw(c)
            c.restore()
            y += l.height + 5f
        }

        fun subtituloItem(texto: String) {
            val l = layoutTexto(texto, paintSub, LARGURA_UTIL)
            val c = canvasAtual(l.height + 14f)
            c.save()
            c.translate(MARGEM_H, y)
            l.draw(c)
            c.restore()
            y += l.height + 4f
        }

        fun paragrafo(texto: String) {
            val l = layoutTexto(texto, paintCorpo, LARGURA_UTIL)
            val c = canvasAtual(l.height + 6f)
            c.save()
            c.translate(MARGEM_H, y)
            l.draw(c)
            c.restore()
            y += l.height + 6f
        }

        fun rodape(texto: String) {
            val l = layoutTexto(texto, paintMeta, LARGURA_UTIL)
            val c = canvasAtual(l.height + 4f)
            c.save()
            c.translate(MARGEM_H, y)
            l.draw(c)
            c.restore()
            y += l.height + 4f
        }

        fun blocoParecer(cabecalho: String, metadados: String, conteudo: String) {
            val lCab = layoutTexto(cabecalho, paintSub, LARGURA_UTIL - 12f)
            val lMeta = layoutTexto(metadados, paintMeta, LARGURA_UTIL - 12f)
            val lCont = layoutTexto(conteudo, paintCorpo, LARGURA_UTIL - 12f)
            val totalAlt = lCab.height + lMeta.height + lCont.height + 20f
            val c = canvasAtual(minOf(totalAlt, ALTURA_A4 - MARGEM_SUP - MARGEM_INF))
            val topo = y
            var cy = topo + 6f

            c.save()
            c.translate(MARGEM_H + 6f, cy)
            lCab.draw(c)
            c.restore()
            cy += lCab.height + 2f

            c.save()
            c.translate(MARGEM_H + 6f, cy)
            lMeta.draw(c)
            c.restore()
            cy += lMeta.height + 4f

            if (cy + lCont.height > ALTURA_A4 - MARGEM_INF) {
                c.drawRect(MARGEM_H, topo, MARGEM_H + LARGURA_UTIL, cy, paintBorda)
                val c2 = novaPagina()
                c2.save()
                c2.translate(MARGEM_H + 6f, y + 6f)
                lCont.draw(c2)
                c2.restore()
                val fim2 = y + lCont.height + 12f
                c2.drawRect(MARGEM_H, y, MARGEM_H + LARGURA_UTIL, fim2, paintBorda)
                y = fim2 + 8f
            } else {
                c.save()
                c.translate(MARGEM_H + 6f, cy)
                lCont.draw(c)
                c.restore()
                val fim = cy + lCont.height + 6f
                c.drawRect(MARGEM_H, topo, MARGEM_H + LARGURA_UTIL, fim, paintBorda)
                y = fim + 8f
            }
        }

        fun tabela(
            linhas: List<List<String>>,
            larguras: List<Float>,
            primeiraLinhaCabecalho: Boolean,
        ) {
            if (linhas.isEmpty()) return
            val padH = 5f
            val padV = 4f
            val cabecalho = if (primeiraLinhaCabecalho) linhas.first() else null

            linhas.forEachIndexed { idx, celulas ->
                val ehCab = primeiraLinhaCabecalho && idx == 0
                val p = if (ehCab) paintCabTabela else paintCelula
                val layouts = celulas.mapIndexed { cIdx, txt ->
                    val larg = larguras.getOrElse(cIdx) { 60f } - 2 * padH
                    layoutTexto(txt, p, larg)
                }
                val alturaLinha = (layouts.maxOfOrNull { it.height } ?: 10) + 2 * padV

                val precisaQuebrar = (pagina == null || y + alturaLinha > ALTURA_A4 - MARGEM_INF)
                if (precisaQuebrar) {
                    novaPagina()
                    if (!ehCab && cabecalho != null) {
                        desenharLinhaTabela(cabecalho, larguras, ehCab = true, padH = padH, padV = padV)
                    }
                }
                desenharLinhaTabela(celulas, larguras, ehCab = ehCab, padH = padH, padV = padV)
            }
        }

        private fun desenharLinhaTabela(
            celulas: List<String>,
            larguras: List<Float>,
            ehCab: Boolean,
            padH: Float,
            padV: Float,
        ) {
            val c = pagina?.canvas ?: novaPagina()
            val p = if (ehCab) paintCabTabela else paintCelula
            val layouts = celulas.mapIndexed { cIdx, txt ->
                val larg = larguras.getOrElse(cIdx) { 60f } - 2 * padH
                layoutTexto(txt, p, larg)
            }
            val alturaLinha = (layouts.maxOfOrNull { it.height } ?: 10) + 2 * padV

            if (ehCab) {
                c.drawRect(MARGEM_H, y, MARGEM_H + larguras.sum(), y + alturaLinha, paintFundoCab)
            }

            var x = MARGEM_H
            celulas.indices.forEach { cIdx ->
                val w = larguras.getOrElse(cIdx) { 60f }
                c.drawRect(x, y, x + w, y + alturaLinha, paintBorda)
                c.save()
                c.translate(x + padH, y + padV)
                layouts[cIdx].draw(c)
                c.restore()
                x += w
            }
            y += alturaLinha
        }

        fun fechar() {
            pagina?.let { doc.finishPage(it) }
            pagina = null
        }
    }
}
