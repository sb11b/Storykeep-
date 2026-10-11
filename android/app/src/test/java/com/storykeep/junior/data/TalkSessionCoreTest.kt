package com.storykeep.junior.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class TalkSessionCoreTest {
    @Test
    fun openTalkIsAliveWithListenAvailable() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        assertTrue(core.talkAlive)
        assertEquals(EntryMode.Talk, core.entryMode)
        assertEquals(VoiceState.Idle, core.voiceState)
        assertFalse(core.listenOn)
    }

    @Test
    fun openTypeNeverStartsTalk() {
        val core = TalkSessionCore()
        core.open(EntryMode.Type)
        assertFalse(core.talkAlive)
        assertEquals(EntryMode.Type, core.entryMode)
        assertTrue(core.keyboardPreferred)
    }

    @Test
    fun typingKillsTalkAndTurnsListenOff() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.tapTalkControl()
        core.toggleListen()
        assertEquals(VoiceState.Listening, core.voiceState)
        assertTrue(core.listenOn)
        core.updateDraft("hello")
        assertFalse(core.talkAlive)
        assertEquals(EntryMode.Type, core.entryMode)
        assertEquals(VoiceState.Idle, core.voiceState)
        assertFalse(core.listenOn)
        assertEquals(TalkKillReason.Type, core.lastKillReason)
        assertEquals("hello", core.draft)
        assertTrue(core.lines.isNotEmpty())
    }

    @Test
    fun sendTypedKeepsTranscriptAndKillsTalk() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.updateDraft("Keep the river note")
        core.sendTyped()
        assertFalse(core.talkAlive)
        assertEquals(EntryMode.Type, core.entryMode)
        assertTrue(core.lines.any { !it.fromJunior && it.text == "Keep the river note" })
        assertEquals("", core.draft)
    }

    @Test
    fun endClearsTheTurn() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.tapTalkControl()
        core.tapTalkControl()
        core.appendLine(fromJunior = false, text = "we walked the river path")
        core.appendLine(fromJunior = true, text = "That's a keeper.")
        assertTrue(core.lines.size > 1)
        core.killTalk(TalkKillReason.End)
        assertFalse(core.talkAlive)
        assertTrue(core.lines.isEmpty())
        assertEquals(EntryMode.Talk, core.entryMode)
        assertEquals(TalkKillReason.End, core.lastKillReason)
    }

    @Test
    fun lockAndNetworkLossKeepTranscript() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.tapTalkControl()
        core.tapTalkControl()
        core.appendLine(fromJunior = false, text = "we walked the river path")
        val kept = core.lines.size
        core.killTalk(TalkKillReason.Lock)
        assertFalse(core.talkAlive)
        assertEquals(kept, core.lines.size)
        assertEquals(TalkKillReason.Lock, core.lastKillReason)
        core.open(EntryMode.Talk)
        core.tapTalkControl()
        core.killTalk(TalkKillReason.NetworkLost)
        assertFalse(core.talkAlive)
        assertEquals(TalkKillReason.NetworkLost, core.lastKillReason)
        assertTrue(core.lines.isNotEmpty())
    }

    @Test
    fun tapTalkDoesNothingAfterKill() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.killTalk(TalkKillReason.NetworkLost)
        core.tapTalkControl()
        assertEquals(VoiceState.Idle, core.voiceState)
        assertFalse(core.talkAlive)
    }

    @Test
    fun tappingTheControlAloneAppendsNoTranscript() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        val before = core.lines.size
        core.tapTalkControl() // Idle -> Listening
        core.tapTalkControl() // Listening -> Speaking
        assertEquals(VoiceState.Speaking, core.voiceState)
        // The fake turn is gone: only a real appendLine grows the transcript.
        assertEquals(before, core.lines.size)
    }

    @Test
    fun appendLineCarriesTheRealTranscriptAndTrims() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.appendLine(fromJunior = false, text = "  we walked the river path  ")
        core.appendLine(fromJunior = true, text = "That's a keeper.")
        assertEquals(3, core.lines.size) // greeting + two real lines
        assertEquals("we walked the river path", core.lines[1].text)
        assertFalse(core.lines[1].fromJunior)
        assertTrue(core.lines[2].fromJunior)
    }

    @Test
    fun appendLineIsRefusedOnceTalkIsDead() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.killTalk(TalkKillReason.NetworkLost)
        core.appendLine(fromJunior = false, text = "a late reply must not land")
        assertTrue(core.lines.none { it.text.contains("late reply") })
    }

    @Test
    fun aFailedMicOpenSettlesBackToIdleWithoutKillingTalk() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.tapTalkControl() // Idle -> Listening
        core.cancelListening() // mic would not open
        assertEquals(VoiceState.Idle, core.voiceState)
        assertTrue(core.talkAlive)
        assertEquals(null, core.lastKillReason)
    }

    @Test
    fun settleVoiceOnlyDropsALiveSpeakingTurn() {
        val core = TalkSessionCore()
        core.open(EntryMode.Talk)
        core.tapTalkControl()
        core.tapTalkControl()
        core.settleVoice()
        assertEquals(VoiceState.Idle, core.voiceState)
        assertTrue(core.talkAlive)
    }
}
