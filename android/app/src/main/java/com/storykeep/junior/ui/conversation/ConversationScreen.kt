package com.storykeep.junior.ui.conversation

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.foundation.rememberScrollState
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
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.storykeep.junior.data.EntryMode
import com.storykeep.junior.data.JuniorSession
import com.storykeep.junior.data.TalkKillReason
import com.storykeep.junior.data.TranscriptLine
import com.storykeep.junior.data.VoiceState
import com.storykeep.junior.network.ApiError
import com.storykeep.junior.network.AuthEvents
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
    val talkEnabled = !typeMode && session.talkAlive
    val focusRequester = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val listState = rememberLazyListState()

    // Talk is real: the mic needs RECORD_AUDIO at runtime (targetSdk 35).
    // The request fires once per screen entry; a denial leaves Talk alive
    // but silent — the session settles the failed mic open back to Idle.
    val context = LocalContext.current
    var micGranted by remember {
        mutableStateOf(
            context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) ==
                PackageManager.PERMISSION_GRANTED,
        )
    }
    val requestMic = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted -> micGranted = granted }
    LaunchedEffect(Unit) {
        if (!micGranted) {
            requestMic.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    LaunchedEffect(session.messages.size, session.lines.size) {
        val total = session.messages.size + session.lines.size
        if (total > 0) {
            listState.animateScrollToItem(total - 1)
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

    val authFlagged by AuthEvents.unauthorized.collectAsState()
    val conversationError = session.conversationError
    val errorBanner: String? = when {
        conversationError is ApiError.Unauthorized || (authFlagged && conversationError != null) ->
            "The app's service token was rejected (401), so the conversation could not load."
        conversationError is ApiError.Offline ->
            "You're offline. The conversation could not load — try again when you're back."
        conversationError is ApiError.Http ->
            "The conversation service answered ${conversationError.code}. Try again."
        conversationError is ApiError.Malformed ->
            "The conversation reply could not be read. Try again."
        else -> null
    }
    val errorIsRetryable = conversationError != null && conversationError !is ApiError.Unauthorized

    val stateLabel = when {
        session.lastKillReason == TalkKillReason.NetworkLost -> "Talk ended · network lost"
        session.lastKillReason == TalkKillReason.Lock -> "Talk ended · app locked or left"
        typeMode || !session.talkAlive -> "Typing · mic off · sound off"
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

        // Slice 3: the real thread list from the shared-memory API.
        if (session.threads.isNotEmpty()) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                session.threads.forEach { thread ->
                    val selected = thread.id == session.activeThread?.id
                    TextButton(
                        onClick = { session.selectThread(thread) },
                        colors = ButtonDefaults.textButtonColors(
                            containerColor = if (selected) Amber.copy(alpha = 0.22f) else PaperRaised,
                            contentColor = if (selected) DeepInk else InkMuted,
                        ),
                    ) {
                        Text(
                            text = thread.title ?: "Untitled thread",
                            style = StorykeepTypography.labelSmall,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
            HorizontalDivider(color = PaperLine)
        }

        LazyColumn(
            state = listState,
            modifier = Modifier
                .weight(1f)
                .fillMaxWidth(),
            contentPadding = PaddingValues(20.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (session.conversationLoading && session.messages.isEmpty()) {
                item(key = "loading") {
                    Box(
                        modifier = Modifier.fillMaxWidth(),
                        contentAlignment = Alignment.Center,
                    ) {
                        CircularProgressIndicator(color = DeepInk)
                    }
                }
            }
            errorBanner?.let { banner ->
                item(key = "error") {
                    Surface(
                        color = PaperRaised,
                        shape = RoundedCornerShape(12.dp),
                    ) {
                        Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                            Text(banner, style = StorykeepTypography.bodyMedium, color = DeepInk)
                            if (errorIsRetryable) {
                                TextButton(onClick = { session.retryConversation() }) {
                                    Text("Try again")
                                }
                            }
                        }
                    }
                }
            }
            if (
                !session.conversationLoading &&
                session.messages.isEmpty() &&
                session.lines.isEmpty() &&
                errorBanner == null
            ) {
                item(key = "empty") {
                    Text(
                        "No messages yet — say hello to Junior.",
                        style = StorykeepTypography.bodyMedium,
                        color = InkMuted,
                    )
                }
            }
            // Real shared-memory history, oldest first.
            items(session.messages, key = { "msg-" + it.id }) { message ->
                TranscriptBubble(
                    TranscriptLine(
                        id = message.id,
                        fromJunior = message.fromJunior,
                        text = message.text,
                    ),
                )
            }
            // The live Talk turn still streams here.
            items(session.lines, key = { "turn-" + it.id }) { line ->
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
                    text = if (!talkEnabled) "Talk control is off" else talkHint(session.voiceState),
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
                .focusRequester(focusRequester)
                .onFocusChanged { focus ->
                    if (focus.isFocused) {
                        session.beginTyping()
                    }
                },
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
                enabled = talkEnabled,
            ) {
                Icon(
                    imageVector = if (session.listenOn && talkEnabled) {
                        Icons.AutoMirrored.Outlined.VolumeUp
                    } else {
                        Icons.AutoMirrored.Outlined.VolumeOff
                    },
                    contentDescription = null,
                    tint = if (!talkEnabled || !session.listenOn) InkSoft else Amber,
                )
                Spacer(Modifier.size(6.dp))
                Text(
                    text = if (!talkEnabled) "Listen off" else if (session.listenOn) "Listen on" else "Listen",
                    color = if (!talkEnabled) InkSoft else DeepInk,
                )
            }
            OutlinedButton(
                onClick = { session.saveAsStory() },
                enabled = !session.storiesSaving &&
                    (session.lines.isNotEmpty() || session.messages.isNotEmpty()),
            ) {
                Text(
                    if (session.savedThisTurn) "Saved" else if (session.storiesSaving) "Saving…" else "Save as story",
                )
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
    VoiceState.Idle -> "Tap to talk"
    VoiceState.Listening -> "Tap when you're done"
    VoiceState.Speaking -> "Junior is replying"
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
