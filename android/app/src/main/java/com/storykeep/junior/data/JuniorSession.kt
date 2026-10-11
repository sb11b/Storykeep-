package com.storykeep.junior.data

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.storykeep.junior.audio.NoopTalkPlayer
import com.storykeep.junior.audio.TalkPlayer
import com.storykeep.junior.audio.TalkRecorder
import com.storykeep.junior.network.ApiError
import com.storykeep.junior.network.NetworkTalkTransport
import com.storykeep.junior.network.TalkResult
import com.storykeep.junior.network.TalkTransport
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * UI-facing session. Talk rules live in [TalkSessionCore].
 *
 * Talk is real: a tap records a mic clip, the clip goes to the backend STT
 * endpoint, the real transcript replaces the local fake, and Junior's reply
 * is spoken through the backend TTS endpoint. Every network call runs off
 * the main thread through [TalkTransport] / safeApiCall. The reply *wording*
 * is still local until slice 3 wires the chat endpoint — the voice is real.
 *
 * Product lock: Talk dies on Type / End / leave / lock / network loss, and
 * an offline STT/TTS call kills it with [TalkKillReason.NetworkLost]. No new
 * kill reasons.
 */
class JuniorSession(
    private val storyStore: StoryStore = MemoryStoryStore(),
    private val talkTransport: TalkTransport = NetworkTalkTransport(),
    private val recorder: TalkRecorder = TalkRecorder(),
    private val player: TalkPlayer = NoopTalkPlayer(),
) : ViewModel() {
    private val core = TalkSessionCore()

    private var turnJob: Job? = null

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

    var entryMode: EntryMode by mutableStateOf(core.entryMode)
        private set

    var voiceState: VoiceState by mutableStateOf(core.voiceState)
        private set

    var listenOn: Boolean by mutableStateOf(core.listenOn)
        private set

    var draft: String by mutableStateOf(core.draft)
        private set

    var lines: List<TranscriptLine> by mutableStateOf(core.lines)
        private set

    var savedThisTurn: Boolean by mutableStateOf(core.savedThisTurn)
        private set

    var talkAlive: Boolean by mutableStateOf(core.talkAlive)
        private set

    var lastKillReason: TalkKillReason? by mutableStateOf(core.lastKillReason)
        private set

    val keyboardPreferred: Boolean
        get() = core.keyboardPreferred

    fun selectTab(tab: BottomTab) {
        bottomTab = tab
    }

    fun openConversation(mode: EntryMode) {
        haltAudio()
        core.open(mode)
        publish()
    }

    fun updateDraft(value: String) {
        core.updateDraft(value)
        publish()
    }

    fun beginTyping() {
        haltAudio()
        core.beginTyping()
        publish()
    }

    fun toggleListen() {
        core.toggleListen()
        publish()
    }

    /**
     * One Talk turn: Idle → Listening opens the mic, Listening → Speaking
     * sends the clip to STT and speaks Junior's reply, Speaking → Idle
     * settles. A mic that cannot open (permission denied) drops straight
     * back to Idle without killing Talk.
     */
    fun tapTalkControl() {
        val previous = core.voiceState
        core.tapTalkControl()
        when {
            core.voiceState == VoiceState.Listening && previous == VoiceState.Idle -> {
                if (!recorder.start()) {
                    core.cancelListening()
                }
            }
            core.voiceState == VoiceState.Speaking && previous == VoiceState.Listening -> runTurn()
            core.voiceState == VoiceState.Idle && previous == VoiceState.Speaking -> player.stop()
        }
        publish()
    }

    fun sendTyped() {
        core.sendTyped()
        publish()
    }

    fun saveAsStory(): Boolean {
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
        haltAudio()
        core.killTalk(TalkKillReason.Leave)
        if (bottomTab != BottomTab.Stories) {
            bottomTab = BottomTab.Talk
        }
        publish()
    }

    fun endConversation() {
        haltAudio()
        core.killTalk(TalkKillReason.End)
        if (bottomTab != BottomTab.Stories) {
            bottomTab = BottomTab.Talk
        }
        publish()
    }

    fun onAppBackgrounded() {
        haltAudio()
        if (talkAlive) {
            core.killTalk(TalkKillReason.Lock)
            publish()
        }
    }

    fun onNetworkLost() {
        haltAudio()
        if (talkAlive) {
            core.killTalk(TalkKillReason.NetworkLost)
            publish()
        }
    }

    override fun onCleared() {
        haltAudio()
        super.onCleared()
    }

    /**
     * Stops capture, playback, and any in-flight turn so no late reply lands.
     *
     * Called only from main-thread lifecycle callbacks, so the mic stop must
     * not join the pump thread here: [TalkRecorder.halt] merely signals and
     * the pump thread owns stop+release, which keeps this off the main
     * thread's critical path. The clip is discarded — kill paths never
     * record.
     */
    private fun haltAudio() {
        turnJob?.cancel()
        turnJob = null
        recorder.halt()
        player.stop()
    }

    private fun runTurn() {
        turnJob = viewModelScope.launch {
            // Joining the mic reader can block briefly — keep it off the main thread.
            val clip = withContext(Dispatchers.IO) { recorder.stop() }
            if (clip.isEmpty()) {
                core.settleVoice()
                publish()
                return@launch
            }
            when (val heard = talkTransport.transcribe(clip)) {
                is TalkResult.Heard -> {
                    core.appendLine(fromJunior = false, text = heard.text)
                    publish()
                    speakReply(heard.text)
                }
                is TalkResult.NothingHeard -> {
                    core.settleVoice()
                    publish()
                }
                is TalkResult.Failed -> handleTurnFailure(heard.error)
                is TalkResult.Spoken -> Unit // transcribe never returns this shape
            }
        }
    }

    private suspend fun speakReply(transcript: String) {
        // Slice 3 replaces this wording with the chat endpoint's reply; the
        // voice already comes from the real TTS endpoint.
        val reply = "I heard: $transcript. What else do you want to keep?"
        when (val spoken = talkTransport.speak(reply)) {
            is TalkResult.Spoken -> {
                core.appendLine(fromJunior = true, text = reply)
                player.play(spoken.audio)
                core.settleVoice()
            }
            is TalkResult.Failed -> handleTurnFailure(spoken.error)
            is TalkResult.Heard, is TalkResult.NothingHeard -> Unit // speak never returns these
        }
        publish()
    }

    /**
     * Maps a turn failure onto the product lock: an offline call is a real
     * network loss and kills Talk; anything else keeps Talk alive and says
     * so, because the kill reasons are fixed.
     */
    private fun handleTurnFailure(error: ApiError) {
        when (error) {
            is ApiError.Offline -> core.killTalk(TalkKillReason.NetworkLost)
            is ApiError.Unauthorized -> core.appendLine(
                fromJunior = true,
                text = "I can't reach my voice service — the app's service token needs checking.",
            )
            is ApiError.Http, is ApiError.Malformed -> core.appendLine(
                fromJunior = true,
                text = "The voice service stumbled. Try that again.",
            )
        }
        core.settleVoice()
        publish()
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
