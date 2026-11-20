package br.edu.ariadne.mobile.ui.theme

import androidx.compose.ui.graphics.Color

val AzulAriadne = Color(0xFF1A4B7A)
val AzulEscuro = Color(0xFF123557)
val AzulCabecalhoNoturno = Color(0xFF122D4A)
val AzulSubCabecalhoNoturno = Color(0xFF0C2136)
val AzulDestaqueNoturno = Color(0xFF7BB3E8)

val AzulSuave = Color(0xFFE6EBF1)
val DouradoAriadne = Color(0xFFE8B84B)
val DouradoTexto = Color(0xFF3D2F08)

val FundoApp = Color(0xFFF0F2F5)
val Branco = Color(0xFFFFFFFF)
val BordaPadrao = Color(0xFFD0D5DB)
val TextoPrincipal = Color(0xFF1C1E21)
val TextoSecundario = Color(0xFF5A6570)

val VerdeFundo = Color(0xFFD8F0D8)
val VerdeTexto = Color(0xFF1E4620)
val VerdeAcento = Color(0xFF2E7D32)

val AmbarFundo = Color(0xFFFFF3CD)
val AmbarTexto = Color(0xFF664D03)
val AmbarAcento = Color(0xFFD97706)

val VermelhoFundo = Color(0xFFF8D7DA)
val VermelhoTexto = Color(0xFF842029)
val VermelhoAcento = Color(0xFFB02A37)

val InfoFundo = Color(0xFFDBEAFE)
val InfoTexto = Color(0xFF1E40AF)

data class PaletaSemantica(
    val fundoApp: Color,
    val fundoCartao: Color,
    val superficieSuave: Color,
    val borda: Color,
    val textoPrincipal: Color,
    val textoSecundario: Color,
    val azulDestaque: Color,
    val cabecalhoFundo: Color,
    val subCabecalhoFundo: Color,
    val verdeFundo: Color,
    val verdeTexto: Color,
    val verdeAcento: Color,
    val ambarFundo: Color,
    val ambarTexto: Color,
    val ambarAcento: Color,
    val vermelhoFundo: Color,
    val vermelhoTexto: Color,
    val vermelhoAcento: Color,
    val infoFundo: Color,
    val infoTexto: Color,
)

val PaletaClara = PaletaSemantica(
    fundoApp = FundoApp,
    fundoCartao = Branco,
    superficieSuave = AzulSuave,
    borda = BordaPadrao,
    textoPrincipal = TextoPrincipal,
    textoSecundario = TextoSecundario,
    azulDestaque = AzulAriadne,
    cabecalhoFundo = AzulAriadne,
    subCabecalhoFundo = AzulEscuro,
    verdeFundo = VerdeFundo,
    verdeTexto = VerdeTexto,
    verdeAcento = VerdeAcento,
    ambarFundo = AmbarFundo,
    ambarTexto = AmbarTexto,
    ambarAcento = AmbarAcento,
    vermelhoFundo = VermelhoFundo,
    vermelhoTexto = VermelhoTexto,
    vermelhoAcento = VermelhoAcento,
    infoFundo = InfoFundo,
    infoTexto = InfoTexto,
)

val PaletaEscura = PaletaSemantica(
    fundoApp = Color(0xFF0F1419),
    fundoCartao = Color(0xFF182028),
    superficieSuave = Color(0xFF222C36),
    borda = Color(0xFF2F3B47),
    textoPrincipal = Color(0xFFE6ECF2),
    textoSecundario = Color(0xFF9AA6B2),
    azulDestaque = AzulDestaqueNoturno,
    cabecalhoFundo = AzulCabecalhoNoturno,
    subCabecalhoFundo = AzulSubCabecalhoNoturno,
    verdeFundo = Color(0xFF1A3A24),
    verdeTexto = Color(0xFF9CE2AC),
    verdeAcento = Color(0xFF4CAF50),
    ambarFundo = Color(0xFF3E2E12),
    ambarTexto = Color(0xFFFCD34D),
    ambarAcento = Color(0xFFF59E0B),
    vermelhoFundo = Color(0xFF421C21),
    vermelhoTexto = Color(0xFFFCA5A5),
    vermelhoAcento = Color(0xFFEF5350),
    infoFundo = Color(0xFF1B3554),
    infoTexto = Color(0xFF93C5FD),
)
