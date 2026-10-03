package com.storykeep.junior.system

import com.storykeep.junior.data.EntryMode
import com.storykeep.junior.data.TalkKillReason
import com.storykeep.junior.data.VoiceState

/**
 * Derived UI state for the main system component. No Compose, no Android APIs.
 */
data class MainSystemSnapshot(
    val entryMode: EntryMode,
    val talkAlive: Boolean,
    val voiceState: VoiceState,
    val lastKillReason: TalkKillReason?,
    val listenOn: Boolean,
    val savedThisTurn: Boolean,
    val hasTranscript: Boolean,
    val draftBlank: Boolean,
) {
    val typeMode: Boolean get() = entryMode == EntryMode.Type
    val talkEnabled: Boolean get() = !typeMode && talkAlive

    val stateLabel: String
        get() = when {
            lastKillReason == TalkKillReason.NetworkLost -> "Talk ended · network lost"
            lastKillReason == TalkKillReason.Lock -> "Talk ended · app locked or left"
            typeMode || !talkAlive -> "Typing · mic off · sound off"
            voiceState == VoiceState.Listening -> "Listening"
            voiceState == VoiceState.Speaking -> "Speaking"
            else -> "Ready"
        }

    val talkHint: String
        get() = if (!talkEnabled) {
            "Talk control is off"
        } else {
            when (voiceState) {
                VoiceState.Idle -> "Tap to listen (stub)"
                VoiceState.Listening -> "Tap to add a fake turn"
                VoiceState.Speaking -> "Tap to settle"
            }
        }

    val listenLabel: String
        get() = when {
            !talkEnabled -> "Listen off"
            listenOn -> "Listen on"
            else -> "Listen"
        }

    val saveLabel: String
        get() = if (savedThisTurn) "Saved" else "Save as story"

    companion object {
        fun of(host: MainSystemHost): MainSystemSnapshot = MainSystemSnapshot(
            entryMode = host.entryMode,
            talkAlive = host.talkAlive,
            voiceState = host.voiceState,
            lastKillReason = host.lastKillReason,
            listenOn = host.listenOn,
            savedThisTurn = host.savedThisTurn,
            hasTranscript = host.lines.isNotEmpty(),
            draftBlank = host.draft.isBlank(),
        )
    }
}
