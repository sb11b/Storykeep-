package com.storykeep.junior.data

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import java.util.UUID

enum class EntryMode { Talk, Type }

enum class VoiceState { Idle, Listening, Speaking }

enum class BottomTab { Talk, Stories, Keep }

data class TranscriptLine(
    val id: String = UUID.randomUUID().toString(),
    val fromJunior: Boolean,
    val text: String,
)

data class SavedStory(
    val id: String = UUID.randomUUID().toString(),
    val title: String,
    val body: String,
    val whenLabel: String,
)

/**
 * Local shell only. No Grok Voice / STS / STT calls.
 *
 * Product lock (do not reopen):
 * - Talk will later be Grok STS plus live STT.
 * - Type is the text model; Listen stays off.
 * - STS dies on Type / End / leave / lock / network loss.
 * - v1 save-as-story is transcript text only (no audio files).
 */
class JuniorSession : ViewModel() {
    var bottomTab: BottomTab by mutableStateOf(BottomTab.Talk)
        private set

    var lastSpoke: String by mutableStateOf("Last time we spoke — a placeholder until the first save.")
        private set

    var stories: List<SavedStory> by mutableStateOf(seedStories())
        private set

    var weeklyQuestion: String by mutableStateOf(
        "What did you keep this week that you do not want to lose?",
    )
        private set

    var entryMode: EntryMode by mutableStateOf(EntryMode.Talk)
        private set

    var voiceState: VoiceState by mutableStateOf(VoiceState.Idle)
        private set

    var listenOn: Boolean by mutableStateOf(false)
        private set

    var draft: String by mutableStateOf("")
        private set

    var lines: List<TranscriptLine> by mutableStateOf(emptyList())
        private set

    var savedThisTurn: Boolean by mutableStateOf(false)
        private set

    val keyboardPreferred: Boolean
        get() = entryMode == EntryMode.Type

    fun selectTab(tab: BottomTab) {
        bottomTab = tab
    }

    fun openConversation(mode: EntryMode) {
        entryMode = mode
        savedThisTurn = false
        applyModeRules()
        if (lines.isEmpty()) {
            lines = listOf(
                TranscriptLine(
                    fromJunior = true,
                    text = if (mode == EntryMode.Talk) {
                        "I'm here. Talk when you are ready — this turn is a local stub."
                    } else {
                        "Type whenever you like. Listen is off in Type."
                    },
                ),
            )
        }
    }

    fun updateDraft(value: String) {
        draft = value
    }

    fun toggleListen() {
        if (entryMode == EntryMode.Type) {
            listenOn = false
            return
        }
        listenOn = !listenOn
    }

    fun tapTalkControl() {
        if (entryMode == EntryMode.Type) return
        when (voiceState) {
            VoiceState.Idle -> voiceState = VoiceState.Listening
            VoiceState.Listening -> {
                voiceState = VoiceState.Speaking
                appendFakeTalkTurn()
            }
            VoiceState.Speaking -> voiceState = VoiceState.Idle
        }
    }

    fun sendTyped() {
        val text = draft.trim()
        if (text.isEmpty()) return
        draft = ""
        lines = lines + TranscriptLine(fromJunior = false, text = text)
        lines = lines + TranscriptLine(
            fromJunior = true,
            text = "Noted. I will keep that as text only — no voice on Type.",
        )
        voiceState = VoiceState.Idle
        listenOn = false
    }

    fun saveAsStory(): Boolean {
        val body = lines.joinToString("\n") { line ->
            val who = if (line.fromJunior) "Junior" else "You"
            "$who: ${line.text}"
        }.ifBlank { return false }
        val title = lines.firstOrNull { !it.fromJunior }?.text?.take(42)
            ?: "Conversation with Junior"
        stories = listOf(
            SavedStory(
                title = title,
                body = body,
                whenLabel = "Just now · transcript only",
            ),
        ) + stories
        lastSpoke = "Last time we spoke — just now. You saved a transcript."
        savedThisTurn = true
        return true
    }

    fun leaveConversation() {
        voiceState = VoiceState.Idle
        listenOn = false
        draft = ""
        lines = emptyList()
        savedThisTurn = false
        entryMode = EntryMode.Talk
        if (bottomTab != BottomTab.Stories) {
            bottomTab = BottomTab.Talk
        }
    }

    private fun applyModeRules() {
        voiceState = VoiceState.Idle
        listenOn = false
    }

    private fun appendFakeTalkTurn() {
        lines = lines + TranscriptLine(
            fromJunior = false,
            text = "We walked the river path this morning.",
        )
        lines = lines + TranscriptLine(
            fromJunior = true,
            text = "That's a keeper. What did the water sound like?",
        )
    }

    private fun seedStories(): List<SavedStory> = listOf(
        SavedStory(
            title = "River path",
            body = "A placeholder card. Real saves will be transcript text only in v1.",
            whenLabel = "Earlier this month",
        ),
        SavedStory(
            title = "Kitchen light",
            body = "Another local stub so the Stories list can be walked on a device.",
            whenLabel = "Last week",
        ),
    )
}
