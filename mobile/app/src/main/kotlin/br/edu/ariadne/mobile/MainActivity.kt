package br.edu.ariadne.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import br.edu.ariadne.mobile.core.AriadneCatalogos
import br.edu.ariadne.mobile.core.AriadneRustBridge
import br.edu.ariadne.mobile.core.EstadoApp
import br.edu.ariadne.mobile.core.formatarDataHoraBr
import br.edu.ariadne.mobile.core.parseRespostaPonte
import br.edu.ariadne.mobile.ui.AbaOrientandosEPareceres
import br.edu.ariadne.mobile.ui.AbaPainel
import br.edu.ariadne.mobile.ui.AbaReunioes
import br.edu.ariadne.mobile.ui.AbaTarefas
import br.edu.ariadne.mobile.ui.BannerMensagem
import br.edu.ariadne.mobile.ui.BrasaoAriadne
import br.edu.ariadne.mobile.ui.DialogoAgendarReuniao
import br.edu.ariadne.mobile.ui.DialogoFilaOffline
import br.edu.ariadne.mobile.ui.DialogoNovaTarefa
import br.edu.ariadne.mobile.ui.DialogoNovoParecer
import br.edu.ariadne.mobile.ui.Etiqueta
import br.edu.ariadne.mobile.ui.FiltroReuniao
import br.edu.ariadne.mobile.ui.FiltroStatusTarefa
import br.edu.ariadne.mobile.ui.IconeCalendario
import br.edu.ariadne.mobile.ui.IconeDocumento
import br.edu.ariadne.mobile.ui.IconePainel
import br.edu.ariadne.mobile.ui.IconeSincronizar
import br.edu.ariadne.mobile.ui.IconeTarefas
import br.edu.ariadne.mobile.ui.TelaDetalheMarco
import br.edu.ariadne.mobile.ui.TelaLogin
import br.edu.ariadne.mobile.ui.theme.ARIADNETheme
import br.edu.ariadne.mobile.ui.theme.AzulAriadne
import br.edu.ariadne.mobile.ui.theme.DouradoAriadne
import br.edu.ariadne.mobile.ui.theme.DouradoTexto
import br.edu.ariadne.mobile.ui.theme.coresAriadne
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(android.graphics.Color.TRANSPARENT),
        )
        val dbPath = File(filesDir, "ariadne.db").absolutePath
        setContent {
            ARIADNETheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    AriadneAppRoot(dbPath)
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AriadneAppRoot(dbPath: String) {
    val cores = coresAriadne()
    val scope = rememberCoroutineScope()
    var estado by remember { mutableStateOf(EstadoApp()) }
    var carregando by remember { mutableStateOf(false) }
    var mensagemStatus by remember { mutableStateOf<String?>(null) }
    var erroStatus by remember { mutableStateOf<String?>(null) }

    var abaSelecionada by remember { mutableIntStateOf(0) }
    var filtroOrientacao by remember { mutableStateOf<Long?>(null) }
    var filtroStatusTarefa by remember { mutableStateOf(FiltroStatusTarefa.PENDENTES) }
    var filtroReuniao by remember { mutableStateOf(FiltroReuniao.PROXIMAS) }

    var abrirNovaTarefa by remember { mutableStateOf(false) }
    var abrirAgendarReuniao by remember { mutableStateOf(false) }
    var parecerOrientacaoAlvo by remember { mutableStateOf<Long?>(null) }
    var abrirNovoParecer by remember { mutableStateOf(false) }
    var abrirFila by remember { mutableStateOf(false) }
    var confirmarSaida by remember { mutableStateOf(false) }
    var marcoAbertoId by remember { mutableStateOf<Long?>(null) }
    var modoCalendario by remember { mutableStateOf(false) }

    fun irParaAba(aba: Int) {
        marcoAbertoId = null
        abaSelecionada = aba
    }

    fun executarNoNucleo(chamada: () -> String) {
        if (carregando) return
        carregando = true
        erroStatus = null
        scope.launch {
            val resposta = withContext(Dispatchers.IO) {
                runCatching { parseRespostaPonte(chamada()) }
            }
            carregando = false
            resposta.onSuccess { res ->
                res.estado?.let { estado = it }
                mensagemStatus = res.mensagem
                erroStatus = res.erro
            }.onFailure { exc ->
                erroStatus = exc.message ?: "Erro ao comunicar com o núcleo Rust."
            }
        }
    }

    LaunchedEffect(Unit) {
        executarNoNucleo { AriadneRustBridge.estadoLocal(dbPath) }
    }

    val usuario = estado.usuario
    val ehOrientadorOuAdmin = usuario?.papel == "orientador" || usuario?.papel == "admin"
    val ehOrientador = usuario?.papel == "orientador"

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            Column {
                TopAppBar(
                    title = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            BrasaoAriadne(size = 30.dp)
                            Text(
                                text = "ARIADNE",
                                fontWeight = FontWeight.Bold,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                            )
                        }
                    },
                    actions = {
                        if (estado.autenticado) {
                            TextButton(
                                onClick = { executarNoNucleo { AriadneRustBridge.sincronizar(dbPath) } },
                                enabled = !carregando,
                            ) {
                                IconeSincronizar(cor = Color.White)
                                Spacer(Modifier.width(5.dp))
                                Text("Sincronizar", color = Color.White)
                            }
                            TextButton(
                                onClick = {
                                    if (estado.itensFila.isNotEmpty()) {
                                        confirmarSaida = true
                                    } else {
                                        irParaAba(0)
                                        filtroOrientacao = null
                                        executarNoNucleo { AriadneRustBridge.encerrarSessao(dbPath) }
                                    }
                                },
                            ) {
                                Text("Sair", color = Color.White.copy(alpha = 0.88f))
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = cores.cabecalhoFundo,
                        titleContentColor = Color.White,
                    ),
                )

                if (estado.autenticado && usuario != null) {
                    Surface(
                        color = cores.subCabecalhoFundo,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 16.dp, vertical = 7.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Row(
                                modifier = Modifier.weight(1f),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Text(
                                    text = usuario.nome,
                                    color = Color.White,
                                    style = MaterialTheme.typography.bodySmall,
                                    fontWeight = FontWeight.SemiBold,
                                    maxLines = 1,
                                    overflow = TextOverflow.Ellipsis,
                                )
                                Etiqueta(
                                    texto = AriadneCatalogos.rotuloPapel(usuario.papel),
                                    fundo = DouradoAriadne,
                                    corTexto = DouradoTexto,
                                )
                            }

                            val pendentes = estado.itensFila.size
                            Box(
                                modifier = Modifier.clickable { abrirFila = true },
                            ) {
                                Etiqueta(
                                    texto = if (pendentes > 0) "Fila offline: $pendentes" else "Sincronizado",
                                    fundo = if (pendentes > 0) cores.ambarFundo else cores.verdeFundo,
                                    corTexto = if (pendentes > 0) cores.ambarTexto else cores.verdeTexto,
                                )
                            }
                        }
                    }
                }
            }
        },
        bottomBar = {
            if (estado.autenticado && usuario != null) {
                NavigationBar(containerColor = cores.fundoCartao) {
                    val coresItem = NavigationBarItemDefaults.colors(
                        selectedIconColor = cores.azulDestaque,
                        selectedTextColor = cores.azulDestaque,
                        indicatorColor = cores.superficieSuave,
                        unselectedIconColor = cores.textoSecundario,
                        unselectedTextColor = cores.textoSecundario,
                    )
                    NavigationBarItem(
                        selected = abaSelecionada == 0,
                        onClick = { irParaAba(0) },
                        icon = { IconePainel(if (abaSelecionada == 0) cores.azulDestaque else cores.textoSecundario) },
                        label = { Text("Painel", maxLines = 1) },
                        colors = coresItem,
                    )
                    NavigationBarItem(
                        selected = abaSelecionada == 1,
                        onClick = { irParaAba(1) },
                        icon = { IconeTarefas(if (abaSelecionada == 1) cores.azulDestaque else cores.textoSecundario) },
                        label = {
                            Text(
                                text = if (ehOrientadorOuAdmin) "Tarefas" else "Cronograma",
                                maxLines = 1,
                            )
                        },
                        colors = coresItem,
                    )
                    NavigationBarItem(
                        selected = abaSelecionada == 2,
                        onClick = { irParaAba(2) },
                        icon = { IconeCalendario(if (abaSelecionada == 2) cores.azulDestaque else cores.textoSecundario) },
                        label = { Text("Reuniões", maxLines = 1) },
                        colors = coresItem,
                    )
                    NavigationBarItem(
                        selected = abaSelecionada == 3,
                        onClick = { irParaAba(3) },
                        icon = { IconeDocumento(if (abaSelecionada == 3) cores.azulDestaque else cores.textoSecundario) },
                        label = {
                            Text(
                                text = if (ehOrientadorOuAdmin) "Orientandos" else "Pareceres",
                                maxLines = 1,
                            )
                        },
                        colors = coresItem,
                    )
                }
            }
        },
        floatingActionButton = {
            if (estado.autenticado) {
                if (marcoAbertoId != null) {
                    // na tela da tarefa, sem botão flutuante
                } else if (abaSelecionada == 1 && ehOrientadorOuAdmin) {
                    FloatingActionButton(
                        onClick = { abrirNovaTarefa = true },
                        containerColor = AzulAriadne,
                        contentColor = Color.White,
                    ) { Text("+ Tarefa", modifier = Modifier.padding(horizontal = 14.dp)) }
                } else if (abaSelecionada == 2 && ehOrientador) {
                    FloatingActionButton(
                        onClick = { abrirAgendarReuniao = true },
                        containerColor = AzulAriadne,
                        contentColor = Color.White,
                    ) { Text("+ Reunião", modifier = Modifier.padding(horizontal = 14.dp)) }
                }
            }
        },
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding),
        ) {
            if (!estado.autenticado || usuario == null) {
                TelaLogin(
                    urlInicial = estado.urlServidor,
                    carregando = carregando,
                    mensagem = mensagemStatus,
                    erro = erroStatus,
                    onEntrar = { url, email, senha ->
                        executarNoNucleo {
                            AriadneRustBridge.loginESincronizar(dbPath, url, email, senha)
                        }
                    },
                )
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    if (carregando) {
                        LinearProgressIndicator(
                            modifier = Modifier.fillMaxWidth(),
                            color = cores.azulDestaque,
                            trackColor = cores.superficieSuave,
                        )
                    }

                    if (!estado.ultimaSync.isNullOrBlank()) {
                        Text(
                            text = "Atualizado em ${formatarDataHoraBr(estado.ultimaSync)} (UTC)",
                            style = MaterialTheme.typography.labelSmall,
                            color = cores.textoSecundario,
                        )
                    }
                    if (!mensagemStatus.isNullOrBlank()) {
                        BannerMensagem(mensagemStatus!!, erro = false)
                    }
                    if (!erroStatus.isNullOrBlank()) {
                        BannerMensagem(erroStatus!!, erro = true)
                    }

                    val enfileirar: (String, String) -> Unit = { acao, dadosJson ->
                        executarNoNucleo {
                            AriadneRustBridge.enfileirarOperacao(dbPath, acao, dadosJson)
                        }
                    }

                    val marcoAberto = marcoAbertoId?.let { id -> estado.marcos.firstOrNull { it.id == id } }
                    Box(modifier = Modifier.weight(1f)) {
                        if (marcoAberto != null) {
                            TelaDetalheMarco(
                                marco = marcoAberto,
                                orientacao = estado.orientacoes.firstOrNull { it.id == marcoAberto.orientacaoId },
                                usuario = usuario,
                                documentos = estado.documentos,
                                carregando = carregando,
                                onVoltar = { marcoAbertoId = null },
                                onEnfileirar = enfileirar,
                                onEnviarEntrega = { pedidoJson ->
                                    executarNoNucleo {
                                        AriadneRustBridge.enviarEntrega(dbPath, pedidoJson)
                                    }
                                },
                            )
                        } else when (abaSelecionada) {
                            0 -> AbaPainel(
                                usuario = usuario,
                                orientacoes = estado.orientacoes,
                                marcos = estado.marcos,
                                atas = estado.atas,
                                onEnfileirar = enfileirar,
                                onAbrirNovaTarefa = { abrirNovaTarefa = true },
                                onAbrirAgendarReuniao = { abrirAgendarReuniao = true },
                                onAbrirNovoParecer = {
                                    parecerOrientacaoAlvo = null
                                    abrirNovoParecer = true
                                },
                                onIrParaTarefas = { filtro ->
                                    filtroStatusTarefa = filtro
                                    abaSelecionada = 1
                                },
                                onIrParaReunioes = { filtro ->
                                    filtroReuniao = filtro
                                    abaSelecionada = 2
                                },
                                onAbrirMarco = { marcoAbertoId = it },
                            )
                            1 -> AbaTarefas(
                                usuario = usuario,
                                orientacoes = estado.orientacoes,
                                marcos = estado.marcos,
                                atas = estado.atas,
                                filtroOrientacao = filtroOrientacao,
                                onMudarFiltroOrientacao = { filtroOrientacao = it },
                                filtroStatusInicial = filtroStatusTarefa,
                                modoCalendario = modoCalendario,
                                onMudarModoCalendario = { modoCalendario = it },
                                onEnfileirar = enfileirar,
                                onAbrirMarco = { marcoAbertoId = it },
                            )
                            2 -> AbaReunioes(
                                usuario = usuario,
                                orientacoes = estado.orientacoes,
                                atas = estado.atas,
                                filtroOrientacao = filtroOrientacao,
                                filtroInicial = filtroReuniao,
                                onEnfileirar = enfileirar,
                            )
                            else -> AbaOrientandosEPareceres(
                                usuario = usuario,
                                orientacoes = estado.orientacoes,
                                marcos = estado.marcos,
                                documentos = estado.documentos,
                                atas = estado.atas,
                                pareceres = estado.pareceres,
                                filtroOrientacao = filtroOrientacao,
                                onVerTarefasDaOrientacao = { oid ->
                                    filtroOrientacao = oid
                                    filtroStatusTarefa = FiltroStatusTarefa.PENDENTES
                                    abaSelecionada = 1
                                },
                                onEmitirParecerParaOrientacao = { oid ->
                                    parecerOrientacaoAlvo = oid
                                    abrirNovoParecer = true
                                },
                            )
                        }
                    }
                }
            }
        }
    }

    if (abrirNovaTarefa && usuario != null) {
        val geriveis = estado.orientacoes.filter {
            usuario.papel == "admin" || it.orientadorId == usuario.id
        }
        DialogoNovaTarefa(
            orientacoes = geriveis,
            orientacaoInicialId = filtroOrientacao,
            onDismiss = { abrirNovaTarefa = false },
            onSalvar = { dados ->
                abrirNovaTarefa = false
                executarNoNucleo {
                    AriadneRustBridge.enfileirarOperacao(dbPath, "criar_tarefa", dados)
                }
            },
        )
    }

    if (abrirAgendarReuniao && usuario != null) {
        val proprias = estado.orientacoes.filter { it.orientadorId == usuario.id }
        DialogoAgendarReuniao(
            orientacoes = proprias,
            orientacaoInicialId = filtroOrientacao,
            onDismiss = { abrirAgendarReuniao = false },
            onSalvar = { dados ->
                abrirAgendarReuniao = false
                executarNoNucleo {
                    AriadneRustBridge.enfileirarOperacao(dbPath, "agendar_reuniao", dados)
                }
            },
        )
    }

    if (abrirNovoParecer && usuario != null) {
        val geriveis = estado.orientacoes.filter {
            usuario.papel == "admin" || it.orientadorId == usuario.id
        }
        DialogoNovoParecer(
            orientacoes = geriveis,
            documentos = estado.documentos,
            marcos = estado.marcos,
            orientacaoInicialId = parecerOrientacaoAlvo,
            onDismiss = { abrirNovoParecer = false },
            onSalvar = { dados ->
                abrirNovoParecer = false
                executarNoNucleo {
                    AriadneRustBridge.enfileirarOperacao(dbPath, "emitir_parecer", dados)
                }
            },
        )
    }

    if (abrirFila) {
        DialogoFilaOffline(
            itens = estado.itensFila,
            marcos = estado.marcos,
            onDescartar = { opId ->
                executarNoNucleo { AriadneRustBridge.descartarOperacao(dbPath, opId) }
            },
            onDismiss = { abrirFila = false },
        )
    }

    if (confirmarSaida) {
        AlertDialog(
            onDismissRequest = { confirmarSaida = false },
            title = { Text("Sair com alterações pendentes?") },
            text = {
                Text(
                    "Há ${estado.itensFila.size} alteração(ões) ainda não sincronizadas com o servidor. " +
                        "Se sair agora, elas serão descartadas do aparelho."
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        confirmarSaida = false
                        abaSelecionada = 0
                        filtroOrientacao = null
                        executarNoNucleo { AriadneRustBridge.encerrarSessao(dbPath) }
                    },
                ) { Text("Sair e descartar") }
            },
            dismissButton = {
                TextButton(onClick = { confirmarSaida = false }) { Text("Cancelar") }
            },
        )
    }
}
