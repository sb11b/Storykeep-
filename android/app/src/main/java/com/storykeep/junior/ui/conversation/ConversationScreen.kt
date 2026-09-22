package com.storykeep.junior.ui.conversation

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.VolumeOff
import androidx.compose.material.icons.automirrored.outlined.VolumeUp
import androidx.compose.material.icons.outlined.Keyboard
import androidx.compose.material.icons.outlined.Mic
import androidx.compose.material.icons.outlined.MicOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilledIconButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import com.storykeep.junior.data.EntryMode
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.data.TranscriptLine
import com.storykeep.junior.data.VoiceState
import com.storykeep.junior.ui.theme.Amber
import com.storykeep.junior.ui.theme.DeepInk
import com.storykeep.junior.ui.theme.InkMuted
import com.storykeep.junior.ui.theme.InkSoft
import com.storykeep.junior.ui.theme.OnAmber
import com.storykeep.junior.ui.theme.PaperCream
import com.storykeep.junior.ui.theme.PaperLine
import com.storykeep.junior.ui.theme.PaperRaised
import com.storykeep.junior.ui.theme.StorykeepTypography

@Composable
fun ConversationScreen(
    session: JuniorSession,
    onBack: () -> Unit,
    onEnd: () -> Unit,
) {
    val typeMode = session.entryMode == EntryMode.Type
    val focusRequester = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val listState = rememberLazyListState()

    LaunchedEffect(typeMode, session.lines.size) {
        if (session.lines.isNotEmpty()) {
            listState.animateScrollToItem(session.lines.lastIndex)
        }
    }

    LaunchedEffect(typeMode) {
        if (typeMode) {
            focusRequester.requestFocus()
            keyboard?.show()
        } else {
            keyboard?.hide()
        }
    }

    val stateLabel = when {
        typeMode -> "Typing · mic off · sound off"
        session.voiceState == VoiceState.Listening -> "Listening"
        session.voiceState == VoiceState.Speaking -> "Speaking"
        else -> "Ready"
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(PaperCream)
            .statusBarsPadding()
            .navigationBarsPadding()
            .imePadding(),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Outlined.ArrowBack, contentDescription = "Back", tint = DeepInk)
            }
            Column(Modifier.weight(1f)) {
                Text("Junior", style = StorykeepTypography.titleLarge)
                Text(stateLabel, style = StorykeepTypography.bodyMedium, color = InkMuted)
            }
        }
        HorizontalDivider(color = PaperLine)
        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(session.lines, key = { it.id }) { line ->
                TranscriptBubble(line)
            }
        }
        HorizontalDivider(color = PaperLine)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            val talkEnabled = !typeMode
            FilledIconButton(
                onClick = { session.tapTalkControl() },
                enabled = talkEnabled,
                modifier = Modifier.size(64.dp),
                colors = IconButtonDefaults.filledIconButtonColors(
                    containerColor = if (session.voiceState == VoiceState.Listening) DeepInk else Amber,
                    contentColor = if (session.voiceState == VoiceState.Listening) PaperCream else OnAmber,
                    disabledContainerColor = PaperLine,
                    disabledContentColor = InkSoft,
                ),
            ) {
                Icon(
                    imageVector = if (talkEnabled) Icons.Outlined.Mic else Icons.Outlined.MicOff,
                    contentDescription = if (talkEnabled) "Talk control" else "Microphone off",
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = if (typeMode) "Talk control is off in Type" else talkHint(session.voiceState),
                    style = StorykeepTypography.bodyMedium,
                )
            }
        }
        OutlinedTextField(
            value = session.draft,
            onValueChange = session::updateDraft,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .focusRequester(focusRequester),
            placeholder = { Text("Write to Junior") },
            trailingIcon = {
                IconButton(
                    onClick = { session.sendTyped() },
                    enabled = session.draft.isNotBlank(),
                ) {
                    Icon(Icons.Outlined.Keyboard, contentDescription = "Send", tint = DeepInk)
                }
            },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { session.sendTyped() }),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = Amber,
                unfocusedBorderColor = PaperLine,
                focusedContainerColor = PaperRaised,
                unfocusedContainerColor = PaperRaised,
                cursorColor = DeepInk,
            ),
            shape = RoundedCornerShape(16.dp),
        )
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            TextButton(
                onClick = { session.toggleListen() },
                enabled = !typeMode,
            ) {
                Icon(
                    imageVector = if (session.listenOn && !typeMode) {
                        Icons.AutoMirrored.Outlined.VolumeUp
                    } else {
                        Icons.AutoMirrored.Outlined.VolumeOff
                    },
                    contentDescription = null,
                    tint = if (typeMode || !session.listenOn) InkSoft else Amber,
                )
                Spacer(Modifier.size(6.dp))
                Text(
                    text = if (typeMode) "Listen off" else if (session.listenOn) "Listen on" else "Listen",
                    color = if (typeMode) InkSoft else DeepInk,
                )
            }
            OutlinedButton(
                onClick = { session.saveAsStory() },
                enabled = session.lines.isNotEmpty(),
            ) {
                Text(if (session.savedThisTurn) "Saved" else "Save as story")
            }
        }
        Button(
            onClick = onEnd,
            modifier = Modifier
                .fillMaxWidth()
                .padding(start = 16.dp, end = 16.dp, bottom = 16.dp)
                .height(48.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = DeepInk,
                contentColor = PaperCream,
            ),
            shape = RoundedCornerShape(14.dp),
        ) {
            Text("End")
        }
    }
}

private fun talkHint(state: VoiceState): String = when (state) {
    VoiceState.Idle -> "Tap to listen (stub)"
    VoiceState.Listening -> "Tap to add a fake turn"
    VoiceState.Speaking -> "Tap to settle"
}

@Composable
private fun TranscriptBubble(line: TranscriptLine) {
    val junior = line.fromJunior
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (junior) Arrangement.Start else Arrangement.End,
    ) {
        Surface(
            modifier = Modifier.widthIn(max = 300.dp),
            shape = RoundedCornerShape(
                topStart = 16.dp,
                topEnd = 16.dp,
                bottomStart = if (junior) 4.dp else 16.dp,
                bottomEnd = if (junior) 16.dp else 4.dp,
            ),
            color = if (junior) PaperRaised else Amber.copy(alpha = 0.22f),
        ) {
            Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                Text(
                    text = if (junior) "Junior" else "You",
                    style = StorykeepTypography.labelSmall,
                )
                Text(line.text, style = StorykeepTypography.bodyLarge)
            }
        }
    }
}
