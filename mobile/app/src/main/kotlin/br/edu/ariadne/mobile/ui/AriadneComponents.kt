package br.edu.ariadne.mobile.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import br.edu.ariadne.mobile.R
import br.edu.ariadne.mobile.core.formatarDataBr
import br.edu.ariadne.mobile.ui.theme.AzulAriadne
import br.edu.ariadne.mobile.ui.theme.coresAriadne
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneOffset
import java.time.format.TextStyle as EstiloTextoData
import java.util.Locale

@Composable
fun BrasaoAriadne(
    size: Dp = 32.dp,
    modifier: Modifier = Modifier,
    fundo: Color = Color.Transparent,
) {
    val caixaModifier = if (fundo != Color.Transparent) {
        modifier
            .size(size)
            .clip(RoundedCornerShape(size * 0.22f))
            .background(fundo)
    } else {
        modifier.size(size)
    }
    Box(
        modifier = caixaModifier,
        contentAlignment = Alignment.Center,
    ) {
        Image(
            painter = painterResource(id = R.drawable.ic_launcher_foreground),
            contentDescription = "Logotipo ARIADNE",
            modifier = Modifier
                .fillMaxSize()
                .graphicsLayer(scaleX = 1.6f, scaleY = 1.6f),
        )
    }
}

@Composable
fun CartaoAriadne(
    modifier: Modifier = Modifier,
    accentColor: Color? = null,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val cores = coresAriadne()
    val cardModifier = modifier
        .fillMaxWidth()
        .then(if (onClick != null) Modifier.clickable(onClick = onClick) else Modifier)

    Surface(
        modifier = cardModifier,
        shape = RoundedCornerShape(10.dp),
        color = cores.fundoCartao,
        border = BorderStroke(1.dp, cores.borda),
        shadowElevation = 1.dp,
    ) {
        // A faixa de acento é desenhada atrás do conteúdo, na altura que ele de
        // fato ocupa. Antes era um Box numa Row com height(IntrinsicSize.Min):
        // a medição intrínseca subestimava a altura (FlowRow, texto quebrado,
        // fonte grande do aparelho) e esmagava o último item do cartão — o
        // botão "Sinalizar conclusão" virava uma barra azul sem rótulo.
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .then(
                    if (accentColor != null) {
                        Modifier.drawBehind {
                            drawRect(color = accentColor, size = Size(4.dp.toPx(), size.height))
                        }
                    } else {
                        Modifier
                    },
                )
                .padding(
                    start = if (accentColor != null) 18.dp else 14.dp,
                    top = 14.dp,
                    end = 14.dp,
                    bottom = 14.dp,
                ),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            content = content,
        )
    }
}

@Composable
fun Etiqueta(texto: String, fundo: Color, corTexto: Color) {
    Box(
        modifier = Modifier
            .background(fundo, RoundedCornerShape(999.dp))
            .padding(horizontal = 9.dp, vertical = 3.dp),
    ) {
        Text(
            text = texto,
            color = corTexto,
            style = MaterialTheme.typography.labelSmall,
            fontWeight = FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis,
        )
    }
}

@Composable
fun BannerMensagem(texto: String, erro: Boolean, sucesso: Boolean = false) {
    val cores = coresAriadne()
    val (fundo, borda, corTexto) = when {
        erro -> Triple(cores.vermelhoFundo, cores.vermelhoAcento, cores.vermelhoTexto)
        sucesso -> Triple(cores.verdeFundo, cores.verdeAcento, cores.verdeTexto)
        else -> Triple(cores.infoFundo, cores.azulDestaque, cores.infoTexto)
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(1.dp, borda.copy(alpha = 0.45f)),
        colors = CardDefaults.cardColors(containerColor = fundo),
    ) {
        Text(
            text = texto,
            color = corTexto,
            style = MaterialTheme.typography.bodySmall,
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
        )
    }
}

@Composable
fun CabecalhoSecao(
    titulo: String,
    contagem: Int? = null,
    subtitulo: String? = null,
) {
    val cores = coresAriadne()
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = titulo,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                color = cores.azulDestaque,
            )
            if (contagem != null) {
                Etiqueta(contagem.toString(), cores.superficieSuave, cores.azulDestaque)
            }
        }
        if (!subtitulo.isNullOrBlank()) {
            Text(
                text = subtitulo,
                style = MaterialTheme.typography.bodySmall,
                color = cores.textoSecundario,
            )
        }
    }
}

@Composable
fun KpiCard(
    valor: Int,
    rotulo: String,
    corAcento: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val cores = coresAriadne()
    Surface(
        modifier = modifier.clickable(onClick = onClick),
        shape = RoundedCornerShape(10.dp),
        color = cores.fundoCartao,
        border = BorderStroke(1.dp, cores.borda),
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(
                text = valor.toString(),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = corAcento,
            )
            Text(
                text = rotulo,
                style = MaterialTheme.typography.labelSmall,
                color = cores.textoSecundario,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
fun BarraProgressoCronograma(concluidas: Int, total: Int) {
    val cores = coresAriadne()
    val fracao = if (total > 0) (concluidas.toFloat() / total.toFloat()).coerceIn(0f, 1f) else 0f
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = "Progresso do cronograma",
                style = MaterialTheme.typography.labelMedium,
                color = cores.textoSecundario,
            )
            Text(
                text = if (total > 0) "$concluidas de $total concluídas" else "Sem tarefas",
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
                color = cores.azulDestaque,
            )
        }
        LinearProgressIndicator(
            progress = { fracao },
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp)
                .clip(RoundedCornerShape(999.dp)),
            color = cores.verdeAcento,
            trackColor = cores.superficieSuave,
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CampoDataMaterial3(
    rotulo: String,
    dataIso: String,
    onDataSelecionada: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    val cores = coresAriadne()
    var abrirPicker by remember { mutableStateOf(false) }

    Box(modifier = modifier) {
        OutlinedTextField(
            value = formatarDataBr(dataIso),
            onValueChange = {},
            readOnly = true,
            label = { Text(rotulo) },
            placeholder = { Text("DD/MM/AAAA") },
            trailingIcon = {
                IconeCalendario(cor = cores.azulDestaque, modifier = Modifier.size(20.dp))
            },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        Box(
            modifier = Modifier
                .matchParentSize()
                .clickable { abrirPicker = true },
        )
    }

    if (abrirPicker) {
        val inicialMillis = remember(dataIso) {
            runCatching {
                LocalDate.parse(dataIso.trim().take(10))
                    .atStartOfDay(ZoneOffset.UTC)
                    .toInstant()
                    .toEpochMilli()
            }.getOrNull()
        }
        val state = rememberDatePickerState(initialSelectedDateMillis = inicialMillis)
        DatePickerDialog(
            onDismissRequest = { abrirPicker = false },
            confirmButton = {
                TextButton(
                    onClick = {
                        state.selectedDateMillis?.let { millis ->
                            val data = Instant.ofEpochMilli(millis)
                                .atZone(ZoneOffset.UTC)
                                .toLocalDate()
                                .toString()
                            onDataSelecionada(data)
                        }
                        abrirPicker = false
                    },
                ) { Text("Selecionar") }
            },
            dismissButton = {
                TextButton(onClick = { abrirPicker = false }) { Text("Cancelar") }
            },
        ) {
            DatePicker(state = state)
        }
    }
}

@Composable
fun SeletorDropdown(
    rotulo: String,
    opcoes: List<String>,
    indiceAtual: Int,
    onSelecionar: (Int) -> Unit,
) {
    var expandido by remember { mutableStateOf(false) }
    Box {
        OutlinedButton(onClick = { expandido = true }, modifier = Modifier.fillMaxWidth()) {
            Text(
                text = "$rotulo: ${opcoes.getOrElse(indiceAtual) { "" }}",
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
        DropdownMenu(expanded = expandido, onDismissRequest = { expandido = false }) {
            opcoes.forEachIndexed { idx, nome ->
                DropdownMenuItem(
                    text = { Text(nome) },
                    onClick = {
                        onSelecionar(idx)
                        expandido = false
                    },
                )
            }
        }
    }
}

@Composable
fun NotaDestacada(
    titulo: String,
    texto: String,
    fundo: Color,
    corBorda: Color,
    corTexto: Color,
) {
    val cores = coresAriadne()
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(6.dp),
        color = fundo,
        border = BorderStroke(1.dp, corBorda.copy(alpha = 0.35f)),
    ) {
        Column(modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp)) {
            Text(
                text = titulo,
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.Bold,
                color = corTexto,
            )
            Spacer(Modifier.height(2.dp))
            TextoComLinks(
                texto = texto,
                style = MaterialTheme.typography.bodySmall,
                color = cores.textoPrincipal,
            )
        }
    }
}

@Composable
fun IconePainel(cor: Color, modifier: Modifier = Modifier.size(22.dp)) {
    Canvas(modifier = modifier) {
        val gap = size.width * 0.12f
        val cell = (size.width - gap * 3f) / 2f
        val r = CornerRadius(cell * 0.25f, cell * 0.25f)
        val stroke = Stroke(width = size.width * 0.09f)
        drawRoundRect(cor, Offset(gap, gap), Size(cell, cell), r, style = stroke)
        drawRoundRect(cor, Offset(gap * 2 + cell, gap), Size(cell, cell), r, style = stroke)
        drawRoundRect(cor, Offset(gap, gap * 2 + cell), Size(cell, cell), r, style = stroke)
        drawRoundRect(cor, Offset(gap * 2 + cell, gap * 2 + cell), Size(cell, cell), r, style = stroke)
    }
}

@Composable
fun IconeTarefas(cor: Color, modifier: Modifier = Modifier.size(22.dp)) {
    Canvas(modifier = modifier) {
        val sw = size.width * 0.09f
        val ys = listOf(0.26f, 0.52f, 0.78f)
        ys.forEach { y ->
            drawCircle(cor, radius = sw * 0.65f, center = Offset(size.width * 0.18f, size.height * y))
            drawLine(
                color = cor,
                start = Offset(size.width * 0.34f, size.height * y),
                end = Offset(size.width * 0.88f, size.height * y),
                strokeWidth = sw,
                cap = StrokeCap.Round,
            )
        }
    }
}

@Composable
fun IconeCalendario(cor: Color, modifier: Modifier = Modifier.size(22.dp)) {
    Canvas(modifier = modifier) {
        val sw = size.width * 0.085f
        val left = size.width * 0.14f
        val top = size.height * 0.22f
        val w = size.width * 0.72f
        val h = size.height * 0.64f
        drawRoundRect(
            color = cor,
            topLeft = Offset(left, top),
            size = Size(w, h),
            cornerRadius = CornerRadius(size.width * 0.12f),
            style = Stroke(width = sw),
        )
        drawLine(
            cor,
            Offset(left, top + h * 0.30f),
            Offset(left + w, top + h * 0.30f),
            strokeWidth = sw,
        )
        drawLine(
            cor,
            Offset(size.width * 0.34f, size.height * 0.12f),
            Offset(size.width * 0.34f, size.height * 0.28f),
            strokeWidth = sw,
            cap = StrokeCap.Round,
        )
        drawLine(
            cor,
            Offset(size.width * 0.66f, size.height * 0.12f),
            Offset(size.width * 0.66f, size.height * 0.28f),
            strokeWidth = sw,
            cap = StrokeCap.Round,
        )
    }
}

@Composable
fun IconeDocumento(cor: Color, modifier: Modifier = Modifier.size(22.dp)) {
    Canvas(modifier = modifier) {
        val sw = size.width * 0.085f
        val left = size.width * 0.22f
        val right = size.width * 0.78f
        val top = size.height * 0.14f
        val bottom = size.height * 0.86f
        val fold = size.width * 0.18f
        val path = Path().apply {
            moveTo(left, top)
            lineTo(right - fold, top)
            lineTo(right, top + fold)
            lineTo(right, bottom)
            lineTo(left, bottom)
            close()
        }
        drawPath(path, cor, style = Stroke(width = sw, join = StrokeJoin.Round))
        drawLine(
            cor,
            Offset(left + size.width * 0.12f, size.height * 0.48f),
            Offset(right - size.width * 0.12f, size.height * 0.48f),
            strokeWidth = sw,
            cap = StrokeCap.Round,
        )
        drawLine(
            cor,
            Offset(left + size.width * 0.12f, size.height * 0.66f),
            Offset(right - size.width * 0.20f, size.height * 0.66f),
            strokeWidth = sw,
            cap = StrokeCap.Round,
        )
    }
}

@Composable
fun IconeSincronizar(cor: Color, modifier: Modifier = Modifier.size(20.dp)) {
    Canvas(modifier = modifier) {
        val sw = size.width * 0.10f
        val inset = size.width * 0.18f
        val arcSize = Size(size.width - inset * 2f, size.height - inset * 2f)
        drawArc(
            color = cor,
            startAngle = -35f,
            sweepAngle = 140f,
            useCenter = false,
            topLeft = Offset(inset, inset),
            size = arcSize,
            style = Stroke(width = sw, cap = StrokeCap.Round),
        )
        drawArc(
            color = cor,
            startAngle = 145f,
            sweepAngle = 140f,
            useCenter = false,
            topLeft = Offset(inset, inset),
            size = arcSize,
            style = Stroke(width = sw, cap = StrokeCap.Round),
        )
    }
}

// ---------------------------------------------------------------------------
// Texto com links clicáveis

private val REGEX_URL = Regex("""https?://[^\s<>"']+""")

/** Tira a pontuação que costuma colar no fim de um link dentro de uma frase
 * ("Vide https://exemplo.org/x)." → o link termina em "x"). Parêntese de
 * fechamento só sai quando não tem par aberto dentro do próprio link. */
private fun aparaPontuacaoFinal(url: String): String {
    var fim = url.length
    while (fim > 0) {
        val c = url[fim - 1]
        if (c !in ".,;:!?)]}") break
        if (c == ')') {
            val trecho = url.substring(0, fim)
            if (trecho.count { it == '(' } >= trecho.count { it == ')' }) break
        }
        fim--
    }
    return url.substring(0, fim)
}

/** Texto em que os endereços http(s) viram links que abrem no navegador. */
@Composable
fun TextoComLinks(
    texto: String,
    modifier: Modifier = Modifier,
    style: TextStyle = MaterialTheme.typography.bodyMedium,
    color: Color = Color.Unspecified,
    maxLines: Int = Int.MAX_VALUE,
) {
    val cores = coresAriadne()
    val corLink = cores.azulDestaque
    val anotado = remember(texto, corLink) {
        val estiloLink = TextLinkStyles(
            style = SpanStyle(color = corLink, textDecoration = TextDecoration.Underline),
        )
        buildAnnotatedString {
            var cursor = 0
            for (achado in REGEX_URL.findAll(texto)) {
                val url = aparaPontuacaoFinal(achado.value)
                if (url.length < 10) continue
                val inicio = achado.range.first
                append(texto.substring(cursor, inicio))
                withLink(LinkAnnotation.Url(url, estiloLink)) { append(url) }
                cursor = inicio + url.length
            }
            append(texto.substring(cursor))
        }
    }
    Text(
        text = anotado,
        modifier = modifier,
        style = style,
        color = color,
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
    )
}

// ---------------------------------------------------------------------------
// Calendário mensal de prazos

/** Um marcador num dia do calendário: cor do ponto e se é reunião (anel). */
data class MarcaCalendario(val cor: Color, val reuniao: Boolean = false)

/**
 * Grade mensal com os dias que têm prazos (pontos coloridos pelo status) e
 * reuniões (anel). `marcas` é indexado pela data ISO (yyyy-MM-dd).
 */
@Composable
fun CalendarioPrazos(
    mes: YearMonth,
    hoje: LocalDate,
    selecionado: LocalDate?,
    marcas: Map<String, List<MarcaCalendario>>,
    onMudarMes: (YearMonth) -> Unit,
    onSelecionarDia: (LocalDate) -> Unit,
    modifier: Modifier = Modifier,
) {
    val cores = coresAriadne()
    val local = Locale.forLanguageTag("pt-BR")
    CartaoAriadne(modifier = modifier) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            TextButton(onClick = { onMudarMes(mes.minusMonths(1)) }) { Text("‹") }
            Text(
                text = mes.month.getDisplayName(EstiloTextoData.FULL_STANDALONE, local)
                    .replaceFirstChar { it.titlecase(local) } + " de ${mes.year}",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = cores.textoPrincipal,
            )
            TextButton(onClick = { onMudarMes(mes.plusMonths(1)) }) { Text("›") }
        }

        // Semana começando no domingo, como no calendário de parede.
        val diasSemana = listOf("D", "S", "T", "Q", "Q", "S", "S")
        Row(modifier = Modifier.fillMaxWidth()) {
            diasSemana.forEach { d ->
                Text(
                    text = d,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.labelSmall,
                    color = cores.textoSecundario,
                    textAlign = TextAlign.Center,
                )
            }
        }

        val deslocamento = mes.atDay(1).dayOfWeek.value % 7 // domingo = 0
        val semanas = (deslocamento + mes.lengthOfMonth() + 6) / 7
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            for (semana in 0 until semanas) {
                Row(modifier = Modifier.fillMaxWidth()) {
                    for (col in 0 until 7) {
                        val numeroDia = semana * 7 + col - deslocamento + 1
                        if (numeroDia < 1 || numeroDia > mes.lengthOfMonth()) {
                            Spacer(Modifier.weight(1f).height(46.dp))
                        } else {
                            val data = mes.atDay(numeroDia)
                            CelulaDia(
                                dia = numeroDia,
                                ehHoje = data == hoje,
                                selecionado = data == selecionado,
                                fimDeSemana = data.dayOfWeek == DayOfWeek.SUNDAY ||
                                    data.dayOfWeek == DayOfWeek.SATURDAY,
                                marcas = marcas[data.toString()].orEmpty(),
                                onClick = { onSelecionarDia(data) },
                                modifier = Modifier.weight(1f),
                            )
                        }
                    }
                }
            }
        }

        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            LegendaCalendario(cores.vermelhoAcento, "atrasada/devolvida")
            LegendaCalendario(cores.ambarAcento, "aguarda orientador")
        }
        Row(
            horizontalArrangement = Arrangement.spacedBy(10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            LegendaCalendario(cores.azulDestaque, "em aberto")
            LegendaCalendario(cores.verdeAcento, "concluída")
            LegendaCalendario(cores.textoSecundario, "reunião", reuniao = true)
        }
    }
}

@Composable
private fun LegendaCalendario(cor: Color, texto: String, reuniao: Boolean = false) {
    val cores = coresAriadne()
    Row(
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Canvas(modifier = Modifier.size(8.dp)) {
            if (reuniao) {
                drawCircle(color = cor, style = Stroke(width = 1.5.dp.toPx()))
            } else {
                drawCircle(color = cor)
            }
        }
        Text(texto, style = MaterialTheme.typography.labelSmall, color = cores.textoSecundario)
    }
}

@Composable
private fun CelulaDia(
    dia: Int,
    ehHoje: Boolean,
    selecionado: Boolean,
    fimDeSemana: Boolean,
    marcas: List<MarcaCalendario>,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val cores = coresAriadne()
    val fundo = when {
        selecionado -> cores.azulDestaque
        ehHoje -> cores.infoFundo
        else -> Color.Transparent
    }
    val corNumero = when {
        selecionado -> Color.White
        fimDeSemana -> cores.textoSecundario
        else -> cores.textoPrincipal
    }
    Column(
        modifier = modifier
            .height(46.dp)
            .padding(1.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(fundo)
            .clickable(onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = dia.toString(),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (ehHoje || marcas.isNotEmpty()) FontWeight.Bold else FontWeight.Normal,
            color = corNumero,
        )
        if (marcas.isNotEmpty()) {
            Row(
                horizontalArrangement = Arrangement.spacedBy(2.dp),
                modifier = Modifier.padding(top = 2.dp),
            ) {
                marcas.take(4).forEach { m ->
                    val cor = if (selecionado) Color.White else m.cor
                    Canvas(modifier = Modifier.size(6.dp)) {
                        if (m.reuniao) {
                            drawCircle(color = cor, style = Stroke(width = 1.5.dp.toPx()))
                        } else {
                            drawCircle(color = cor)
                        }
                    }
                }
            }
        }
    }
}
