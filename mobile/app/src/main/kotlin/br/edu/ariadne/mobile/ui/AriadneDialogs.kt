package br.edu.ariadne.mobile.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import br.edu.ariadne.mobile.core.AriadneCatalogos
import br.edu.ariadne.mobile.core.Ata
import br.edu.ariadne.mobile.core.Documento
import br.edu.ariadne.mobile.core.ItemFila
import br.edu.ariadne.mobile.core.descricao
import br.edu.ariadne.mobile.core.Marco
import br.edu.ariadne.mobile.core.Orientacao
import br.edu.ariadne.mobile.core.formatarDataBr
import br.edu.ariadne.mobile.core.formatarDataHoraBr
import br.edu.ariadne.mobile.core.hojeIso
import br.edu.ariadne.mobile.ui.theme.coresAriadne
import org.json.JSONArray
import org.json.JSONObject

@Composable
fun DialogoTextoSimples(
    titulo: String,
    rotulo: String,
    textoBotao: String,
    obrigatorio: Boolean,
    onDismiss: () -> Unit,
    onConfirmar: (String) -> Unit,
) {
    var texto by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(titulo) },
        text = {
            OutlinedTextField(
                value = texto,
                onValueChange = { texto = it },
                label = { Text(rotulo) },
                minLines = 2,
                modifier = Modifier.fillMaxWidth(),
            )
        },
        confirmButton = {
            Button(
                onClick = { onConfirmar(texto.trim()) },
                enabled = !obrigatorio || texto.trim().isNotEmpty(),
            ) { Text(textoBotao) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Fechar") }
        },
    )
}

@Composable
fun DialogoNovaTarefa(
    orientacoes: List<Orientacao>,
    orientacaoInicialId: Long? = null,
    onDismiss: () -> Unit,
    onSalvar: (String) -> Unit,
) {
    val selecionadas = remember(orientacaoInicialId) {
        mutableStateListOf<Long>().apply {
            if (orientacaoInicialId != null && orientacoes.any { it.id == orientacaoInicialId && it.status == "ativa" }) {
                add(orientacaoInicialId)
            }
        }
    }
    var titulo by remember { mutableStateOf("") }
    var dataPrevista by remember { mutableStateOf(hojeIso()) }
    var descricao by remember { mutableStateOf("") }
    var tipoIdx by remember { mutableIntStateOf(0) }
    var etapaIdx by remember { mutableIntStateOf(0) }
    var entregaIdx by remember { mutableIntStateOf(0) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Nova tarefa") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("Orientandos:", fontWeight = FontWeight.SemiBold)
                orientacoes.filter { it.status == "ativa" }.forEach { o ->
                    val marcado = selecionadas.contains(o.id)
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                if (marcado) selecionadas.remove(o.id) else selecionadas.add(o.id)
                            },
                    ) {
                        Checkbox(
                            checked = marcado,
                            onCheckedChange = {
                                if (it) selecionadas.add(o.id) else selecionadas.remove(o.id)
                            },
                        )
                        Text(
                            "${o.orientandoNome} (${o.tituloProjeto})",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                OutlinedTextField(
                    value = titulo,
                    onValueChange = { titulo = it },
                    label = { Text("Título") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                CampoDataMaterial3(
                    rotulo = "Data prevista",
                    dataIso = dataPrevista,
                    onDataSelecionada = { dataPrevista = it },
                )
                SeletorDropdown("Tipo", AriadneCatalogos.tiposMarco.map { it.second }, tipoIdx) {
                    tipoIdx = it
                }
                SeletorDropdown("Etapa", AriadneCatalogos.etapasMarco.map { it.second }, etapaIdx) {
                    etapaIdx = it
                }
                SeletorDropdown(
                    "Entrega esperada",
                    AriadneCatalogos.entregasEsperadas.map { it.second },
                    entregaIdx,
                ) { entregaIdx = it }
                OutlinedTextField(
                    value = descricao,
                    onValueChange = { descricao = it },
                    label = { Text("Descrição (opcional)") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val idsArr = JSONArray().apply { selecionadas.forEach { put(it) } }
                    val payload = JSONObject()
                        .put("orientacao_ids", idsArr)
                        .put("titulo", titulo.trim())
                        .put("tipo", AriadneCatalogos.tiposMarco[tipoIdx].first)
                        .put("etapa", AriadneCatalogos.etapasMarco[etapaIdx].first)
                        .put("entrega_esperada", AriadneCatalogos.entregasEsperadas[entregaIdx].first)
                        .put("data_prevista", dataPrevista.trim())
                        .put("descricao", descricao.trim())
                    onSalvar(payload.toString())
                },
                enabled = selecionadas.isNotEmpty() &&
                    titulo.trim().isNotEmpty() &&
                    dataPrevista.trim().isNotEmpty(),
            ) { Text("Salvar offline") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}

@Composable
fun DialogoEditarMarco(
    marco: Marco,
    onDismiss: () -> Unit,
    onSalvar: (String) -> Unit,
) {
    var titulo by remember(marco.id) { mutableStateOf(marco.titulo) }
    var dataPrevista by remember(marco.id) { mutableStateOf(marco.dataPrevista) }
    var descricao by remember(marco.id) { mutableStateOf(marco.descricao ?: "") }
    var tipoIdx by remember(marco.id) {
        mutableIntStateOf(
            AriadneCatalogos.tiposMarco.indexOfFirst { it.first == marco.tipo }.coerceAtLeast(0)
        )
    }
    var etapaIdx by remember(marco.id) {
        mutableIntStateOf(
            AriadneCatalogos.etapasMarco.indexOfFirst { it.first == marco.etapa }.coerceAtLeast(0)
        )
    }
    var entregaIdx by remember(marco.id) {
        mutableIntStateOf(
            AriadneCatalogos.entregasEsperadas
                .indexOfFirst { it.first == (marco.entregaEsperada ?: "") }
                .coerceAtLeast(0)
        )
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Editar tarefa") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = titulo,
                    onValueChange = { titulo = it },
                    label = { Text("Título") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                CampoDataMaterial3(
                    rotulo = "Data prevista",
                    dataIso = dataPrevista,
                    onDataSelecionada = { dataPrevista = it },
                )
                SeletorDropdown("Tipo", AriadneCatalogos.tiposMarco.map { it.second }, tipoIdx) {
                    tipoIdx = it
                }
                SeletorDropdown("Etapa", AriadneCatalogos.etapasMarco.map { it.second }, etapaIdx) {
                    etapaIdx = it
                }
                SeletorDropdown(
                    "Entrega esperada",
                    AriadneCatalogos.entregasEsperadas.map { it.second },
                    entregaIdx,
                ) { entregaIdx = it }
                OutlinedTextField(
                    value = descricao,
                    onValueChange = { descricao = it },
                    label = { Text("Descrição (opcional)") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val payload = JSONObject()
                        .put("marco_id", marco.id)
                        .put("titulo", titulo.trim())
                        .put("tipo", AriadneCatalogos.tiposMarco[tipoIdx].first)
                        .put("etapa", AriadneCatalogos.etapasMarco[etapaIdx].first)
                        .put("entrega_esperada", AriadneCatalogos.entregasEsperadas[entregaIdx].first)
                        .put("data_prevista", dataPrevista.trim())
                        .put("descricao", descricao.trim())
                    onSalvar(payload.toString())
                },
                enabled = titulo.trim().isNotEmpty() && dataPrevista.trim().isNotEmpty(),
            ) { Text("Salvar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}

@Composable
fun DialogoAgendarReuniao(
    orientacoes: List<Orientacao>,
    orientacaoInicialId: Long? = null,
    onDismiss: () -> Unit,
    onSalvar: (String) -> Unit,
) {
    val selecionadas = remember(orientacaoInicialId) {
        mutableStateListOf<Long>().apply {
            if (orientacaoInicialId != null && orientacoes.any { it.id == orientacaoInicialId && it.status == "ativa" }) {
                add(orientacaoInicialId)
            }
        }
    }
    var dataReuniao by remember { mutableStateOf(hojeIso()) }
    var horaReuniao by remember { mutableStateOf("") }
    var linkReuniao by remember { mutableStateOf("") }
    var pauta by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Agendar reunião") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text("Convidados:", fontWeight = FontWeight.SemiBold)
                orientacoes.filter { it.status == "ativa" }.forEach { o ->
                    val marcado = selecionadas.contains(o.id)
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable {
                                if (marcado) selecionadas.remove(o.id) else selecionadas.add(o.id)
                            },
                    ) {
                        Checkbox(
                            checked = marcado,
                            onCheckedChange = {
                                if (it) selecionadas.add(o.id) else selecionadas.remove(o.id)
                            },
                        )
                        Text(
                            "${o.orientandoNome} (${o.tituloProjeto})",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
                CampoDataMaterial3(
                    rotulo = "Data da reunião",
                    dataIso = dataReuniao,
                    onDataSelecionada = { dataReuniao = it },
                )
                OutlinedTextField(
                    value = horaReuniao,
                    onValueChange = { horaReuniao = it },
                    label = { Text("Hora (HH:MM, opcional)") },
                    placeholder = { Text("14:30") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = linkReuniao,
                    onValueChange = { linkReuniao = it },
                    label = { Text("Link da sala (opcional)") },
                    placeholder = { Text("https://meet.google.com/...") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = pauta,
                    onValueChange = { pauta = it },
                    label = { Text("Pauta") },
                    minLines = 3,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val idsArr = JSONArray().apply { selecionadas.forEach { put(it) } }
                    val payload = JSONObject()
                        .put("orientacao_ids", idsArr)
                        .put("data_reuniao", dataReuniao.trim())
                        .put("hora_reuniao", horaReuniao.trim())
                        .put("link_reuniao", linkReuniao.trim())
                        .put("pauta", pauta.trim())
                    onSalvar(payload.toString())
                },
                enabled = selecionadas.isNotEmpty() &&
                    dataReuniao.trim().isNotEmpty() &&
                    pauta.trim().isNotEmpty(),
            ) { Text("Agendar offline") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}

@Composable
fun DialogoEditarAta(
    ata: Ata,
    onDismiss: () -> Unit,
    onSalvar: (String) -> Unit,
) {
    var pauta by remember(ata.id) { mutableStateOf(ata.pauta) }
    var deliberacoes by remember(ata.id) { mutableStateOf(ata.deliberacoes) }
    var link by remember(ata.id) { mutableStateOf(ata.linkReuniao ?: "") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Editar ata") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = pauta,
                    onValueChange = { pauta = it },
                    label = { Text("Pauta") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = deliberacoes,
                    onValueChange = { deliberacoes = it },
                    label = { Text("Deliberações") },
                    minLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = link,
                    onValueChange = { link = it },
                    label = { Text("Link da sala virtual") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val payload = JSONObject()
                        .put("ata_id", ata.id)
                        .put("pauta", pauta.trim())
                        .put("deliberacoes", deliberacoes)
                        .put("link_reuniao", link.trim())
                    onSalvar(payload.toString())
                },
                enabled = pauta.trim().isNotEmpty(),
            ) { Text("Salvar offline") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Fechar") } },
    )
}

@Composable
fun DialogoReagendar(
    ata: Ata,
    onDismiss: () -> Unit,
    onSalvar: (String) -> Unit,
) {
    var dataNova by remember(ata.id) { mutableStateOf(ata.dataReuniao) }
    var horaNova by remember(ata.id) { mutableStateOf(ata.horaReuniao ?: "") }
    var motivo by remember(ata.id) { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Reagendar reunião") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                CampoDataMaterial3(
                    rotulo = "Nova data",
                    dataIso = dataNova,
                    onDataSelecionada = { dataNova = it },
                )
                OutlinedTextField(
                    value = horaNova,
                    onValueChange = { horaNova = it },
                    label = { Text("Nova hora (HH:MM, opcional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = motivo,
                    onValueChange = { motivo = it },
                    label = { Text("Motivo (opcional)") },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val payload = JSONObject()
                        .put("ata_id", ata.id)
                        .put("data_nova", dataNova.trim())
                        .put("hora_nova", horaNova.trim())
                        .put("motivo", motivo.trim())
                    onSalvar(payload.toString())
                },
                enabled = dataNova.trim().isNotEmpty(),
            ) { Text("Reagendar") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Fechar") } },
    )
}

@Composable
fun DialogoNovoParecer(
    orientacoes: List<Orientacao>,
    documentos: List<Documento> = emptyList(),
    marcos: List<Marco> = emptyList(),
    orientacaoInicialId: Long? = null,
    onDismiss: () -> Unit,
    onSalvar: (String) -> Unit,
) {
    val cores = coresAriadne()
    val orientacaoFixa = remember(orientacaoInicialId, orientacoes) {
        orientacaoInicialId?.let { id -> orientacoes.firstOrNull { it.id == id } }
            ?: orientacoes.singleOrNull()
    }
    var orientacaoId by remember(orientacaoInicialId, orientacoes) {
        mutableStateOf(orientacaoFixa?.id ?: orientacoes.firstOrNull()?.id ?: 0L)
    }
    val idSelecionado = orientacaoFixa?.id ?: orientacaoId

    val opcoesVersao = remember(idSelecionado, documentos) {
        documentos
            .filter { it.orientacaoId == idSelecionado }
            .flatMap { doc -> doc.versoes.filter { it.temArquivo }.map { v -> doc to v } }
    }
    val marcosAbertos = remember(idSelecionado, marcos) {
        marcos.filter { it.orientacaoId == idSelecionado && it.status != "concluido" }
    }

    var versaoIdx by remember(idSelecionado, opcoesVersao) { mutableIntStateOf(0) }
    var tipoIdx by remember(idSelecionado, opcoesVersao) {
        mutableIntStateOf(if (opcoesVersao.isEmpty()) 0 else 1)
    }
    var marcoRefIdx by remember(idSelecionado, marcosAbertos) { mutableIntStateOf(0) }
    var resultadoIdx by remember { mutableIntStateOf(0) }
    var concluirMarco by remember(idSelecionado, versaoIdx) { mutableStateOf(true) }
    var conteudo by remember { mutableStateOf("") }

    val parSelecionado = opcoesVersao.getOrNull(versaoIdx)
    val marcoVinculadoTitulo = parSelecionado?.let { (doc, versao) ->
        versao.marcoAbertoTitulo ?: doc.marcoTitulo
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Emitir parecer") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (orientacaoFixa != null) {
                    Text(
                        text = "${orientacaoFixa.orientandoNome} · ${orientacaoFixa.tituloProjeto}",
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = cores.azulDestaque,
                    )
                } else {
                    Text("Vínculo:", fontWeight = FontWeight.SemiBold)
                    orientacoes.forEach { o ->
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { orientacaoId = o.id },
                        ) {
                            RadioButton(selected = orientacaoId == o.id, onClick = { orientacaoId = o.id })
                            Text(
                                "${o.orientandoNome} (${o.tituloProjeto})",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }

                if (opcoesVersao.isNotEmpty()) {
                    SeletorDropdown(
                        rotulo = "Documento / versão avaliada",
                        opcoes = opcoesVersao.map { (doc, v) ->
                            val dataEnv = v.enviadoEm?.let { " · ${formatarDataBr(it)}" } ?: ""
                            "${doc.titulo} (v${v.numeroVersao})$dataEnv" +
                                (v.nomeOriginal?.let { " · $it" } ?: "")
                        },
                        indiceAtual = versaoIdx.coerceIn(0, opcoesVersao.lastIndex),
                    ) { versaoIdx = it }

                    if (marcoVinculadoTitulo != null) {
                        Text(
                            text = "Marco vinculado: $marcoVinculadoTitulo",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = cores.azulDestaque,
                        )
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable { concluirMarco = !concluirMarco },
                        ) {
                            Checkbox(
                                checked = concluirMarco,
                                onCheckedChange = { concluirMarco = it },
                            )
                            Text(
                                text = "Concluir tarefa vinculada ao aprovar (ou devolver se reprovado)",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                } else {
                    Text(
                        text = "Nenhum documento enviado neste vínculo até o momento.",
                        style = MaterialTheme.typography.bodySmall,
                        color = cores.textoSecundario,
                    )
                    SeletorDropdown("Tipo", AriadneCatalogos.tiposParecer.map { it.second }, tipoIdx) {
                        tipoIdx = it
                    }
                    if (marcosAbertos.isNotEmpty()) {
                        val opcoesMarcos = listOf("(nenhum)") + marcosAbertos.map { it.titulo }
                        SeletorDropdown(
                            rotulo = "Marco de referência (opcional)",
                            opcoes = opcoesMarcos,
                            indiceAtual = marcoRefIdx.coerceIn(0, opcoesMarcos.lastIndex),
                        ) {
                            marcoRefIdx = it
                            if (it > 0) tipoIdx = 2 // marco
                        }
                    }
                }

                SeletorDropdown(
                    "Resultado",
                    AriadneCatalogos.resultadosParecer.map { it.second },
                    resultadoIdx,
                ) { resultadoIdx = it }
                OutlinedTextField(
                    value = conteudo,
                    onValueChange = { conteudo = it },
                    label = { Text("Texto do parecer") },
                    minLines = 4,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val payload = JSONObject()
                        .put("orientacao_id", idSelecionado)
                        .put("resultado", AriadneCatalogos.resultadosParecer[resultadoIdx].first)
                        .put("conteudo", conteudo.trim())
                    if (parSelecionado != null) {
                        payload
                            .put("tipo", "documento")
                            .put("versao_documento_id", parSelecionado.second.id)
                            .put("concluir_marco", concluirMarco)
                    } else {
                        payload.put("tipo", AriadneCatalogos.tiposParecer[tipoIdx].first)
                    }
                    onSalvar(payload.toString())
                },
                enabled = idSelecionado != 0L && conteudo.trim().isNotEmpty(),
            ) { Text("Emitir offline") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancelar") } },
    )
}

@Composable
fun DialogoFilaOffline(
    itens: List<ItemFila>,
    marcos: List<Marco>,
    onDescartar: (String) -> Unit,
    onDismiss: () -> Unit,
) {
    val cores = coresAriadne()
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Fila offline (${itens.size})") },
        text = {
            Column(
                modifier = Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (itens.isEmpty()) {
                    Text("Nenhuma operação pendente de envio.")
                } else {
                    Text(
                        text = "Estas alterações estão só no aparelho. Descartar desfaz a alteração " +
                            "aqui; sincronizar envia ao servidor.",
                        style = MaterialTheme.typography.bodySmall,
                        color = cores.textoSecundario,
                    )
                    itens.forEach { item ->
                        Card(
                            modifier = Modifier.fillMaxWidth(),
                            colors = CardDefaults.cardColors(containerColor = cores.superficieSuave),
                        ) {
                            Column(modifier = Modifier.padding(10.dp)) {
                                Text(
                                    text = item.descricao(marcos),
                                    fontWeight = FontWeight.SemiBold,
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                                Text(
                                    text = formatarDataHoraBr(item.criadaEm),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = cores.textoSecundario,
                                )
                                Spacer(Modifier.height(4.dp))
                                TextButton(onClick = { onDescartar(item.opId) }) {
                                    Text("Descartar e desfazer", color = cores.vermelhoTexto)
                                }
                            }
                        }
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Fechar") } },
    )
}
