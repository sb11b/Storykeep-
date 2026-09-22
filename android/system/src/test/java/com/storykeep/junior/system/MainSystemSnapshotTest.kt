package com.storykeep.junior.system

import com.storykeep.junior.data.EntryMode
import com.storykeep.junior.data.TalkKillReason
import com.storykeep.junior.data.TalkSessionCore
import com.storykeep.junior.data.TranscriptLine
import com.storykeep.junior.data.VoiceState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MainSystemSnapshotTest {
    @Test
    fun talkOpenShowsReadyAndEnablesMic() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        val snap = MainSystemSnapshot.of(FakeHost.from(core))
        assertTrue(snap.talkEnabled)
        assertEquals("Ready", snap.stateLabel)
        assertEquals("Tap to listen (stub)", snap.talkHint)
        assertEquals("Listen", snap.listenLabel)
        assertEquals("Save as story", snap.saveLabel)
    }

    @Test
    fun typeModeDisablesTalkChrome() {
        val core = TalkSessionCore()
        core.open(EntryMode.Type)
        val snap = MainSystemSnapshot.of(FakeHost.from(core))
        assertTrue(snap.typeMode)
        assertFalse(snap.talkEnabled)
        assertEquals("Typing · mic off · sound off", snap.stateLabel)
        assertEquals("Talk control is off", snap.talkHint)
        assertEquals("Listen off", snap.listenLabel)
    }

    @Test
    fun lockKeepsTranscriptButKillsTalkChrome() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.tapTalkControl()
        core.tapTalkControl()
        core.killTalk(TalkKillReason.Lock)
        val snap = MainSystemSnapshot.of(FakeHost.from(core))
        assertFalse(snap.talkEnabled)
        assertTrue(snap.hasTranscript)
        assertEquals("Talk ended · app locked or left", snap.stateLabel)
    }

    @Test
    fun networkLossLabelAndSavedFlag() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.tapTalkControl()
        core.tapTalkControl()
        core.killTalk(TalkKillReason.NetworkLost)
        core.markSaved()
        val snap = MainSystemSnapshot.of(FakeHost.from(core))
        assertEquals("Talk ended · network lost", snap.stateLabel)
        assertEquals("Saved", snap.saveLabel)
        assertTrue(snap.hasTranscript)
    }

    private class FakeHost(
        override val entryMode: EntryMode,
        override val voiceState: VoiceState,
        override val listenOn: Boolean,
        override val draft: String,
        override val lines: List<TranscriptLine>,
        override val savedThisTurn: Boolean,
        override val talkAlive: Boolean,
        override val lastKillReason: TalkKillReason?,
    ) : MainSystemHost {
        override fun updateDraft(value: String) = Unit
        override fun beginTyping() = Unit
        override fun toggleListen() = Unit
        override fun tapTalkControl() = Unit
        override fun sendTyped() = Unit
        override fun saveAsStory(): Boolean = false

        companion object {
            fun from(core: TalkSessionCore) = FakeHost(
                entryMode = core.entryMode,
                voiceState = core.voiceState,
                listenOn = core.listenOn,
                draft = core.draft,
                lines = core.lines,
                savedThisTurn = core.savedThisTurn,
                talkAlive = core.talkAlive,
                lastKillReason = core.lastKillReason,
            )
        }
    }
}
