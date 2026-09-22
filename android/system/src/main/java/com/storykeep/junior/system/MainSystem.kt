package com.storykeep.junior.system

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
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
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

/**
 * Main Talk / Type system component. Screens host this; they do not reimplement
 * mic, listen, type-to-kill, or save chrome.
 */
@Composable
fun MainSystem(
    host: MainSystemHost,
    onBack: () -> Unit,
    onEnd: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val snapshot = MainSystemSnapshot.of(host)
    val focusRequester = remember { FocusRequester() }
    val keyboard = LocalSoftwareKeyboardController.current
    val listState = rememberLazyListState()

    LaunchedEffect(snapshot.typeMode, host.lines.size) {
        if (host.lines.isNotEmpty()) {
            listState.animateScrollToItem(host.lines.lastIndex)
        }
    }

    LaunchedEffect(snapshot.typeMode) {
        if (snapshot.typeMode) {
            focusRequester.requestFocus()
            keyboard?.show()
        } else {
            keyboard?.hide()
        }
    }

    Column(
        modifier = modifier
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
                Text(snapshot.stateLabel, style = StorykeepTypography.bodyMedium, color = InkMuted)
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
            items(host.lines, key = { it.id }) { line ->
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
                onClick = { host.tapTalkControl() },
                enabled = snapshot.talkEnabled,
                modifier = Modifier.size(64.dp),
                colors = IconButtonDefaults.filledIconButtonColors(
                    containerColor = if (host.voiceState == VoiceState.Listening) DeepInk else Amber,
                    contentColor = if (host.voiceState == VoiceState.Listening) PaperCream else OnAmber,
                    disabledContainerColor = PaperLine,
                    disabledContentColor = InkSoft,
                ),
            ) {
                Icon(
                    imageVector = if (snapshot.talkEnabled) Icons.Outlined.Mic else Icons.Outlined.MicOff,
                    contentDescription = if (snapshot.talkEnabled) "Talk control" else "Microphone off",
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(text = snapshot.talkHint, style = StorykeepTypography.bodyMedium)
            }
        }
        OutlinedTextField(
            value = host.draft,
            onValueChange = host::updateDraft,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .focusRequester(focusRequester)
                .onFocusChanged { focus ->
                    if (focus.isFocused) {
                        host.beginTyping()
                    }
                },
            placeholder = { Text("Write to Junior") },
            trailingIcon = {
                IconButton(
                    onClick = { host.sendTyped() },
                    enabled = !snapshot.draftBlank,
                ) {
                    Icon(Icons.Outlined.Keyboard, contentDescription = "Send", tint = DeepInk)
                }
            },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = { host.sendTyped() }),
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
                onClick = { host.toggleListen() },
                enabled = snapshot.talkEnabled,
            ) {
                Icon(
                    imageVector = if (host.listenOn && snapshot.talkEnabled) {
                        Icons.AutoMirrored.Outlined.VolumeUp
                    } else {
                        Icons.AutoMirrored.Outlined.VolumeOff
                    },
                    contentDescription = null,
                    tint = if (!snapshot.talkEnabled || !host.listenOn) InkSoft else Amber,
                )
                Spacer(Modifier.size(6.dp))
                Text(
                    text = snapshot.listenLabel,
                    color = if (!snapshot.talkEnabled) InkSoft else DeepInk,
                )
            }
            OutlinedButton(
                onClick = { host.saveAsStory() },
                enabled = snapshot.hasTranscript,
            ) {
                Text(snapshot.saveLabel)
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
