package br.edu.ariadne.mobile.ui

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import br.edu.ariadne.mobile.core.AriadneCatalogos
import br.edu.ariadne.mobile.core.Ata
import br.edu.ariadne.mobile.core.Documento
import br.edu.ariadne.mobile.core.ExtratoPdfGenerator
import br.edu.ariadne.mobile.core.Marco
import br.edu.ariadne.mobile.core.Orientacao
import br.edu.ariadne.mobile.core.Parecer
import br.edu.ariadne.mobile.core.Usuario
import br.edu.ariadne.mobile.core.VersaoDocumento
import br.edu.ariadne.mobile.core.ehPassadaOuHoje
import br.edu.ariadne.mobile.core.estaAtrasado
import br.edu.ariadne.mobile.core.formatarDataBr
import br.edu.ariadne.mobile.core.formatarDataHoraBr
import br.edu.ariadne.mobile.core.hojeIso
import br.edu.ariadne.mobile.ui.theme.PaletaSemantica
import br.edu.ariadne.mobile.ui.theme.coresAriadne
import java.time.LocalDate
import java.time.YearMonth
import java.time.temporal.ChronoUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

enum class FiltroStatusTarefa(val rotulo: String) {
    PENDENTES("Em aberto"),
    AGUARDAM_VOCE("Aguardam você"),
    DEVOLVIDAS("Devolvidas"),
    CONCLUIDAS("Concluídas"),
    TODAS("Todas"),
}

enum class FiltroReuniao(val rotulo: String) {
    PROXIMAS("Próximas"),
    SEM_ATA("Sem ata / Rascunho"),
    FINALIZADAS("Finalizadas"),
    CANCELADAS("Canceladas"),
    TODAS("Todas"),
}

@Composable
fun TelaLogin(
    urlInicial: String,
    carregando: Boolean,
    mensagem: String?,
    erro: String?,
    onEntrar: (url: String, email: String, senha: String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val cores = coresAriadne()
    var url by remember(urlInicial) { mutableStateOf(urlInicial) }
    var email by remember { mutableStateOf("") }
    var senha by remember { mutableStateOf("") }
    var editarServidor by remember { mutableStateOf(false) }

    Box(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
        contentAlignment = Alignment.TopCenter,
    ) {
        Column(
            modifier = Modifier
                .widthIn(max = 440.dp)
                .fillMaxWidth()
                .padding(top = 16.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            BrasaoAriadne(size = 64.dp, fundo = cores.cabecalhoFundo)
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(
                    text = "ARIADNE Móvel",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = cores.azulDestaque,
                )
                Text(
                    text = "Ambiente de Revisão, Integração, Acompanhamento Discente e Normatização de Estudos",
                    style = MaterialTheme.typography.bodySmall,
                    color = cores.textoSecundario,
                    textAlign = TextAlign.Center,
                )
            }

            CartaoAriadne {
                Text(
                    text = "Acessar conta",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = cores.textoPrincipal,
                )
                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text("E-mail") },
                    placeholder = { Text("nome@instituicao.br") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = senha,
                    onValueChange = { senha = it },
                    label = { Text("Senha") },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                    modifier = Modifier.fillMaxWidth(),
                )

                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { editarServidor = !editarServidor }
                        .padding(vertical = 2.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = if (editarServidor) {
                            "Ocultar servidor"
                        } else {
                            "Servidor: ${url.removePrefix("https://").removePrefix("http://")}"
                        },
                        style = MaterialTheme.typography.labelMedium,
                        color = cores.azulDestaque,
                    )
                    Text(
                        text = if (editarServidor) "▲" else "Alterar",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = cores.azulDestaque,
                    )
                }

                if (editarServidor) {
                    OutlinedTextField(
                        value = url,
                        onValueChange = { url = it },
                        label = { Text("Endereço do servidor (PythonAnywhere)") },
                        placeholder = { Text("https://orientacao.pythonanywhere.com") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                Button(
                    onClick = { onEntrar(url, email, senha) },
                    enabled = !carregando,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (carregando) "Conectando e sincronizando..." else "Entrar e sincronizar")
                }

                Text(
                    text = "Após a primeira sincronização, suas tarefas, reuniões e pareceres ficam salvos no aparelho para uso offline.",
                    style = MaterialTheme.typography.bodySmall,
                    color = cores.textoSecundario,
                )
            }

            if (!mensagem.isNullOrBlank()) BannerMensagem(mensagem, erro = false)
            if (!erro.isNullOrBlank()) BannerMensagem(erro, erro = true)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AbaPainel(
    usuario: Usuario,
    orientacoes: List<Orientacao>,
    marcos: List<Marco>,
    atas: List<Ata>,
    onEnfileirar: (acao: String, dadosJson: String) -> Unit,
    onAbrirNovaTarefa: () -> Unit,
    onAbrirAgendarReuniao: () -> Unit,
    onAbrirNovoParecer: () -> Unit,
    onIrParaTarefas: (FiltroStatusTarefa) -> Unit,
    onIrParaReunioes: (FiltroReuniao) -> Unit,
    onAbrirMarco: (Long) -> Unit,
) {
    val cores = coresAriadne()
    val ehGestor = usuario.papel == "orientador" || usuario.papel == "admin"
    val ehOrientador = usuario.papel == "orientador"
    val hoje = remember(marcos, atas) { hojeIso() }
    val orientacoesPorId = remember(orientacoes) { orientacoes.associateBy { it.id } }

    var marcoDevolver by remember { mutableStateOf<Marco?>(null) }
    var ataEditar by remember { mutableStateOf<Ata?>(null) }
    val uriHandler = LocalUriHandler.current

    if (ehGestor) {
        val entregasConfirmar = remember(marcos, orientacoes, usuario) {
            marcos.filter { m ->
                val o = orientacoesPorId[m.orientacaoId]
                m.id > 0 &&
                    m.aguardando == "orientador" &&
                    (usuario.papel == "admin" || o?.orientadorId == usuario.id)
            }.sortedBy { it.dataPrevista }
        }
        val reunioesSemAta = remember(atas, hoje) {
            atas.filter { it.status == "rascunho" && it.ehPassadaOuHoje(hoje) }
        }
        val proximasReunioes = remember(atas, hoje) {
            atas.filter { it.status == "rascunho" && !it.ehPassadaOuHoje(hoje) }
                .sortedBy { it.dataReuniao }
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Text(
                    text = "Acesso rápido",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = cores.textoSecundario,
                )
                Spacer(Modifier.height(6.dp))
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    HubBotao("+ Nova tarefa", onClick = onAbrirNovaTarefa)
                    if (ehOrientador) {
                        HubBotao("+ Agendar reunião", onClick = onAbrirAgendarReuniao)
                    }
                    HubBotao("+ Emitir parecer", onClick = onAbrirNovoParecer)
                }
            }

            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    KpiCard(
                        valor = entregasConfirmar.size,
                        rotulo = "Entregas a confirmar",
                        corAcento = if (entregasConfirmar.isNotEmpty()) cores.ambarAcento else cores.verdeAcento,
                        onClick = { onIrParaTarefas(FiltroStatusTarefa.AGUARDAM_VOCE) },
                        modifier = Modifier.weight(1f),
                    )
                    KpiCard(
                        valor = reunioesSemAta.size,
                        rotulo = "Reuniões sem ata",
                        corAcento = if (reunioesSemAta.isNotEmpty()) cores.vermelhoAcento else cores.verdeAcento,
                        onClick = { onIrParaReunioes(FiltroReuniao.SEM_ATA) },
                        modifier = Modifier.weight(1f),
                    )
                    KpiCard(
                        valor = proximasReunioes.size,
                        rotulo = "Próximas reuniões",
                        corAcento = cores.azulDestaque,
                        onClick = { onIrParaReunioes(FiltroReuniao.PROXIMAS) },
                        modifier = Modifier.weight(1f),
                    )
                }
            }

            if (entregasConfirmar.isEmpty() && reunioesSemAta.isEmpty() && proximasReunioes.isEmpty()) {
                item {
                    BannerMensagem("Nenhuma pendência em aberto no momento.", erro = false, sucesso = true)
                }
            }

            if (entregasConfirmar.isNotEmpty()) {
                item {
                    CabecalhoSecao(
                        titulo = "Entregas aguardando sua confirmação",
                        contagem = entregasConfirmar.size,
                    )
                }
                items(entregasConfirmar, key = { "conf-${it.id}" }) { m ->
                    val o = orientacoesPorId[m.orientacaoId]
                    CartaoAriadne(accentColor = cores.ambarAcento, onClick = { onAbrirMarco(m.id) }) {
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Text(
                                text = m.titulo,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.SemiBold,
                            )
                            if (m.estaAtrasado(hoje)) {
                                Etiqueta("atrasada", cores.vermelhoFundo, cores.vermelhoTexto)
                            }
                        }
                        if (o != null) {
                            Text(
                                text = "${o.orientandoNome} · ${o.tituloProjeto}",
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.Medium,
                                color = cores.azulDestaque,
                            )
                        }
                        Text(
                            text = "Prazo: ${formatarDataBr(m.dataPrevista)} · ${AriadneCatalogos.rotuloEtapa(m.etapa)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = cores.textoSecundario,
                        )
                        if (!m.notaConclusao.isNullOrBlank()) {
                            NotaDestacada(
                                titulo = "Nota do orientando",
                                texto = m.notaConclusao,
                                fundo = cores.infoFundo,
                                corBorda = cores.azulDestaque,
                                corTexto = cores.infoTexto,
                            )
                        }
                        FlowRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalArrangement = Arrangement.spacedBy(6.dp),
                        ) {
                            Button(
                                onClick = {
                                    onEnfileirar(
                                        "confirmar_conclusao_marco",
                                        JSONObject().put("marco_id", m.id).toString(),
                                    )
                                },
                            ) { Text("Confirmar") }
                            OutlinedButton(onClick = { marcoDevolver = m }) {
                                Text("Devolver")
                            }
                            TextButton(onClick = { onAbrirMarco(m.id) }) { Text("Ver entrega ›") }
                        }
                    }
                }
            }

            if (reunioesSemAta.isNotEmpty()) {
                item {
                    CabecalhoSecao(
                        titulo = "Reuniões realizadas sem ata / em redação",
                        contagem = reunioesSemAta.size,
                    )
                }
                items(reunioesSemAta, key = { "semata-${it.id}" }) { a ->
                    val nomes = a.orientacaoIds.mapNotNull { orientacoesPorId[it]?.orientandoNome }
                    CartaoAriadne(accentColor = cores.vermelhoAcento) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = "${formatarDataBr(a.dataReuniao)}${a.horaReuniao?.let { " às $it" } ?: ""}",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                            )
                            Etiqueta(
                                texto = if (a.deliberacoes.isBlank()) "aguardando ata" else "em redação",
                                fundo = if (a.deliberacoes.isBlank()) cores.vermelhoFundo else cores.ambarFundo,
                                corTexto = if (a.deliberacoes.isBlank()) cores.vermelhoTexto else cores.ambarTexto,
                            )
                        }
                        if (nomes.isNotEmpty()) {
                            Text(
                                text = "Participantes: ${nomes.joinToString(", ")}",
                                style = MaterialTheme.typography.bodySmall,
                                color = cores.textoSecundario,
                            )
                        }
                        Text(
                            text = "Pauta: ${a.pauta}",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        if (a.id > 0) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Button(onClick = { ataEditar = a }) {
                                    Text(if (a.deliberacoes.isBlank()) "Redigir ata" else "Editar ata")
                                }
                                if (a.deliberacoes.isNotBlank()) {
                                    OutlinedButton(
                                        onClick = {
                                            onEnfileirar(
                                                "finalizar_ata",
                                                JSONObject().put("ata_id", a.id).toString(),
                                            )
                                        },
                                    ) { Text("Finalizar") }
                                }
                            }
                        }
                    }
                }
            }

            if (proximasReunioes.isNotEmpty()) {
                item {
                    CabecalhoSecao(
                        titulo = "Próximas reuniões",
                        contagem = proximasReunioes.size,
                    )
                }
                items(proximasReunioes, key = { "prox-${it.id}" }) { a ->
                    val nomes = a.orientacaoIds.mapNotNull { orientacoesPorId[it]?.orientandoNome }
                    CartaoAriadne(accentColor = cores.azulDestaque) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = "${formatarDataBr(a.dataReuniao)}${a.horaReuniao?.let { " às $it" } ?: " (hora a definir)"}",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                            )
                            Etiqueta(a.tipo, cores.infoFundo, cores.infoTexto)
                        }
                        if (nomes.isNotEmpty()) {
                            Text(
                                text = "Convidados: ${nomes.joinToString(", ")}",
                                style = MaterialTheme.typography.bodySmall,
                                color = cores.textoSecundario,
                            )
                        }
                        Text(text = "Pauta: ${a.pauta}", style = MaterialTheme.typography.bodyMedium)
                        if (!a.linkReuniao.isNullOrBlank()) {
                            OutlinedButton(
                                onClick = { runCatching { uriHandler.openUri(a.linkReuniao) } },
                            ) { Text("Abrir sala virtual") }
                        }
                    }
                }
            }
        }
    } else {
        // Perfil Orientando
        val ativas = remember(orientacoes) {
            orientacoes.filter { it.status == "ativa" }.ifEmpty { orientacoes }
        }
        val devolvidas = remember(marcos) {
            marcos.filter { it.aguardando == "orientando_revisao" }.sortedBy { it.dataPrevista }
        }
        val aFazer = remember(marcos) {
            marcos.filter { it.aguardando == "orientando" }.sortedBy { it.dataPrevista }
        }
        val aguardandoOrientador = remember(marcos) {
            marcos.filter { it.aguardando == "orientador" }.sortedBy { it.dataPrevista }
        }
        val proximasReunioes = remember(atas, hoje) {
            atas.filter { it.status == "rascunho" && it.dataReuniao >= hoje }.sortedBy { it.dataReuniao }
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            items(ativas, key = { "minha-${it.id}" }) { o ->
                val doVinculo = marcos.filter { it.orientacaoId == o.id }
                val concluidas = doVinculo.count { it.status == "concluido" }
                CartaoAriadne(accentColor = cores.azulDestaque) {
                    FlowRow(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Etiqueta(
                            AriadneCatalogos.rotuloModalidade(o.modalidade),
                            cores.infoFundo,
                            cores.infoTexto,
                        )
                        Etiqueta(o.status, cores.superficieSuave, cores.azulDestaque)
                    }
                    Text(
                        text = o.tituloProjeto,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                    Text(
                        text = "Orientador: ${o.orientadorNome}",
                        style = MaterialTheme.typography.bodySmall,
                        color = cores.textoSecundario,
                    )
                    BarraProgressoCronograma(concluidas = concluidas, total = doVinculo.size)
                }
            }

            if (devolvidas.isEmpty() && aFazer.isEmpty() && aguardandoOrientador.isEmpty() && proximasReunioes.isEmpty()) {
                item {
                    BannerMensagem("Você não possui pendências no momento.", erro = false, sucesso = true)
                }
            }

            if (devolvidas.isNotEmpty()) {
                item {
                    CabecalhoSecao(
                        titulo = "Devolvidas para você corrigir",
                        contagem = devolvidas.size,
                        subtitulo = "Confira as observações do orientador e reenvie a sinalização.",
                    )
                }
                items(devolvidas, key = { "dev-${it.id}" }) { m ->
                    CartaoMarco(
                        marco = m,
                        orientacao = orientacoesPorId[m.orientacaoId],
                        usuario = usuario,
                        hoje = hoje,
                        onEnfileirar = onEnfileirar,
                        onDevolver = { marcoDevolver = it },
                        onEditar = {},
                        onAbrir = { onAbrirMarco(it.id) },
                    )
                }
            }

            if (aFazer.isNotEmpty()) {
                item {
                    CabecalhoSecao(
                        titulo = "Próximas tarefas a entregar",
                        contagem = aFazer.size,
                    )
                }
                items(aFazer, key = { "faz-${it.id}" }) { m ->
                    CartaoMarco(
                        marco = m,
                        orientacao = orientacoesPorId[m.orientacaoId],
                        usuario = usuario,
                        hoje = hoje,
                        onEnfileirar = onEnfileirar,
                        onDevolver = { marcoDevolver = it },
                        onEditar = {},
                        onAbrir = { onAbrirMarco(it.id) },
                    )
                }
            }

            if (proximasReunioes.isNotEmpty()) {
                item {
                    CabecalhoSecao(titulo = "Próximas reuniões", contagem = proximasReunioes.size)
                }
                items(proximasReunioes, key = { "alprox-${it.id}" }) { a ->
                    CartaoAriadne(accentColor = cores.azulDestaque) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            Text(
                                text = "${formatarDataBr(a.dataReuniao)}${a.horaReuniao?.let { " às $it" } ?: ""}",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                            )
                            if (a.dataReuniao == hoje) {
                                Etiqueta("Hoje", cores.ambarFundo, cores.ambarTexto)
                            }
                        }
                        Text(text = "Pauta: ${a.pauta}", style = MaterialTheme.typography.bodyMedium)
                        if (!a.linkReuniao.isNullOrBlank()) {
                            OutlinedButton(
                                onClick = { runCatching { uriHandler.openUri(a.linkReuniao) } },
                            ) { Text("Entrar na sala virtual") }
                        }
                    }
                }
            }

            if (aguardandoOrientador.isNotEmpty()) {
                item {
                    CabecalhoSecao(
                        titulo = "Aguardando avaliação do orientador",
                        contagem = aguardandoOrientador.size,
                    )
                }
                items(aguardandoOrientador, key = { "ag-${it.id}" }) { m ->
                    CartaoMarco(
                        marco = m,
                        orientacao = orientacoesPorId[m.orientacaoId],
                        usuario = usuario,
                        hoje = hoje,
                        onEnfileirar = onEnfileirar,
                        onDevolver = {},
                        onEditar = {},
                        onAbrir = { onAbrirMarco(it.id) },
                    )
                }
            }
        }
    }

    marcoDevolver?.let { m ->
        DialogoTextoSimples(
            titulo = "Devolver para revisão",
            rotulo = "O que precisa corrigir (opcional)",
            textoBotao = "Devolver",
            obrigatorio = false,
            onDismiss = { marcoDevolver = null },
            onConfirmar = { nota ->
                val payload = JSONObject().put("marco_id", m.id).put("nota", nota)
                marcoDevolver = null
                onEnfileirar("devolver_marco", payload.toString())
            },
        )
    }

    ataEditar?.let { a ->
        DialogoEditarAta(
            ata = a,
            onDismiss = { ataEditar = null },
            onSalvar = { dados ->
                ataEditar = null
                onEnfileirar("atualizar_ata", dados)
            },
        )
    }
}

@Composable
private fun HubBotao(texto: String, onClick: () -> Unit) {
    val cores = coresAriadne()
    Surface(
        modifier = Modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(8.dp),
        color = cores.fundoCartao,
        border = BorderStroke(1.dp, cores.azulDestaque.copy(alpha = 0.55f)),
    ) {
        Text(
            text = texto,
            color = cores.azulDestaque,
            fontWeight = FontWeight.SemiBold,
            style = MaterialTheme.typography.labelLarge,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
        )
    }
}

@Composable
fun AbaTarefas(
    usuario: Usuario,
    orientacoes: List<Orientacao>,
    marcos: List<Marco>,
    atas: List<Ata>,
    filtroOrientacao: Long?,
    onMudarFiltroOrientacao: (Long?) -> Unit,
    filtroStatusInicial: FiltroStatusTarefa,
    modoCalendario: Boolean,
    onMudarModoCalendario: (Boolean) -> Unit,
    onEnfileirar: (acao: String, dadosJson: String) -> Unit,
    onAbrirMarco: (Long) -> Unit,
) {
    val cores = coresAriadne()
    var filtroStatus by remember(filtroStatusInicial) { mutableStateOf(filtroStatusInicial) }
    var marcoDevolver by remember { mutableStateOf<Marco?>(null) }
    var marcoEditar by remember { mutableStateOf<Marco?>(null) }
    val hoje = remember(marcos) { hojeIso() }
    val hojeData = remember(hoje) { LocalDate.parse(hoje) }
    var mesCalendario by remember { mutableStateOf(YearMonth.from(hojeData)) }
    var diaSelecionado by remember { mutableStateOf<LocalDate?>(hojeData) }
    val orientacoesPorId = remember(orientacoes) { orientacoes.associateBy { it.id } }

    val filtrados = remember(marcos, filtroOrientacao, filtroStatus) {
        marcos.filter { m ->
            (filtroOrientacao == null || m.orientacaoId == filtroOrientacao) &&
                when (filtroStatus) {
                    FiltroStatusTarefa.PENDENTES -> m.status != "concluido"
                    FiltroStatusTarefa.AGUARDAM_VOCE ->
                        if (usuario.papel == "orientando") {
                            m.aguardando == "orientando" || m.aguardando == "orientando_revisao"
                        } else {
                            m.aguardando == "orientador"
                        }
                    FiltroStatusTarefa.DEVOLVIDAS -> m.aguardando == "orientando_revisao"
                    FiltroStatusTarefa.CONCLUIDAS -> m.status == "concluido"
                    FiltroStatusTarefa.TODAS -> true
                }
        }
    }

    val porEtapa = remember(filtrados) {
        AriadneCatalogos.etapasMarco.mapNotNull { (codigo, _) ->
            val grupo = filtrados.filter { it.etapa == codigo }.sortedBy { it.dataPrevista }
            if (grupo.isEmpty()) null else codigo to grupo
        }
    }

    // Calendário: pontos por dia, coloridos pelo status, e reuniões (anel).
    val marcasCalendario = remember(filtrados, atas, filtroOrientacao, hoje, cores) {
        val mapa = mutableMapOf<String, MutableList<MarcaCalendario>>()
        filtrados.forEach { m ->
            val cor = when {
                m.status == "concluido" -> cores.verdeAcento
                m.aguardando == "orientando_revisao" || m.estaAtrasado(hoje) -> cores.vermelhoAcento
                m.aguardando == "orientador" -> cores.ambarAcento
                else -> cores.azulDestaque
            }
            mapa.getOrPut(m.dataPrevista.take(10)) { mutableListOf() }.add(MarcaCalendario(cor))
        }
        atas.filter { a ->
            a.status != "cancelada" &&
                (filtroOrientacao == null || a.orientacaoIds.contains(filtroOrientacao))
        }.forEach { a ->
            mapa.getOrPut(a.dataReuniao.take(10)) { mutableListOf() }
                .add(MarcaCalendario(cores.textoSecundario, reuniao = true))
        }
        mapa
    }
    val doDia = remember(filtrados, diaSelecionado) {
        val alvo = diaSelecionado?.toString()
        filtrados.filter { it.dataPrevista.take(10) == alvo }
    }
    val reunioesDoDia = remember(atas, diaSelecionado, filtroOrientacao) {
        val alvo = diaSelecionado?.toString()
        atas.filter { a ->
            a.status != "cancelada" && a.dataReuniao.take(10) == alvo &&
                (filtroOrientacao == null || a.orientacaoIds.contains(filtroOrientacao))
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 84.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip(
                    selected = !modoCalendario,
                    onClick = { onMudarModoCalendario(false) },
                    label = { Text("Lista") },
                    leadingIcon = { IconeTarefas(cores.azulDestaque, Modifier.size(16.dp)) },
                )
                FilterChip(
                    selected = modoCalendario,
                    onClick = { onMudarModoCalendario(true) },
                    label = { Text("Calendário") },
                    leadingIcon = { IconeCalendario(cores.azulDestaque, Modifier.size(16.dp)) },
                )
            }
        }
        if (orientacoes.size > 1) {
            item {
                Row(
                    modifier = Modifier.horizontalScroll(rememberScrollState()),
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    FilterChip(
                        selected = filtroOrientacao == null,
                        onClick = { onMudarFiltroOrientacao(null) },
                        label = { Text("Todos") },
                    )
                    orientacoes.forEach { o ->
                        FilterChip(
                            selected = filtroOrientacao == o.id,
                            onClick = {
                                onMudarFiltroOrientacao(if (filtroOrientacao == o.id) null else o.id)
                            },
                            label = {
                                Text(
                                    if (usuario.papel == "orientando") o.tituloProjeto else o.orientandoNome
                                )
                            },
                        )
                    }
                }
            }
        }

        item {
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                FiltroStatusTarefa.entries.forEach { f ->
                    FilterChip(
                        selected = filtroStatus == f,
                        onClick = { filtroStatus = f },
                        label = { Text(f.rotulo) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = cores.infoFundo,
                            selectedLabelColor = cores.azulDestaque,
                        ),
                    )
                }
            }
        }

        if (modoCalendario) {
            item(key = "calendario") {
                CalendarioPrazos(
                    mes = mesCalendario,
                    hoje = hojeData,
                    selecionado = diaSelecionado,
                    marcas = marcasCalendario,
                    onMudarMes = { mesCalendario = it },
                    onSelecionarDia = { diaSelecionado = if (diaSelecionado == it) null else it },
                )
            }
            diaSelecionado?.let { dia ->
                item(key = "dia-cab") {
                    CabecalhoSecao(
                        titulo = "Em ${formatarDataBr(dia.toString())}",
                        contagem = doDia.size + reunioesDoDia.size,
                    )
                }
                if (doDia.isEmpty() && reunioesDoDia.isEmpty()) {
                    item(key = "dia-vazio") {
                        Text(
                            text = "Nada marcado para este dia com o filtro atual.",
                            style = MaterialTheme.typography.bodySmall,
                            color = cores.textoSecundario,
                        )
                    }
                }
                items(reunioesDoDia, key = { "dia-ata-${it.id}" }) { a ->
                    CartaoAriadne(accentColor = cores.textoSecundario) {
                        Text(
                            text = "Reunião${a.horaReuniao?.let { " às $it" } ?: ""}",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            text = "Pauta: ${a.pauta}",
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 3,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
                items(doDia, key = { "dia-${it.id}" }) { m ->
                    CartaoMarco(
                        marco = m,
                        orientacao = orientacoesPorId[m.orientacaoId],
                        usuario = usuario,
                        hoje = hoje,
                        onEnfileirar = onEnfileirar,
                        onDevolver = { marcoDevolver = it },
                        onEditar = { marcoEditar = it },
                        onAbrir = { onAbrirMarco(it.id) },
                    )
                }
            }
        } else if (porEtapa.isEmpty()) {
            item {
                CartaoAriadne {
                    Text(
                        text = "Nenhuma tarefa encontrada para o filtro selecionado.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = cores.textoSecundario,
                    )
                }
            }
        } else {
            porEtapa.forEach { (codigoEtapa, grupo) ->
                item(key = "etapa-$codigoEtapa") {
                    CabecalhoSecao(
                        titulo = AriadneCatalogos.rotuloEtapa(codigoEtapa),
                        contagem = grupo.size,
                    )
                }
                items(grupo, key = { it.id }) { m ->
                    CartaoMarco(
                        marco = m,
                        orientacao = orientacoesPorId[m.orientacaoId],
                        usuario = usuario,
                        hoje = hoje,
                        onEnfileirar = onEnfileirar,
                        onDevolver = { marcoDevolver = it },
                        onEditar = { marcoEditar = it },
                        onAbrir = { onAbrirMarco(it.id) },
                    )
                }
            }
        }
    }

    marcoDevolver?.let { m ->
        DialogoTextoSimples(
            titulo = "Devolver para revisão",
            rotulo = "O que precisa corrigir (opcional)",
            textoBotao = "Devolver",
            obrigatorio = false,
            onDismiss = { marcoDevolver = null },
            onConfirmar = { nota ->
                val payload = JSONObject().put("marco_id", m.id).put("nota", nota)
                marcoDevolver = null
                onEnfileirar("devolver_marco", payload.toString())
            },
        )
    }

    marcoEditar?.let { m ->
        DialogoEditarMarco(
            marco = m,
            onDismiss = { marcoEditar = null },
            onSalvar = { dados ->
                marcoEditar = null
                onEnfileirar("editar_marco", dados)
            },
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun CartaoMarco(
    marco: Marco,
    orientacao: Orientacao?,
    usuario: Usuario,
    hoje: String,
    onEnfileirar: (String, String) -> Unit,
    onDevolver: (Marco) -> Unit,
    onEditar: (Marco) -> Unit,
    onAbrir: (Marco) -> Unit,
) {
    val cores = coresAriadne()
    val atrasado = marco.estaAtrasado(hoje)
    val podeSinalizar = orientacao?.orientandoId == usuario.id &&
        marco.id > 0 &&
        marco.status != "concluido" &&
        !marco.conclusaoSinalizada
    val podeGerir = marco.id > 0 &&
        (usuario.papel == "admin" || orientacao?.orientadorId == usuario.id)

    val corAcento = when {
        marco.status == "concluido" -> cores.verdeAcento
        marco.aguardando == "orientando_revisao" || atrasado -> cores.vermelhoAcento
        marco.aguardando == "orientador" -> cores.ambarAcento
        else -> cores.azulDestaque
    }

    CartaoAriadne(accentColor = corAcento, onClick = { onAbrir(marco) }) {
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = marco.titulo,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = cores.textoPrincipal,
            )
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
            if (atrasado) {
                Etiqueta("atrasada", cores.vermelhoFundo, cores.vermelhoTexto)
            }
        }

        val infoOrientacao = orientacao?.let {
            if (usuario.papel == "orientando") it.tituloProjeto else "${it.orientandoNome} · ${it.tituloProjeto}"
        }
        val prazoTxt = "Prazo: ${formatarDataBr(marco.dataPrevista)}"
        val tipoTxt = AriadneCatalogos.rotuloTipoMarco(marco.tipo)
        Text(
            text = listOfNotNull(infoOrientacao, prazoTxt, tipoTxt).joinToString(" · "),
            style = MaterialTheme.typography.bodySmall,
            color = cores.textoSecundario,
        )

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
                maxLines = 5,
            )
        }
        if (!marco.notaDevolucao.isNullOrBlank() && marco.aguardando == "orientando_revisao") {
            NotaDestacada(
                titulo = "Devolução do orientador",
                texto = marco.notaDevolucao,
                fundo = cores.vermelhoFundo,
                corBorda = cores.vermelhoAcento,
                corTexto = cores.vermelhoTexto,
            )
        }

        // Ações do orientando ficam na tela da tarefa: lá o envio do documento
        // e a sinalização têm rótulo, explicação e confirmação.
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            if (podeSinalizar) {
                Button(onClick = { onAbrir(marco) }) {
                    Text(
                        if (marco.entregaEsperada == "ato") {
                            "Abrir e sinalizar conclusão"
                        } else {
                            "Abrir e entregar"
                        }
                    )
                }
            } else {
                TextButton(onClick = { onAbrir(marco) }) { Text("Abrir tarefa ›") }
            }
            if (podeGerir && marco.status != "concluido") {
                Button(
                    onClick = {
                        onEnfileirar(
                            "confirmar_conclusao_marco",
                            JSONObject().put("marco_id", marco.id).toString(),
                        )
                    },
                ) { Text("Confirmar") }
                if (marco.conclusaoSinalizada) {
                    OutlinedButton(onClick = { onDevolver(marco) }) {
                        Text("Devolver")
                    }
                }
            }
            if (podeGerir) {
                OutlinedButton(onClick = { onEditar(marco) }) { Text("Editar") }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AbaReunioes(
    usuario: Usuario,
    orientacoes: List<Orientacao>,
    atas: List<Ata>,
    filtroOrientacao: Long?,
    filtroInicial: FiltroReuniao,
    onEnfileirar: (acao: String, dadosJson: String) -> Unit,
) {
    val cores = coresAriadne()
    var filtro by remember(filtroInicial) { mutableStateOf(filtroInicial) }
    var ataSelecionadaId by remember { mutableStateOf<Long?>(null) }
    val hoje = remember(atas) { hojeIso() }
    val orientacoesPorId = remember(orientacoes) { orientacoes.associateBy { it.id } }
    val uriHandler = LocalUriHandler.current

    val base = remember(atas, filtroOrientacao) {
        atas.filter { a -> filtroOrientacao == null || a.orientacaoIds.contains(filtroOrientacao) }
    }
    val filtradas = remember(base, filtro, hoje) {
        base.filter { a ->
            when (filtro) {
                FiltroReuniao.PROXIMAS -> a.status == "rascunho" && !a.ehPassadaOuHoje(hoje)
                FiltroReuniao.SEM_ATA -> a.status == "rascunho" && a.ehPassadaOuHoje(hoje)
                FiltroReuniao.FINALIZADAS -> a.status == "finalizada"
                FiltroReuniao.CANCELADAS -> a.status == "cancelada"
                FiltroReuniao.TODAS -> true
            }
        }
    }

    var ataEditar by remember { mutableStateOf<Ata?>(null) }
    var ataReagendar by remember { mutableStateOf<Ata?>(null) }
    var ataCancelar by remember { mutableStateOf<Ata?>(null) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 84.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        item {
            Row(
                modifier = Modifier.horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                FiltroReuniao.entries.forEach { f ->
                    val qtd = when (f) {
                        FiltroReuniao.PROXIMAS -> base.count { it.status == "rascunho" && !it.ehPassadaOuHoje(hoje) }
                        FiltroReuniao.SEM_ATA -> base.count { it.status == "rascunho" && it.ehPassadaOuHoje(hoje) }
                        FiltroReuniao.FINALIZADAS -> base.count { it.status == "finalizada" }
                        FiltroReuniao.CANCELADAS -> base.count { it.status == "cancelada" }
                        FiltroReuniao.TODAS -> base.size
                    }
                    FilterChip(
                        selected = filtro == f,
                        onClick = { filtro = f },
                        label = { Text("${f.rotulo} ($qtd)") },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = cores.infoFundo,
                            selectedLabelColor = cores.azulDestaque,
                        ),
                    )
                }
            }
        }

        if (filtradas.isEmpty()) {
            item {
                CartaoAriadne {
                    Text(
                        text = "Nenhuma reunião nesta categoria.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = cores.textoSecundario,
                    )
                }
            }
        } else {
            items(filtradas, key = { it.id }) { a ->
                val selecionada = ataSelecionadaId == a.id
                val podeGerir = usuario.papel == "admin" || a.orientadorId == usuario.id
                val corAcento = when (a.status) {
                    "finalizada" -> cores.verdeAcento
                    "cancelada" -> cores.vermelhoAcento
                    else -> if (a.ehPassadaOuHoje(hoje)) cores.ambarAcento else cores.azulDestaque
                }
                val nomesParticipantes = a.orientacaoIds
                    .mapNotNull { orientacoesPorId[it]?.orientandoNome }
                    .joinToString(", ")

                CartaoAriadne(
                    modifier = Modifier.animateContentSize(),
                    accentColor = corAcento,
                    onClick = {
                        ataSelecionadaId = if (selecionada) null else a.id
                    },
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        FlowRow(
                            modifier = Modifier.weight(1f),
                            horizontalArrangement = Arrangement.spacedBy(6.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            val hora = a.horaReuniao?.let { " · $it" } ?: ""
                            Text(
                                text = "${formatarDataBr(a.dataReuniao)}$hora",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.Bold,
                                color = cores.textoPrincipal,
                            )
                            Etiqueta(a.tipo, cores.infoFundo, cores.infoTexto)
                            if (a.id < 0) Etiqueta("Pendente", cores.ambarFundo, cores.ambarTexto)
                            val (bg, fg) = when (a.status) {
                                "finalizada" -> cores.verdeFundo to cores.verdeTexto
                                "cancelada" -> cores.vermelhoFundo to cores.vermelhoTexto
                                else -> cores.ambarFundo to cores.ambarTexto
                            }
                            Etiqueta(a.status, bg, fg)
                        }
                        Text(
                            text = if (selecionada) "▲" else "▼",
                            style = MaterialTheme.typography.labelLarge,
                            color = cores.azulDestaque,
                            modifier = Modifier.padding(start = 8.dp),
                        )
                    }

                    if (!selecionada) {
                        if (nomesParticipantes.isNotEmpty()) {
                            Text(
                                text = nomesParticipantes,
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.Medium,
                                color = cores.azulDestaque,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                        Text(
                            text = a.pauta,
                            style = MaterialTheme.typography.bodySmall,
                            color = cores.textoSecundario,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    } else {
                        HorizontalDivider(color = cores.borda)

                        NotaDestacada(
                            titulo = "Pauta",
                            texto = a.pauta,
                            fundo = cores.superficieSuave,
                            corBorda = cores.borda,
                            corTexto = cores.azulDestaque,
                        )

                        if (a.deliberacoes.isNotBlank()) {
                            NotaDestacada(
                                titulo = "Deliberações",
                                texto = a.deliberacoes,
                                fundo = cores.fundoCartao,
                                corBorda = cores.borda,
                                corTexto = cores.textoSecundario,
                            )
                        }

                        if (!a.linkReuniao.isNullOrBlank()) {
                            OutlinedButton(
                                onClick = { runCatching { uriHandler.openUri(a.linkReuniao) } },
                            ) { Text("Abrir sala virtual") }
                        }

                        if (!a.motivoCancelamento.isNullOrBlank()) {
                            NotaDestacada(
                                titulo = "Motivo do cancelamento",
                                texto = a.motivoCancelamento,
                                fundo = cores.vermelhoFundo,
                                corBorda = cores.vermelhoAcento,
                                corTexto = cores.vermelhoTexto,
                            )
                        }

                        HorizontalDivider(color = cores.borda)
                        Text(
                            text = "Participantes e presenças",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.Bold,
                            color = cores.textoSecundario,
                        )
                        a.participacoes.forEach { p ->
                            val rotulo = orientacoesPorId[p.orientacaoId]
                                ?.let { "${it.orientandoNome} (${it.tituloProjeto})" }
                                ?: "Vínculo #${p.orientacaoId}"
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Text(
                                    text = rotulo,
                                    style = MaterialTheme.typography.bodySmall,
                                    modifier = Modifier.weight(1f),
                                )
                                val (pBg, pFg) = coresPresenca(p.presenca, cores)
                                Etiqueta(p.presenca, pBg, pFg)
                            }
                            if (a.id > 0 && a.status != "cancelada" && podeGerir) {
                                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    TextButton(
                                        onClick = {
                                            val payload = JSONObject()
                                                .put("ata_id", a.id)
                                                .put("orientacao_id", p.orientacaoId)
                                                .put("presenca", "presente")
                                            onEnfileirar("registrar_presenca", payload.toString())
                                        },
                                    ) { Text("Marcar presente") }
                                    TextButton(
                                        onClick = {
                                            val payload = JSONObject()
                                                .put("ata_id", a.id)
                                                .put("orientacao_id", p.orientacaoId)
                                                .put("presenca", "ausente")
                                            onEnfileirar("registrar_presenca", payload.toString())
                                        },
                                    ) { Text("Marcar ausente", color = cores.vermelhoTexto) }
                                }
                            }
                        }

                        if (a.id > 0 && a.status == "rascunho" && podeGerir) {
                            HorizontalDivider(color = cores.borda)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                OutlinedButton(onClick = { ataEditar = a }) { Text("Editar ata") }
                                OutlinedButton(onClick = { ataReagendar = a }) { Text("Reagendar") }
                                OutlinedButton(
                                    onClick = { ataCancelar = a },
                                    colors = ButtonDefaults.outlinedButtonColors(contentColor = cores.vermelhoTexto),
                                ) { Text("Cancelar") }
                                if (a.deliberacoes.isNotBlank()) {
                                    Button(
                                        onClick = {
                                            onEnfileirar(
                                                "finalizar_ata",
                                                JSONObject().put("ata_id", a.id).toString(),
                                            )
                                        },
                                    ) { Text("Finalizar ata") }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    ataEditar?.let { a ->
        DialogoEditarAta(
            ata = a,
            onDismiss = { ataEditar = null },
            onSalvar = { dados ->
                ataEditar = null
                onEnfileirar("atualizar_ata", dados)
            },
        )
    }
    ataReagendar?.let { a ->
        DialogoReagendar(
            ata = a,
            onDismiss = { ataReagendar = null },
            onSalvar = { dados ->
                ataReagendar = null
                onEnfileirar("reagendar_ata", dados)
            },
        )
    }
    ataCancelar?.let { a ->
        DialogoTextoSimples(
            titulo = "Cancelar reunião",
            rotulo = "Motivo do cancelamento",
            textoBotao = "Confirmar cancelamento",
            obrigatorio = true,
            onDismiss = { ataCancelar = null },
            onConfirmar = { motivo ->
                val payload = JSONObject().put("ata_id", a.id).put("motivo", motivo)
                ataCancelar = null
                onEnfileirar("cancelar_reuniao", payload.toString())
            },
        )
    }
}

private fun coresPresenca(presenca: String, cores: PaletaSemantica): Pair<Color, Color> =
    when (presenca) {
        "presente" -> cores.verdeFundo to cores.verdeTexto
        "ausente" -> cores.vermelhoFundo to cores.vermelhoTexto
        else -> cores.superficieSuave to cores.textoSecundario
    }

private fun coresResultadoParecer(
    resultado: String,
    cores: PaletaSemantica,
): Triple<Color, Color, Color> =
    when (resultado) {
        "aprovado" -> Triple(cores.verdeFundo, cores.verdeTexto, cores.verdeAcento)
        "aprovado_com_ressalvas" -> Triple(cores.ambarFundo, cores.ambarTexto, cores.ambarAcento)
        else -> Triple(cores.vermelhoFundo, cores.vermelhoTexto, cores.vermelhoAcento)
    }

private fun rotuloPrazoVinculo(
    dataFimPrevista: String?,
    hoje: String,
    cores: PaletaSemantica,
): Pair<String, Color>? {
    val fimStr = dataFimPrevista?.takeIf { it.isNotBlank() } ?: return null
    val dias = runCatching {
        ChronoUnit.DAYS.between(LocalDate.parse(hoje), LocalDate.parse(fimStr))
    }.getOrNull() ?: return null
    return when {
        dias > 30 -> "$dias dia(s) restante(s)" to cores.verdeTexto
        dias > 0 -> "$dias dia(s) restante(s)" to cores.ambarTexto
        dias == 0L -> "Prazo previsto termina hoje" to cores.ambarTexto
        else -> "Prazo previsto vencido há ${-dias} dia(s)" to cores.vermelhoTexto
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun AbaOrientandosEPareceres(
    usuario: Usuario,
    orientacoes: List<Orientacao>,
    marcos: List<Marco>,
    documentos: List<Documento> = emptyList(),
    atas: List<Ata>,
    pareceres: List<Parecer>,
    filtroOrientacao: Long?,
    onVerTarefasDaOrientacao: (Long) -> Unit,
    onEmitirParecerParaOrientacao: (Long) -> Unit,
) {
    val cores = coresAriadne()
    val ehGestor = usuario.papel == "orientador" || usuario.papel == "admin"
    val hoje = remember(marcos, atas) { hojeIso() }
    val orientacoesPorId = remember(orientacoes) { orientacoes.associateBy { it.id } }
    val versaoInfoPorId = remember(documentos) {
        buildMap {
            documentos.forEach { d ->
                d.versoes.forEach { v -> put(v.id, d to v) }
            }
        }
    }
    val vigentes = remember(orientacoes) {
        orientacoes.filter { it.status == "ativa" }.ifEmpty { orientacoes }
    }
    var orientacaoSelecionadaId by remember { mutableStateOf<Long?>(null) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(bottom = 84.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        if (ehGestor) {
            item {
                CabecalhoSecao(
                    titulo = "Orientandos vigentes",
                    contagem = vigentes.size,
                )
            }

            if (vigentes.isEmpty()) {
                item {
                    CartaoAriadne {
                        Text(
                            text = "Nenhum orientando vigente vinculado.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = cores.textoSecundario,
                        )
                    }
                }
            } else {
                items(vigentes, key = { "ori-${it.id}" }) { o ->
                    val selecionada = orientacaoSelecionadaId == o.id
                    val doVinculo = marcos.filter { it.orientacaoId == o.id }
                    val concluidas = doVinculo.count { it.status == "concluido" }
                    val atrasadas = doVinculo.count { it.estaAtrasado(hoje) }
                    val docsDoVinculo = if (selecionada) {
                        documentos.filter { it.orientacaoId == o.id }
                    } else {
                        emptyList()
                    }
                    val atasDoVinculo = if (selecionada) {
                        atas.filter { it.orientacaoIds.contains(o.id) }.sortedByDescending { it.dataReuniao }
                    } else {
                        emptyList()
                    }
                    val pareceresDoVinculo = if (selecionada) {
                        pareceres.filter { it.orientacaoId == o.id }
                    } else {
                        emptyList()
                    }

                    CartaoAriadne(
                        modifier = Modifier.animateContentSize(),
                        accentColor = if (atrasadas > 0) cores.ambarAcento else cores.azulDestaque,
                        onClick = {
                            orientacaoSelecionadaId = if (selecionada) null else o.id
                        },
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            FlowRow(
                                modifier = Modifier.weight(1f),
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                verticalArrangement = Arrangement.spacedBy(4.dp),
                            ) {
                                Text(
                                    text = o.orientandoNome,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.Bold,
                                    color = cores.textoPrincipal,
                                )
                                Etiqueta(
                                    AriadneCatalogos.rotuloModalidade(o.modalidade),
                                    cores.infoFundo,
                                    cores.infoTexto,
                                )
                                if (atrasadas > 0) {
                                    Etiqueta(
                                        "$atrasadas atrasada(s)",
                                        cores.vermelhoFundo,
                                        cores.vermelhoTexto,
                                    )
                                }
                            }
                            Text(
                                text = if (selecionada) "▲" else "▼",
                                style = MaterialTheme.typography.labelLarge,
                                color = cores.azulDestaque,
                                modifier = Modifier.padding(start = 8.dp),
                            )
                        }

                        Text(
                            text = o.tituloProjeto,
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.Medium,
                            color = cores.textoPrincipal,
                        )
                        BarraProgressoCronograma(concluidas = concluidas, total = doVinculo.size)

                        if (selecionada) {
                            ExtratoOrientando(
                                usuario = usuario,
                                orientacao = o,
                                marcos = doVinculo,
                                concluidas = concluidas,
                                atrasadas = atrasadas,
                                documentos = docsDoVinculo,
                                atas = atasDoVinculo,
                                pareceres = pareceresDoVinculo,
                                versaoInfoPorId = versaoInfoPorId,
                                hoje = hoje,
                                onVerTarefasDaOrientacao = onVerTarefasDaOrientacao,
                                onEmitirParecerParaOrientacao = onEmitirParecerParaOrientacao,
                            )
                        }
                    }
                }
            }
        } else {
            item {
                CabecalhoSecao(
                    titulo = "Pareceres recebidos",
                    contagem = pareceres.size,
                )
            }

            val filtrados = pareceres.filter { p ->
                filtroOrientacao == null || p.orientacaoId == filtroOrientacao
            }
            if (filtrados.isEmpty()) {
                item {
                    CartaoAriadne {
                        Text(
                            text = "Nenhum parecer emitido.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = cores.textoSecundario,
                        )
                    }
                }
            } else {
                items(filtrados, key = { "par-${it.id}" }) { p ->
                    val (_, _, acento) = coresResultadoParecer(p.resultado, cores)
                    CartaoAriadne(accentColor = acento) {
                        ConteudoParecerDetalhado(
                            parecer = p,
                            orientacao = orientacoesPorId[p.orientacaoId],
                            versaoInfoPorId = versaoInfoPorId,
                            ampliado = true,
                            mostrarProjeto = true,
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ConteudoParecerDetalhado(
    parecer: Parecer,
    orientacao: Orientacao?,
    versaoInfoPorId: Map<Long, Pair<Documento, VersaoDocumento>>,
    ampliado: Boolean,
    mostrarProjeto: Boolean = false,
) {
    val cores = coresAriadne()
    val (bg, fg, _) = coresResultadoParecer(parecer.resultado, cores)
    val infoLocal = parecer.versaoDocumentoId?.let { versaoInfoPorId[it] }
    val docTitulo = parecer.documentoTitulo ?: infoLocal?.first?.titulo
    val numVersao = parecer.numeroVersao ?: infoLocal?.second?.numeroVersao
    val nomeArquivo = parecer.nomeArquivo ?: infoLocal?.second?.nomeOriginal
    val marcoTitulo = parecer.marcoTitulo
        ?: infoLocal?.first?.marcoTitulo
        ?: infoLocal?.second?.marcoAbertoTitulo

    if (mostrarProjeto && orientacao != null) {
        Text(
            text = orientacao.tituloProjeto,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            color = cores.textoPrincipal,
        )
    }

    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Etiqueta(AriadneCatalogos.rotuloResultadoParecer(parecer.resultado), bg, fg)
        Etiqueta(
            parecer.tipo.replaceFirstChar { it.uppercase() },
            cores.infoFundo,
            cores.infoTexto,
        )
        if (parecer.id < 0) {
            Etiqueta("Pendente de envio", cores.ambarFundo, cores.ambarTexto)
        }
    }

    if (!docTitulo.isNullOrBlank()) {
        val rotuloDoc = buildString {
            append("Documento avaliado: $docTitulo")
            if (numVersao != null) append(" (v$numVersao)")
            if (!nomeArquivo.isNullOrBlank()) append(" · $nomeArquivo")
        }
        Text(
            text = rotuloDoc,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium,
            color = cores.azulDestaque,
        )
    }

    if (!marcoTitulo.isNullOrBlank()) {
        Text(
            text = "Marco vinculado: $marcoTitulo",
            style = MaterialTheme.typography.labelMedium,
            color = cores.textoPrincipal,
        )
    }

    val metaEmissor = buildList {
        parecer.emissorNome?.takeIf { it.isNotBlank() }?.let { add("Emitido por $it") }
        add(formatarDataHoraBr(parecer.emitidoEm))
    }.joinToString(" · ")
    Text(
        text = metaEmissor,
        style = MaterialTheme.typography.labelSmall,
        color = cores.textoSecundario,
    )

    Text(
        text = parecer.conteudo,
        style = MaterialTheme.typography.bodySmall,
        color = cores.textoPrincipal,
        maxLines = if (ampliado) Int.MAX_VALUE else 4,
        overflow = TextOverflow.Ellipsis,
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ExtratoOrientando(
    usuario: Usuario,
    orientacao: Orientacao,
    marcos: List<Marco>,
    concluidas: Int,
    atrasadas: Int,
    documentos: List<Documento>,
    atas: List<Ata>,
    pareceres: List<Parecer>,
    versaoInfoPorId: Map<Long, Pair<Documento, VersaoDocumento>>,
    hoje: String,
    onVerTarefasDaOrientacao: (Long) -> Unit,
    onEmitirParecerParaOrientacao: (Long) -> Unit,
) {
    val cores = coresAriadne()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var ampliado by remember(orientacao.id) { mutableStateOf(false) }
    var gerandoPdf by remember(orientacao.id) { mutableStateOf(false) }
    var avisoPdf by remember(orientacao.id) { mutableStateOf<Pair<String, Boolean>?>(null) }

    val prazo = rotuloPrazoVinculo(orientacao.dataFimPrevista, hoje, cores)
    val totalVersoes = documentos.sumOf { it.versoes.size }
    val presencas = atas.count { ata ->
        ata.participacoes.any { it.orientacaoId == orientacao.id && it.presenca == "presente" }
    }
    val docsPorMarcoId = remember(documentos) {
        documentos.filter { it.marcoId != null }.groupBy { it.marcoId!! }
    }
    val pareceresPorVersaoId = remember(pareceres) {
        pareceres.filter { it.versaoDocumentoId != null }.groupBy { it.versaoDocumentoId!! }
    }
    val marcosPorId = remember(marcos) { marcos.associateBy { it.id } }
    val marcosOrdenados = remember(marcos) {
        marcos.sortedWith(
            compareBy<Marco> { it.status == "concluido" }.thenBy { it.etapa }.thenBy { it.dataPrevista }
        )
    }

    HorizontalDivider(color = cores.borda)

    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Button(
            onClick = {
                if (gerandoPdf) return@Button
                gerandoPdf = true
                avisoPdf = null
                scope.launch {
                    val res = withContext(Dispatchers.IO) {
                        ExtratoPdfGenerator.gerarESalvarExtrato(
                            context = context,
                            orientacao = orientacao,
                            marcos = marcos,
                            documentos = documentos,
                            atas = atas,
                            pareceres = pareceres,
                        )
                    }
                    gerandoPdf = false
                    res.onSuccess { pdf ->
                        avisoPdf = "PDF salvo em ${pdf.localDescricao}" to false
                        ExtratoPdfGenerator.abrirPdf(context, pdf.uri)
                    }.onFailure { exc ->
                        avisoPdf = (exc.message ?: "Falha ao gerar o PDF do extrato.") to true
                    }
                }
            },
            enabled = !gerandoPdf,
        ) {
            Text(if (gerandoPdf) "Gerando PDF..." else "Baixar Extrato PDF")
        }

        OutlinedButton(onClick = { ampliado = !ampliado }) {
            Text(if (ampliado) "Modo resumido" else "Ampliar informações")
        }
    }

    avisoPdf?.let { (texto, ehErro) ->
        BannerMensagem(texto = texto, erro = ehErro, sucesso = !ehErro)
    }

    Surface(
        shape = RoundedCornerShape(8.dp),
        color = cores.superficieSuave,
        border = BorderStroke(1.dp, cores.borda),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier.padding(10.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = "Resumo do vínculo",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = cores.azulDestaque,
            )
            Text(
                text = "Orientador: ${orientacao.orientadorNome} · Status: ${orientacao.status}",
                style = MaterialTheme.typography.bodySmall,
                color = cores.textoPrincipal,
            )
            Text(
                text = "Início: ${formatarDataBr(orientacao.dataInicio)} · Término previsto: ${
                    orientacao.dataFimPrevista?.let { formatarDataBr(it) } ?: "não definido"
                }",
                style = MaterialTheme.typography.bodySmall,
                color = cores.textoSecundario,
            )
            if (prazo != null) {
                Text(
                    text = prazo.first,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = prazo.second,
                )
            }
            Text(
                text = "Marcos: $concluidas/${marcos.size} ($atrasadas atrasada(s)) · " +
                    "Docs: ${documentos.size} ($totalVersoes versão(ões)) · " +
                    "Reuniões: ${atas.size} ($presencas presença(s)) · Pareceres: ${pareceres.size}",
                style = MaterialTheme.typography.labelSmall,
                color = cores.textoSecundario,
            )
        }
    }

    // Cronograma
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "Cronograma (${marcos.size})",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
            color = cores.azulDestaque,
        )
        TextButton(onClick = { onVerTarefasDaOrientacao(orientacao.id) }) {
            Text("Abrir no Cronograma")
        }
    }

    if (marcosOrdenados.isEmpty()) {
        Text(
            text = "Nenhuma tarefa cadastrada neste vínculo.",
            style = MaterialTheme.typography.bodySmall,
            color = cores.textoSecundario,
        )
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            marcosOrdenados.forEach { m ->
                val atrasado = m.estaAtrasado(hoje)
                val (rotulo, mBg, mFg) = when {
                    m.status == "concluido" -> Triple("concluída", cores.verdeFundo, cores.verdeTexto)
                    atrasado -> Triple("atrasada", cores.vermelhoFundo, cores.vermelhoTexto)
                    m.aguardando == "orientador" ->
                        Triple(AriadneCatalogos.rotuloAguardando(m.aguardando), cores.ambarFundo, cores.ambarTexto)
                    m.aguardando == "orientando_revisao" ->
                        Triple(AriadneCatalogos.rotuloAguardando(m.aguardando), cores.vermelhoFundo, cores.vermelhoTexto)
                    else ->
                        Triple(AriadneCatalogos.rotuloAguardando(m.aguardando), cores.infoFundo, cores.infoTexto)
                }
                val docsMarco = docsPorMarcoId[m.id].orEmpty()
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = cores.superficieSuave,
                    border = BorderStroke(1.dp, cores.borda),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(9.dp),
                        verticalArrangement = Arrangement.spacedBy(3.dp),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = m.titulo,
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.SemiBold,
                                color = cores.textoPrincipal,
                                modifier = Modifier.weight(1f).padding(end = 8.dp),
                            )
                            Etiqueta(rotulo, mBg, mFg)
                        }
                        val subInfo = buildList {
                            add(AriadneCatalogos.rotuloEtapa(m.etapa))
                            add(AriadneCatalogos.rotuloTipoMarco(m.tipo))
                            AriadneCatalogos.rotuloEntregaEsperada(m.entregaEsperada)?.let { add(it) }
                        }.joinToString(" · ")
                        Text(
                            text = subInfo,
                            style = MaterialTheme.typography.labelSmall,
                            color = cores.textoSecundario,
                        )
                        val prazoLine = buildString {
                            append("Prazo: ${formatarDataBr(m.dataPrevista)}")
                            m.dataConclusao?.takeIf { it.isNotBlank() }?.let {
                                append(" · Concluída em ${formatarDataBr(it)}")
                            }
                        }
                        Text(
                            text = prazoLine,
                            style = MaterialTheme.typography.labelSmall,
                            color = cores.textoSecundario,
                        )
                        if (docsMarco.isNotEmpty()) {
                            Text(
                                text = "Documentos: ${docsMarco.joinToString(", ") { it.titulo }}",
                                style = MaterialTheme.typography.labelSmall,
                                fontWeight = FontWeight.Medium,
                                color = cores.azulDestaque,
                            )
                        }
                        if (ampliado) {
                            if (!m.descricao.isNullOrBlank()) {
                                TextoComLinks(
                                    texto = m.descricao,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = cores.textoPrincipal,
                                )
                            }
                            if (!m.notaConclusao.isNullOrBlank()) {
                                NotaDestacada(
                                    titulo = "Nota do orientando",
                                    texto = m.notaConclusao,
                                    fundo = cores.infoFundo,
                                    corBorda = cores.azulDestaque,
                                    corTexto = cores.infoTexto,
                                )
                            }
                            if (!m.notaDevolucao.isNullOrBlank()) {
                                NotaDestacada(
                                    titulo = "Devolução do orientador",
                                    texto = m.notaDevolucao,
                                    fundo = cores.vermelhoFundo,
                                    corBorda = cores.vermelhoAcento,
                                    corTexto = cores.vermelhoTexto,
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    HorizontalDivider(color = cores.borda)

    // Documentos entregues e versões
    Text(
        text = "Documentos entregues e versões (${documentos.size})",
        style = MaterialTheme.typography.labelLarge,
        fontWeight = FontWeight.Bold,
        color = cores.azulDestaque,
    )
    if (documentos.isEmpty()) {
        Text(
            text = "Nenhum documento enviado neste vínculo.",
            style = MaterialTheme.typography.bodySmall,
            color = cores.textoSecundario,
        )
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            documentos.forEach { d ->
                val versoesExibidas = if (ampliado) d.versoes else d.versoes.take(1)
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = cores.superficieSuave,
                    border = BorderStroke(1.dp, cores.borda),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(10.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = d.titulo,
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.Bold,
                                color = cores.textoPrincipal,
                                modifier = Modifier.weight(1f).padding(end = 8.dp),
                            )
                            Etiqueta(
                                "${d.versoes.size} versão(ões)",
                                cores.infoFundo,
                                cores.infoTexto,
                            )
                        }
                        if (!d.marcoTitulo.isNullOrBlank()) {
                            Text(
                                text = "Marco vinculado: ${d.marcoTitulo}",
                                style = MaterialTheme.typography.labelSmall,
                                color = cores.azulDestaque,
                            )
                        }
                        if (versoesExibidas.isEmpty()) {
                            Text(
                                text = "Sem versões enviadas.",
                                style = MaterialTheme.typography.labelSmall,
                                color = cores.textoSecundario,
                            )
                        } else {
                            versoesExibidas.forEach { v ->
                                val natRotulo = when (v.natureza) {
                                    "devolucao" -> "devolução"
                                    "entrega" -> "entrega"
                                    else -> "registro"
                                }
                                val pareceresDaVersao = pareceresPorVersaoId[v.id].orEmpty()
                                FlowRow(
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                    verticalArrangement = Arrangement.spacedBy(3.dp),
                                ) {
                                    Text(
                                        text = "v${v.numeroVersao} · ${
                                            v.enviadoEm?.let(::formatarDataHoraBr) ?: "—"
                                        } · ${v.remetenteNome.ifBlank { "Participante" }} ($natRotulo)",
                                        style = MaterialTheme.typography.labelSmall,
                                        fontWeight = FontWeight.Medium,
                                        color = cores.textoPrincipal,
                                    )
                                    pareceresDaVersao.forEach { p ->
                                        val (pBg, pFg, _) = coresResultadoParecer(p.resultado, cores)
                                        Etiqueta(
                                            "Parecer: ${AriadneCatalogos.rotuloResultadoParecer(p.resultado)}",
                                            pBg,
                                            pFg,
                                        )
                                    }
                                }
                                val nomeArq = v.nomeOriginal
                                    ?: if (v.temArquivo) "Arquivo anexado" else "só comentário"
                                Text(
                                    text = "Arquivo: $nomeArq",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = cores.textoSecundario,
                                )
                                if (!v.comentario.isNullOrBlank()) {
                                    Text(
                                        text = v.comentario,
                                        style = MaterialTheme.typography.bodySmall,
                                        color = cores.textoSecundario,
                                        maxLines = if (ampliado) Int.MAX_VALUE else 1,
                                        overflow = TextOverflow.Ellipsis,
                                    )
                                }
                            }
                            if (!ampliado && d.versoes.size > 1) {
                                Text(
                                    text = "+ ${d.versoes.size - 1} versão(ões) anterior(es) (use Ampliar informações)",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = cores.azulDestaque,
                                )
                            }
                        }
                    }
                }
            }
        }
    }

    HorizontalDivider(color = cores.borda)

    // Pareceres emitidos
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "Pareceres emitidos (${pareceres.size})",
            style = MaterialTheme.typography.labelLarge,
            fontWeight = FontWeight.Bold,
            color = cores.azulDestaque,
        )
        if (usuario.papel == "admin" || orientacao.orientadorId == usuario.id) {
            OutlinedButton(onClick = { onEmitirParecerParaOrientacao(orientacao.id) }) {
                Text("+ Emitir parecer")
            }
        }
    }

    if (pareceres.isEmpty()) {
        Text(
            text = "Nenhum parecer emitido para este vínculo.",
            style = MaterialTheme.typography.bodySmall,
            color = cores.textoSecundario,
        )
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            pareceres.forEach { p ->
                val (_, _, acento) = coresResultadoParecer(p.resultado, cores)
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = cores.superficieSuave,
                    border = BorderStroke(1.dp, acento.copy(alpha = 0.45f)),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(10.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        ConteudoParecerDetalhado(
                            parecer = p,
                            orientacao = orientacao,
                            versaoInfoPorId = versaoInfoPorId,
                            ampliado = ampliado,
                            mostrarProjeto = false,
                        )
                    }
                }
            }
        }
    }

    HorizontalDivider(color = cores.borda)

    // Reuniões e presenças
    Text(
        text = "Reuniões e presenças (${atas.size})",
        style = MaterialTheme.typography.labelLarge,
        fontWeight = FontWeight.Bold,
        color = cores.azulDestaque,
    )
    if (atas.isEmpty()) {
        Text(
            text = "Nenhuma reunião registrada para este vínculo.",
            style = MaterialTheme.typography.bodySmall,
            color = cores.textoSecundario,
        )
    } else {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            atas.forEach { a ->
                val presenca = a.participacoes
                    .firstOrNull { it.orientacaoId == orientacao.id }
                    ?.presenca ?: "pendente"
                val (pBg, pFg) = coresPresenca(presenca, cores)
                val marcosDiscutidos = a.marcoIds.mapNotNull { marcosPorId[it]?.titulo }
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = cores.superficieSuave,
                    border = BorderStroke(1.dp, cores.borda),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Column(
                        modifier = Modifier.padding(9.dp),
                        verticalArrangement = Arrangement.spacedBy(3.dp),
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                text = "${formatarDataBr(a.dataReuniao)}${a.horaReuniao?.let { " às $it" } ?: ""} · ${a.tipo} · ${a.status}",
                                style = MaterialTheme.typography.bodySmall,
                                fontWeight = FontWeight.SemiBold,
                                color = cores.textoPrincipal,
                                modifier = Modifier.weight(1f).padding(end = 8.dp),
                            )
                            Etiqueta(presenca, pBg, pFg)
                        }
                        if (marcosDiscutidos.isNotEmpty()) {
                            Text(
                                text = "Marcos discutidos: ${marcosDiscutidos.joinToString(", ")}",
                                style = MaterialTheme.typography.labelSmall,
                                color = cores.azulDestaque,
                            )
                        }
                        Text(
                            text = "Pauta: ${a.pauta}",
                            style = MaterialTheme.typography.bodySmall,
                            color = cores.textoSecundario,
                            maxLines = if (ampliado) Int.MAX_VALUE else 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                        if (ampliado && a.deliberacoes.isNotBlank()) {
                            Text(
                                text = "Deliberações: ${a.deliberacoes}",
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
