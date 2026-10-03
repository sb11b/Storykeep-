package com.storykeep.junior.ui.conversation

import androidx.compose.runtime.Composable
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.system.MainSystem

@Composable
fun ConversationScreen(
    session: JuniorSession,
    onBack: () -> Unit,
    onEnd: () -> Unit,
) {
    MainSystem(
        host = session,
        onBack = onBack,
        onEnd = onEnd,
    )
}
