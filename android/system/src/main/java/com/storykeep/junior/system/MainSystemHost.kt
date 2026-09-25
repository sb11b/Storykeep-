package com.storykeep.junior.system

import com.storykeep.junior.data.EntryMode
import com.storykeep.junior.data.TalkKillReason
import com.storykeep.junior.data.TranscriptLine
import com.storykeep.junior.data.VoiceState

/**
 * App-facing contract for the main Talk / Type system component.
 * [JuniorSession] implements this; [MainSystem] renders it.
 */
interface MainSystemHost {
    val entryMode: EntryMode
    val voiceState: VoiceState
    val listenOn: Boolean
    val draft: String
    val lines: List<TranscriptLine>
    val savedThisTurn: Boolean
    val talkAlive: Boolean
    val lastKillReason: TalkKillReason?

    fun updateDraft(value: String)
    fun beginTyping()
    fun toggleListen()
    fun tapTalkControl()
    fun sendTyped()
    fun saveAsStory(): Boolean
}
