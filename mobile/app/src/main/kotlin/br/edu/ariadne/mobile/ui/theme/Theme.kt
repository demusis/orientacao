package br.edu.ariadne.mobile.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

private val AriadneLightColorScheme = lightColorScheme(
    primary = AzulAriadne,
    onPrimary = Branco,
    primaryContainer = InfoFundo,
    onPrimaryContainer = AzulEscuro,
    secondary = Color(0xFF486271),
    onSecondary = Branco,
    secondaryContainer = AzulSuave,
    onSecondaryContainer = TextoPrincipal,
    tertiary = DouradoAriadne,
    onTertiary = DouradoTexto,
    background = FundoApp,
    onBackground = TextoPrincipal,
    surface = Branco,
    onSurface = TextoPrincipal,
    surfaceVariant = AzulSuave,
    onSurfaceVariant = TextoSecundario,
    outline = BordaPadrao,
    outlineVariant = BordaPadrao,
    error = VermelhoAcento,
    onError = Branco,
    errorContainer = VermelhoFundo,
    onErrorContainer = VermelhoTexto,
)

private val AriadneDarkColorScheme = darkColorScheme(
    primary = AzulDestaqueNoturno,
    onPrimary = Color(0xFF0A243E),
    primaryContainer = Color(0xFF1B3554),
    onPrimaryContainer = Color(0xFFDBEAFE),
    secondary = Color(0xFFB0CADC),
    onSecondary = Color(0xFF193342),
    secondaryContainer = Color(0xFF222C36),
    onSecondaryContainer = Color(0xFFE6ECF2),
    tertiary = DouradoAriadne,
    onTertiary = DouradoTexto,
    background = Color(0xFF0F1419),
    onBackground = Color(0xFFE6ECF2),
    surface = Color(0xFF182028),
    onSurface = Color(0xFFE6ECF2),
    surfaceVariant = Color(0xFF222C36),
    onSurfaceVariant = Color(0xFF9AA6B2),
    outline = Color(0xFF2F3B47),
    outlineVariant = Color(0xFF2F3B47),
    error = Color(0xFFEF5350),
    onError = Color(0xFF3E0A0E),
    errorContainer = Color(0xFF421C21),
    onErrorContainer = Color(0xFFFCA5A5),
)

private val LocalPaletaSemantica = staticCompositionLocalOf { PaletaClara }

@Composable
fun coresAriadne(): PaletaSemantica = LocalPaletaSemantica.current

@Composable
fun ARIADNETheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    @Suppress("UNUSED_PARAMETER") dynamicColor: Boolean = false,
    content: @Composable () -> Unit,
) {
    val colorScheme = if (darkTheme) AriadneDarkColorScheme else AriadneLightColorScheme
    val paleta = if (darkTheme) PaletaEscura else PaletaClara

    CompositionLocalProvider(LocalPaletaSemantica provides paleta) {
        MaterialTheme(
            colorScheme = colorScheme,
            typography = Typography,
            content = content,
        )
    }
}
