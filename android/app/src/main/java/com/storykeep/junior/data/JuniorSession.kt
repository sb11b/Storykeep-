package com.storykeep.junior.data

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import com.storykeep.junior.system.MainSystemHost

/**
 * UI-facing session. Talk rules live in [TalkSessionCore].
 * Stories persist through [StoryStore]. No Grok Voice / STS / STT calls.
 */
class JuniorSession(
    private val storyStore: StoryStore = MemoryStoryStore(),
) : ViewModel(), MainSystemHost {
    private val core = TalkSessionCore()

    var bottomTab: BottomTab by mutableStateOf(BottomTab.Talk)
        private set

    var lastSpoke: String by mutableStateOf("Last time we spoke — a placeholder until the first save.")
        private set

    var stories: List<SavedStory> by mutableStateOf(storyStore.load())
        private set

    var weeklyQuestion: String by mutableStateOf(
        "What did you keep this week that you do not want to lose?",
    )
        private set

    override var entryMode: EntryMode by mutableStateOf(core.entryMode)
        private set

    override var voiceState: VoiceState by mutableStateOf(core.voiceState)
        private set

    override var listenOn: Boolean by mutableStateOf(core.listenOn)
        private set

    override var draft: String by mutableStateOf(core.draft)
        private set

    override var lines: List<TranscriptLine> by mutableStateOf(core.lines)
        private set

    override var savedThisTurn: Boolean by mutableStateOf(core.savedThisTurn)
        private set

    override var talkAlive: Boolean by mutableStateOf(core.talkAlive)
        private set

    override var lastKillReason: TalkKillReason? by mutableStateOf(core.lastKillReason)
        private set

    val keyboardPreferred: Boolean
        get() = core.keyboardPreferred

    fun selectTab(tab: BottomTab) {
        bottomTab = tab
    }

    fun openConversation(mode: EntryMode) {
        core.open(mode)
        publish()
    }

    override fun updateDraft(value: String) {
        core.updateDraft(value)
        publish()
    }

    override fun beginTyping() {
        core.beginTyping()
        publish()
    }

    override fun toggleListen() {
        core.toggleListen()
        publish()
    }

    override fun tapTalkControl() {
        core.tapTalkControl()
        publish()
    }

    override fun sendTyped() {
        core.sendTyped()
        publish()
    }

    override fun saveAsStory(): Boolean {
        val body = core.transcriptBody().ifBlank { return false }
        stories = listOf(
            SavedStory(
                title = core.transcriptTitle(),
                body = body,
                whenLabel = "Just now · transcript only",
            ),
        ) + stories
        storyStore.save(stories)
        lastSpoke = "Last time we spoke — just now. You saved a transcript."
        core.markSaved()
        publish()
        return true
    }

    fun leaveConversation() {
        core.killTalk(TalkKillReason.Leave)
        if (bottomTab != BottomTab.Stories) {
            bottomTab = BottomTab.Talk
        }
        publish()
    }

    fun endConversation() {
        core.killTalk(TalkKillReason.End)
        if (bottomTab != BottomTab.Stories) {
            bottomTab = BottomTab.Talk
        }
        publish()
    }

    fun onAppBackgrounded() {
        if (talkAlive) {
            core.killTalk(TalkKillReason.Lock)
            publish()
        }
    }

    fun onNetworkLost() {
        if (talkAlive) {
            core.killTalk(TalkKillReason.NetworkLost)
            publish()
        }
    }

    private fun publish() {
        entryMode = core.entryMode
        voiceState = core.voiceState
        listenOn = core.listenOn
        draft = core.draft
        lines = core.lines
        savedThisTurn = core.savedThisTurn
        talkAlive = core.talkAlive
        lastKillReason = core.lastKillReason
    }
}
