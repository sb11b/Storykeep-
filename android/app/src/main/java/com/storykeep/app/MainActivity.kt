package com.storykeep.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            StorykeepTheme {
                StorykeepApp()
            }
        }
    }
}

@Composable
fun StorykeepApp() {
    Scaffold(modifier = Modifier.fillMaxSize()) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(
                text = "Storykeep",
                style = MaterialTheme.typography.headlineMedium,
            )
            Text(
                text = "Kotlin · Jetpack Compose scaffold. Sync comes later.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
fun StorykeepTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Color(0xFF1B3A4B),
            onPrimary = Color(0xFFF4EFE6),
            background = Color(0xFFF4EFE6),
            surface = Color(0xFFF4EFE6),
            onBackground = Color(0xFF1B3A4B),
            onSurface = Color(0xFF1B3A4B),
        ),
    ) {
        Surface(color = MaterialTheme.colorScheme.background, content = content)
    }
}

@Preview(showBackground = true)
@Composable
private fun StorykeepAppPreview() {
    StorykeepTheme {
        StorykeepApp()
    }
}
