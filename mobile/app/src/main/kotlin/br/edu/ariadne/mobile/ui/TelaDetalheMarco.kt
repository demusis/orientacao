package br.edu.ariadne.mobile.ui

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import br.edu.ariadne.mobile.core.AriadneCatalogos
import br.edu.ariadne.mobile.core.Documento
import br.edu.ariadne.mobile.core.Marco
import br.edu.ariadne.mobile.core.Orientacao
import br.edu.ariadne.mobile.core.Usuario
import br.edu.ariadne.mobile.core.documentosDaTarefa
import br.edu.ariadne.mobile.core.estaAtrasado
import br.edu.ariadne.mobile.core.formatarDataBr
import br.edu.ariadne.mobile.core.formatarDataHoraBr
import br.edu.ariadne.mobile.core.hojeIso
import br.edu.ariadne.mobile.ui.theme.coresAriadne
import java.io.File
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Mesmo teto do servidor (MAX_CONTENT_LENGTH). */
private const val LIMITE_BYTES = 20L * 1024 * 1024

/** Extensões aceitas pelo servidor (config.ALLOWED_EXTENSIONS). */
private val EXTENSOES_ACEITAS = setOf(
    "pdf", "doc", "docx", "odt", "txt", "zip", "xlsx", "xls", "ods", "csv", "png", "jpg", "jpeg",
)

private val TIPOS_SELETOR = arrayOf(
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/zip",
    "text/plain",
    "text/csv",
    "text/comma-separated-values",
    "image/png",
    "image/jpeg",
)

/** Arquivo escolhido pelo usuário, já copiado para o cache do app (o núcleo
 * Rust lê de um caminho, não de um content://). `opId` acompanha a escolha:
 * reenviar o mesmo arquivo depois de uma falha de rede não duplica a versão. */
private data class ArquivoEscolhido(
    val caminho: String,
    val nome: String,
    val mime: String?,
    val tamanho: Long,
    val opId: String = UUID.randomUUID().toString(),
)

private fun copiarParaCache(context: Context, uri: Uri): Result<ArquivoEscolhido> = runCatching {
    val resolver = context.contentResolver
    var nome = "arquivo"
    var tamanho = -1L
    resolver.query(uri, null, null, null, null)?.use { c ->
        if (c.moveToFirst()) {
            val iNome = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            val iTam = c.getColumnIndex(OpenableColumns.SIZE)
            if (iNome >= 0 && !c.isNull(iNome)) nome = c.getString(iNome)
            if (iTam >= 0 && !c.isNull(iTam)) tamanho = c.getLong(iTam)
        }
    }
    val ext = nome.substringAfterLast('.', "").lowercase()
    require(ext in EXTENSOES_ACEITAS) {
        "Tipo de arquivo não aceito (.${ext.ifEmpty { "?" }}). Aceitos: " +
            EXTENSOES_ACEITAS.sorted().joinToString(", ") + "."
    }
    require(tamanho <= LIMITE_BYTES) { "Arquivo grande demais: o limite é de 20 MB." }
    val pasta = File(context.cacheDir, "entregas").apply { mkdirs() }
    val destino = File(pasta, "${UUID.randomUUID()}.$ext")
    resolver.openInputStream(uri).use { entrada ->
        requireNotNull(entrada) { "Não foi possível abrir o arquivo escolhido." }
        destino.outputStream().use { saida -> entrada.copyTo(saida) }
    }
    if (destino.length() > LIMITE_BYTES) {
        destino.delete()
        throw IllegalArgumentException("Arquivo grande demais: o limite é de 20 MB.")
    }
    ArquivoEscolhido(
        caminho = destino.absolutePath,
        nome = nome,
        mime = resolver.getType(uri),
        tamanho = destino.length(),
    )
}

private fun formatarTamanho(bytes: Long): String = when {
    bytes >= 1024 * 1024 -> String.format("%.1f MB", bytes / (1024.0 * 1024.0))
    bytes >= 1024 -> "${bytes / 1024} KB"
    else -> "$bytes B"
}

/**
 * Tela da tarefa: tudo o que o cartão resume, por inteiro — descrição com
 * links, notas, documentos e versões — e as ações: enviar o documento
 * esperado (com a opção de sinalizar no mesmo ato), sinalizar a conclusão
 * (sempre com confirmação) e, para quem orienta, confirmar/devolver/editar.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun TelaDetalheMarco(
    marco: Marco,
    orientacao: Orientacao?,
    usuario: Usuario,
    documentos: List<Documento>,
    carregando: Boolean,
    onVoltar: () -> Unit,
    onEnfileirar: (acao: String, dadosJson: String) -> Unit,
    onEnviarEntrega: (pedidoJson: String) -> Unit,
) {
    BackHandler(onBack = onVoltar)
    val cores = coresAriadne()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val hoje = remember { hojeIso() }

    val ehOrientando = orientacao?.orientandoId == usuario.id
    val podeSinalizar = ehOrientando && marco.id > 0 && marco.status != "concluido" &&
        !marco.conclusaoSinalizada
    val podeGerir = marco.id > 0 &&
        (usuario.papel == "admin" || orientacao?.orientadorId == usuario.id)
    val podeEnviar = marco.id > 0 && marco.status != "concluido" &&
        (ehOrientando || podeGerir)
    val esperaArquivo = marco.entregaEsperada != "ato"

    val docsTarefa = remember(marco, documentos) { marco.documentosDaTarefa(documentos) }
    val totalVersoes = docsTarefa.sumOf { it.versoes.size }

    var arquivo by remember(marco.id) { mutableStateOf<ArquivoEscolhido?>(null) }
    var erroArquivo by remember(marco.id) { mutableStateOf<String?>(null) }
    var destino by remember(marco.id) {
        mutableStateOf(docsTarefa.firstOrNull()?.id?.toString() ?: "novo")
    }
    var tituloNovo by remember(marco.id) { mutableStateOf(marco.titulo) }
    var comentario by remember(marco.id) { mutableStateOf("") }
    var sinalizarJunto by remember(marco.id) { mutableStateOf(podeSinalizar) }
    var nota by remember(marco.id) { mutableStateOf("") }
    var confirmarSinalizacao by remember { mutableStateOf(false) }
    var confirmarEnvio by remember { mutableStateOf(false) }
    var abrirDevolver by remember { mutableStateOf(false) }
    var abrirEditar by remember { mutableStateOf(false) }

    // Envio confirmado pelo servidor (o estado volta com uma versão a mais):
    // limpa a escolha e o arquivo temporário.
    var versoesNaEscolha by remember(marco.id) { mutableStateOf(totalVersoes) }
    LaunchedEffect(totalVersoes) {
        if (arquivo != null && totalVersoes > versoesNaEscolha) {
            File(arquivo!!.caminho).delete()
            arquivo = null
            comentario = ""
        }
    }

    val seletor = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val resultado = withContext(Dispatchers.IO) { copiarParaCache(context, uri) }
            resultado.onSuccess {
                arquivo?.let { antigo -> File(antigo.caminho).delete() }
                arquivo = it
                erroArquivo = null
                versoesNaEscolha = totalVersoes
            }.onFailure { erroArquivo = it.message ?: "Falha ao ler o arquivo." }
        }
    }

    val atrasado = marco.estaAtrasado(hoje)
    val corAcento = when {
        marco.status == "concluido" -> cores.verdeAcento
        marco.aguardando == "orientando_revisao" || atrasado -> cores.vermelhoAcento
        marco.aguardando == "orientador" -> cores.ambarAcento
        else -> cores.azulDestaque
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            TextButton(onClick = onVoltar) { Text("‹ Voltar") }
        }

        item {
            CartaoAriadne(accentColor = corAcento) {
                Text(
                    text = marco.titulo,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = cores.textoPrincipal,
                )
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    if (marco.id < 0) {
                        Etiqueta("Pendente de envio", cores.ambarFundo, cores.ambarTexto)
                    }
                    val (bg, fg) = when (marco.aguardando) {
                        null -> cores.verdeFundo to cores.verdeTexto
                        "orientador" -> cores.ambarFundo to cores.ambarTexto
                        "orientando_revisao" -> cores.vermelhoFundo to cores.vermelhoTexto
                        else -> cores.infoFundo to cores.infoTexto
                    }
                    Etiqueta(AriadneCatalogos.rotuloAguardando(marco.aguardando), bg, fg)
                    if (atrasado) Etiqueta("atrasada", cores.vermelhoFundo, cores.vermelhoTexto)
                }
                orientacao?.let {
                    Text(
                        text = if (ehOrientando) it.tituloProjeto else "${it.orientandoNome} · ${it.tituloProjeto}",
                        style = MaterialTheme.typography.bodySmall,
                        color = cores.textoSecundario,
                    )
                }
                Text(
                    text = listOf(
                        "Prazo: ${formatarDataBr(marco.dataPrevista)}",
                        AriadneCatalogos.rotuloTipoMarco(marco.tipo),
                        AriadneCatalogos.rotuloEtapa(marco.etapa),
                    ).joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = cores.textoSecundario,
                )
                if (marco.dataConclusao != null) {
                    Text(
                        text = "Concluída em ${formatarDataBr(marco.dataConclusao)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = cores.verdeTexto,
                    )
                }
                AriadneCatalogos.rotuloEntregaEsperada(marco.entregaEsperada)?.let { espera ->
                    Text(
                        text = "Esperado: $espera",
                        style = MaterialTheme.typography.labelMedium,
                        color = cores.azulDestaque,
                        fontWeight = FontWeight.Medium,
                    )
                }
                if (!marco.descricao.isNullOrBlank()) {
                    TextoComLinks(
                        texto = marco.descricao,
                        style = MaterialTheme.typography.bodyMedium,
                        color = cores.textoPrincipal,
                    )
                }
                if (!marco.notaConclusao.isNullOrBlank()) {
                    NotaDestacada(
                        titulo = "Nota do orientando",
                        texto = marco.notaConclusao,
                        fundo = cores.infoFundo,
                        corBorda = cores.azulDestaque,
                        corTexto = cores.infoTexto,
                    )
                }
                if (!marco.notaDevolucao.isNullOrBlank()) {
                    NotaDestacada(
                        titulo = "Devolução do orientador" +
                            (marco.devolvidoEm?.let { " (${formatarDataBr(it)})" } ?: ""),
                        texto = marco.notaDevolucao,
                        fundo = cores.vermelhoFundo,
                        corBorda = cores.vermelhoAcento,
                        corTexto = cores.vermelhoTexto,
                    )
                }
            }
        }

        // Documentos e versões já entregues pela tarefa
        item {
            CabecalhoSecao(titulo = "Documentos da tarefa", contagem = docsTarefa.size)
        }
        if (docsTarefa.isEmpty()) {
            item {
                Text(
                    text = "Nenhum documento enviado por esta tarefa ainda.",
                    style = MaterialTheme.typography.bodySmall,
                    color = cores.textoSecundario,
                )
            }
        } else {
            docsTarefa.forEach { d ->
                item(key = "doc-${d.id}") {
                    CartaoAriadne {
                        Text(
                            text = d.titulo,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold,
                        )
                        d.versoes.forEachIndexed { i, v ->
                            if (i > 0) HorizontalDivider(color = cores.borda)
                            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(
                                    text = listOfNotNull(
                                        "v${v.numeroVersao}",
                                        v.nomeOriginal,
                                    ).joinToString(" · "),
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.Medium,
                                )
                                Text(
                                    text = "${v.remetenteNome} · ${formatarDataHoraBr(v.enviadoEm)}",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = cores.textoSecundario,
                                )
                                if (!v.comentario.isNullOrBlank()) {
                                    TextoComLinks(
                                        texto = v.comentario,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = cores.textoPrincipal,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        // Enviar documento (só online)
        if (podeEnviar && esperaArquivo) {
            item {
                CartaoAriadne(accentColor = cores.azulDestaque) {
                    Text(
                        text = "Enviar documento",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "O envio de arquivos precisa de internet. Limite de 20 MB.",
                        style = MaterialTheme.typography.labelSmall,
                        color = cores.textoSecundario,
                    )
                    OutlinedButton(
                        onClick = { seletor.launch(TIPOS_SELETOR) },
                        enabled = !carregando,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(if (arquivo == null) "Escolher arquivo…" else "Trocar arquivo…")
                    }
                    arquivo?.let { a ->
                        Text(
                            text = "${a.nome} (${formatarTamanho(a.tamanho)})",
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.Medium,
                            color = cores.textoPrincipal,
                        )
                    }
                    erroArquivo?.let { BannerMensagem(it, erro = true) }

                    if (docsTarefa.isNotEmpty()) {
                        Text(
                            text = "Para onde vai este envio?",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        docsTarefa.forEach { d ->
                            OpcaoRadio(
                                selecionada = destino == d.id.toString(),
                                texto = "Nova versão de \"${d.titulo}\"",
                                onClick = { destino = d.id.toString() },
                            )
                        }
                        OpcaoRadio(
                            selecionada = destino == "novo",
                            texto = "Documento novo",
                            onClick = { destino = "novo" },
                        )
                    }
                    if (destino == "novo") {
                        OutlinedTextField(
                            value = tituloNovo,
                            onValueChange = { tituloNovo = it },
                            label = { Text("Título do documento") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    OutlinedTextField(
                        value = comentario,
                        onValueChange = { comentario = it },
                        label = { Text("Comentário (opcional)") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    if (podeSinalizar) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { sinalizarJunto = !sinalizarJunto },
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(checked = sinalizarJunto, onCheckedChange = { sinalizarJunto = it })
                            Text(
                                text = "Esta é a entrega da tarefa — avisar o orientador para conferir",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                    Button(
                        onClick = { confirmarEnvio = true },
                        enabled = arquivo != null && !carregando &&
                            (destino != "novo" || tituloNovo.isNotBlank()),
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(if (carregando) "Enviando…" else "Enviar documento")
                    }
                }
            }
        }

        // Sinalizar conclusão sem arquivo
        if (podeSinalizar) {
            item {
                CartaoAriadne(accentColor = cores.ambarAcento) {
                    Text(
                        text = if (marco.aguardando == "orientando_revisao") {
                            "Sinalizar conclusão corrigida"
                        } else {
                            "Sinalizar conclusão"
                        },
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = if (esperaArquivo) {
                            "Avisa o orientador de que a tarefa está pronta para conferência. " +
                                "Se ela pede um documento, prefira enviá-lo acima com a opção de avisar marcada."
                        } else {
                            "Avisa o orientador de que a tarefa está pronta para conferência."
                        },
                        style = MaterialTheme.typography.bodySmall,
                        color = cores.textoSecundario,
                    )
                    OutlinedTextField(
                        value = nota,
                        onValueChange = { nota = it },
                        label = { Text("Nota para o orientador (opcional)") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Button(
                        onClick = { confirmarSinalizacao = true },
                        enabled = !carregando,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text("Sinalizar conclusão…")
                    }
                }
            }
        }

        if (podeGerir) {
            item {
                CartaoAriadne {
                    Text(
                        text = "Ações do orientador",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        if (marco.status != "concluido") {
                            Button(
                                onClick = {
                                    onEnfileirar(
                                        "confirmar_conclusao_marco",
                                        JSONObject().put("marco_id", marco.id).toString(),
                                    )
                                },
                            ) { Text("Confirmar conclusão") }
                            if (marco.conclusaoSinalizada) {
                                OutlinedButton(onClick = { abrirDevolver = true }) { Text("Devolver") }
                            }
                        }
                        OutlinedButton(onClick = { abrirEditar = true }) { Text("Editar") }
                    }
                }
            }
        }
    }

    if (confirmarSinalizacao) {
        AlertDialog(
            onDismissRequest = { confirmarSinalizacao = false },
            title = { Text("Sinalizar conclusão?") },
            text = {
                Text(
                    "A tarefa «${marco.titulo}» será marcada como pronta e o orientador será " +
                        "avisado para conferir. Enquanto não sincronizar, você pode desfazer na fila offline."
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        confirmarSinalizacao = false
                        onEnfileirar(
                            "sinalizar_conclusao_marco",
                            JSONObject().put("marco_id", marco.id).put("nota", nota.trim()).toString(),
                        )
                        nota = ""
                    },
                ) { Text("Sinalizar") }
            },
            dismissButton = {
                TextButton(onClick = { confirmarSinalizacao = false }) { Text("Cancelar") }
            },
        )
    }

    if (confirmarEnvio) {
        val a = arquivo
        AlertDialog(
            onDismissRequest = { confirmarEnvio = false },
            title = { Text("Enviar documento?") },
            text = {
                Text(
                    buildString {
                        append("O arquivo «${a?.nome}» será enviado agora ao servidor")
                        if (destino == "novo") {
                            append(" como o documento \"${tituloNovo.trim()}\"")
                        } else {
                            val d = docsTarefa.firstOrNull { it.id.toString() == destino }
                            append(" como nova versão de \"${d?.titulo}\"")
                        }
                        append(".")
                        if (podeSinalizar && sinalizarJunto) {
                            append(" O orientador será avisado para conferir a entrega.")
                        }
                    },
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        confirmarEnvio = false
                        if (a == null) return@Button
                        val pedido = JSONObject()
                            .put("op_id", a.opId)
                            .put("marco_id", marco.id)
                            .put("caminho_arquivo", a.caminho)
                            .put("nome_arquivo", a.nome)
                            .put("mime", a.mime ?: JSONObject.NULL)
                            .put("destino", destino)
                            .put("titulo", if (destino == "novo") tituloNovo.trim() else JSONObject.NULL)
                            .put("comentario", comentario.trim().ifEmpty { null } ?: JSONObject.NULL)
                            .put("sinalizar", podeSinalizar && sinalizarJunto)
                        onEnviarEntrega(pedido.toString())
                    },
                ) { Text("Enviar") }
            },
            dismissButton = {
                TextButton(onClick = { confirmarEnvio = false }) { Text("Cancelar") }
            },
        )
    }

    if (abrirDevolver) {
        DialogoTextoSimples(
            titulo = "Devolver para revisão",
            rotulo = "O que precisa corrigir (opcional)",
            textoBotao = "Devolver",
            obrigatorio = false,
            onDismiss = { abrirDevolver = false },
            onConfirmar = { texto ->
                abrirDevolver = false
                onEnfileirar(
                    "devolver_marco",
                    JSONObject().put("marco_id", marco.id).put("nota", texto).toString(),
                )
            },
        )
    }

    if (abrirEditar) {
        DialogoEditarMarco(
            marco = marco,
            onDismiss = { abrirEditar = false },
            onSalvar = { dados ->
                abrirEditar = false
                onEnfileirar("editar_marco", dados)
            },
        )
    }
}

@Composable
private fun OpcaoRadio(selecionada: Boolean, texto: String, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        RadioButton(selected = selecionada, onClick = onClick)
        Text(texto, style = MaterialTheme.typography.bodySmall)
    }
}
