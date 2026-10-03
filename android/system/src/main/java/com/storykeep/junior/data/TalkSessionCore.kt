package com.storykeep.junior.data

import java.util.UUID

enum class EntryMode { Talk, Type }

enum class VoiceState { Idle, Listening, Speaking }

enum class BottomTab { Talk, Stories, Keep }

enum class TalkKillReason {
    Type,
    End,
    Leave,
    Lock,
    NetworkLost,
}

data class TranscriptLine(
    val id: String = UUID.randomUUID().toString(),
    val fromJunior: Boolean,
    val text: String,
)

/**
 * Talk / Type session rules. No Android or network APIs.
 *
 * Product lock:
 * - Talk will later be Grok STS plus live STT. This core only tracks whether Talk is alive.
 * - Type is the text model; Listen stays off.
 * - Talk dies on Type / End / leave / lock / network loss.
 * - End and leave clear the turn. Lock and network loss keep the transcript so it can still be saved.
 */
class TalkSessionCore {
    var entryMode: EntryMode = EntryMode.Talk
        private set

    var voiceState: VoiceState = VoiceState.Idle
        private set

    var listenOn: Boolean = false
        private set

    var draft: String = ""
        private set

    var lines: List<TranscriptLine> = emptyList()
        private set

    var savedThisTurn: Boolean = false
        private set

    /** True only while a Talk turn is allowed to hold a future STS stream. */
    var talkAlive: Boolean = false
        private set

    var lastKillReason: TalkKillReason? = null
        private set

    val keyboardPreferred: Boolean
        get() = entryMode == EntryMode.Type

    fun open(mode: EntryMode) {
        entryMode = mode
        savedThisTurn = false
        lastKillReason = null
        voiceState = VoiceState.Idle
        listenOn = false
        if (mode == EntryMode.Talk) {
            talkAlive = true
        } else {
            talkAlive = false
        }
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
        if (value.isNotEmpty()) {
            beginTyping()
        }
        draft = value
    }

    /** Keyboard focus or the first typed character switches to Type and kills Talk. */
    fun beginTyping() {
        if (entryMode == EntryMode.Type && !talkAlive) return
        killTalk(TalkKillReason.Type)
        entryMode = EntryMode.Type
    }

    fun toggleListen() {
        if (entryMode == EntryMode.Type || !talkAlive) {
            listenOn = false
            return
        }
        listenOn = !listenOn
    }

    fun tapTalkControl() {
        if (entryMode == EntryMode.Type || !talkAlive) return
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
        beginTyping()
        val text = draft.trim()
        if (text.isEmpty()) return
        draft = ""
        lines = lines + TranscriptLine(fromJunior = false, text = text)
        lines = lines + TranscriptLine(
            fromJunior = true,
            text = "Noted. I will keep that as text only — no voice on Type.",
        )
    }

    fun killTalk(reason: TalkKillReason) {
        talkAlive = false
        voiceState = VoiceState.Idle
        listenOn = false
        lastKillReason = reason
        if (reason == TalkKillReason.Type) {
            entryMode = EntryMode.Type
        }
        if (reason == TalkKillReason.End || reason == TalkKillReason.Leave) {
            draft = ""
            lines = emptyList()
            savedThisTurn = false
            entryMode = EntryMode.Talk
        }
    }

    fun markSaved() {
        savedThisTurn = true
    }

    fun transcriptBody(): String = lines.joinToString("\n") { line ->
        val who = if (line.fromJunior) "Junior" else "You"
        "$who: ${line.text}"
    }

    fun transcriptTitle(): String =
        lines.firstOrNull { !it.fromJunior }?.text?.take(42) ?: "Conversation with Junior"

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
}
