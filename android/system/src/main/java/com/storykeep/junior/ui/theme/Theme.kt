package com.storykeep.junior.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

private val StorykeepScheme = lightColorScheme(
    primary = Amber,
    onPrimary = OnAmber,
    secondary = DeepInk,
    onSecondary = PaperCream,
    background = PaperCream,
    onBackground = DeepInk,
    surface = PaperRaised,
    onSurface = DeepInk,
    surfaceVariant = PaperCream,
    onSurfaceVariant = InkMuted,
    outline = PaperLine,
    tertiary = Amber,
    onTertiary = OnAmber,
)

@Composable
fun StorykeepTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = StorykeepScheme,
        typography = StorykeepTypography,
        content = content,
    )
}
