package com.storykeep.junior.ui.home

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Keyboard
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.storykeep.junior.data.BottomTab
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.ui.theme.Amber
import com.storykeep.junior.ui.theme.AmberSoft
import com.storykeep.junior.ui.theme.DeepInk
import com.storykeep.junior.ui.theme.OnAmber
import com.storykeep.junior.ui.theme.PaperCream
import com.storykeep.junior.ui.theme.PaperRaised
import com.storykeep.junior.ui.theme.StorykeepTypography
import com.storykeep.junior.ui.navigation.StorykeepBottomBar

@Composable
fun HomeScreen(
    session: JuniorSession,
    onTalk: () -> Unit,
    onType: () -> Unit,
    onStories: () -> Unit,
    onKeep: () -> Unit,
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(PaperCream)
            .statusBarsPadding()
            .navigationBarsPadding(),
    ) {
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                StorykeepMark()
                Text(
                    text = "Junior is here",
                    style = StorykeepTypography.titleMedium,
                    color = DeepInk,
                )
            }
            Spacer(Modifier.height(36.dp))
            PresenceOrb()
            Spacer(Modifier.height(28.dp))
            Text(
                text = "Ready when you are",
                style = StorykeepTypography.headlineMedium,
                textAlign = TextAlign.Center,
            )
            Spacer(Modifier.height(28.dp))
            Button(
                onClick = {
                    session.selectTab(BottomTab.Talk)
                    onTalk()
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(64.dp),
                shape = RoundedCornerShape(20.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = Amber,
                    contentColor = OnAmber,
                ),
            ) {
                Icon(Icons.Outlined.Mic, contentDescription = null)
                Spacer(Modifier.size(10.dp))
                Text("Talk to Junior", style = StorykeepTypography.titleMedium)
            }
            Spacer(Modifier.height(12.dp))
            OutlinedButton(
                onClick = {
                    session.selectTab(BottomTab.Talk)
                    onType()
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(56.dp),
                shape = RoundedCornerShape(18.dp),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = DeepInk),
            ) {
                Icon(Icons.Outlined.Keyboard, contentDescription = null)
                Spacer(Modifier.size(10.dp))
                Text("Type to Junior", style = StorykeepTypography.titleMedium)
            }
            Spacer(Modifier.height(28.dp))
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                color = PaperRaised,
                shadowElevation = 0.dp,
                tonalElevation = 0.dp,
            ) {
                Column(Modifier.padding(18.dp)) {
                    Text(
                        text = "LAST TIME WE SPOKE",
                        style = StorykeepTypography.labelSmall,
                    )
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = session.lastSpoke,
                        style = StorykeepTypography.bodyLarge,
                    )
                }
            }
        }
        StorykeepBottomBar(
            selected = session.bottomTab,
            onTalk = { session.selectTab(BottomTab.Talk) },
            onStories = onStories,
            onKeep = onKeep,
        )
    }
}

@Composable
fun StorykeepMark(modifier: Modifier = Modifier) {
    Canvas(modifier = modifier.size(36.dp)) {
        val stroke = 3.5.dp.toPx()
        drawRoundRect(
            color = DeepInk,
            topLeft = Offset(size.width * 0.22f, size.height * 0.12f),
            size = androidx.compose.ui.geometry.Size(size.width * 0.56f, size.height * 0.76f),
            cornerRadius = androidx.compose.ui.geometry.CornerRadius(8.dp.toPx(), 8.dp.toPx()),
            style = Stroke(width = stroke),
        )
        drawLine(
            color = Amber,
            start = Offset(size.width * 0.22f, size.height * 0.38f),
            end = Offset(size.width * 0.78f, size.height * 0.38f),
            strokeWidth = stroke,
            cap = StrokeCap.Round,
        )
    }
}

@Composable
private fun PresenceOrb() {
    val pulse by rememberInfiniteTransition(label = "presence").animateFloat(
        initialValue = 0.88f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(2200),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "presenceScale",
    )
    Box(
        modifier = Modifier.size(168.dp),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            modifier = Modifier
                .size((168 * pulse).dp)
                .clip(CircleShape)
                .background(AmberSoft.copy(alpha = 0.28f)),
        )
        Box(
            modifier = Modifier
                .size(118.dp)
                .clip(CircleShape)
                .background(PaperRaised),
            contentAlignment = Alignment.Center,
        ) {
            Box(
                modifier = Modifier
                    .size(72.dp)
                    .clip(CircleShape)
                    .background(DeepInk.copy(alpha = 0.08f)),
            )
            Box(
                modifier = Modifier
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(Amber),
            )
        }
    }
}
