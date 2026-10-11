package com.storykeep.junior.data

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.storykeep.junior.audio.NoopTalkPlayer
import com.storykeep.junior.audio.TalkPlayer
import com.storykeep.junior.audio.TalkRecorder
import com.storykeep.junior.network.ApiCallException
import com.storykeep.junior.network.ApiError
import com.storykeep.junior.network.ConversationTransport
import com.storykeep.junior.network.JuniorDocumentDto
import com.storykeep.junior.network.JuniorProjectDto
import com.storykeep.junior.network.JuniorSharedMessageDto
import com.storykeep.junior.network.JuniorSharedThreadDto
import com.storykeep.junior.network.NetworkConversationTransport
import com.storykeep.junior.network.NetworkStoryTransport
import com.storykeep.junior.network.NetworkTalkTransport
import com.storykeep.junior.network.StoryTransport
import com.storykeep.junior.network.TalkResult
import com.storykeep.junior.network.TalkTransport
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.SerializationException
import java.util.UUID

/**
 * One message on screen, mapped from the shared-memory API
 * ([JuniorSharedMessageDto]) or kept locally when a post could not send.
 * [fromJunior] mirrors the backend role: "junior" is Junior, "user" is you.
 */
data class ConversationMessage(
    val id: String,
    val fromJunior: Boolean,
    val text: String,
    val createdAt: String? = null,
)

/**
 * UI-facing session. Talk rules live in [TalkSessionCore].
 *
 * Talk is real: a tap records a mic clip, the clip goes to the backend STT
 * endpoint, the real transcript replaces the local fake, and Junior's reply
 * is spoken through the backend TTS endpoint. Every network call runs off
 * the main thread through [TalkTransport] / safeApiCall.
 *
 * Conversation is real too (slice 3): opening the screen loads the first
 * project, its first thread, and that thread's real message history through
 * [ConversationTransport]; sending a typed message posts to the backend and
 * the returned user + Junior messages replace the placeholder transcript.
 * Loading and failures surface honestly through [conversationLoading] /
 * [conversationError].
 *
 * Stories are real (slice 4): the Stories screen lists real documents from
 * the shared-memory API through [StoryTransport] — the backend is the source
 * of truth, there is no on-device story store. Saving a story from
 * Conversation posts to the real create-or-update route
 * (`POST /junior/documents`, upsert by slug); loading and failures surface
 * honestly through [storiesLoading] / [storiesError].
 *
 * Product lock: Talk dies on Type / End / leave / lock / network loss, and
 * an offline STT/TTS call kills it with [TalkKillReason.NetworkLost]. No new
 * kill reasons. The Conversation venue never adds kill reasons of its own.
 */
class JuniorSession(
    private val talkTransport: TalkTransport = NetworkTalkTransport(),
    private val conversationTransport: ConversationTransport = NetworkConversationTransport(),
    private val storyTransport: StoryTransport = NetworkStoryTransport(),
    private val recorder: TalkRecorder = TalkRecorder(),
    private val player: TalkPlayer = NoopTalkPlayer(),
) : ViewModel() {
    private val core = TalkSessionCore()

    private var turnJob: Job? = null
    private var conversationJob: Job? = null
    private var sendJob: Job? = null
    private var storiesJob: Job? = null
    private var saveStoryJob: Job? = null

    var bottomTab: BottomTab by mutableStateOf(BottomTab.Talk)
        private set

    var lastSpoke: String by mutableStateOf("Last time we spoke — a placeholder until the first save.")
        private set

    /** Real saved stories (documents) from the shared-memory API, newest first. */
    var stories: List<JuniorDocumentDto> by mutableStateOf(emptyList())
        private set

    /** True while the Stories list load is in flight. */
    var storiesLoading: Boolean by mutableStateOf(false)
        private set

    /** The last mapped Stories failure, or null. Offline shows a retry. */
    var storiesError: ApiError? by mutableStateOf(null)
        private set

    /** True while a story save (POST /junior/documents) is in flight. */
    var storiesSaving: Boolean by mutableStateOf(false)
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

    // ---- Conversation venue state (slice 3) ----

    /** True while a conversation load (project → threads → messages) is in flight. */
    var conversationLoading: Boolean by mutableStateOf(false)
        private set

    /** The last mapped conversation failure, or null. Offline shows a retry. */
    var conversationError: ApiError? by mutableStateOf(null)
        private set

    /** The active project (the first one the backend returns). */
    var project: JuniorProjectDto? by mutableStateOf(null)
        private set

    /** Real threads on [project], from the API. */
    var threads: List<JuniorSharedThreadDto> by mutableStateOf(emptyList())
        private set

    /** The thread whose history is on screen; null before the first load. */
    var activeThread: JuniorSharedThreadDto? by mutableStateOf(null)
        private set

    /** The real message history of [activeThread], oldest first, plus turns posted this session. */
    var messages: List<ConversationMessage> by mutableStateOf(emptyList())
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
        // Slice 3: the Conversation screen opens on real shared-memory data.
        loadConversation()
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

    /**
     * Sends the typed draft to the real backend thread.
     *
     * The product lock still fires first — typing kills Talk with
     * [TalkKillReason.Type], exactly as before — but the message no longer
     * gets a local placeholder reply: it posts through
     * [conversationTransport] and the response's user + Junior messages
     * become the transcript. With no loaded thread (or a failed post) the
     * message stays local and the failure is surfaced honestly.
     */
    fun sendTyped() {
        core.beginTyping()
        val text = core.draft.trim()
        core.updateDraft("")
        publish()
        if (text.isEmpty()) return
        postTypedMessage(text)
    }

    /**
     * Saves the current transcript as a story through the real backend:
     * `POST /junior/documents` (upsert by slug). Returns false when there is
     * nothing to save; true means the save started.
     *
     * The post runs on viewModelScope (off the main thread); the returned
     * document is prepended to [stories] and [savedThisTurn] is marked only
     * on success. A failed save surfaces honestly through [storiesError] and
     * leaves the turn unsaved, so the caller can try again.
     */
    fun saveAsStory(): Boolean {
        val body = conversationBody().ifBlank { return false }
        val title = conversationTitle()
        saveStoryJob?.cancel()
        saveStoryJob = viewModelScope.launch {
            storiesSaving = true
            storyTransport.saveStory(
                slug = storySlug(title),
                title = title,
                text = body,
            ).fold(
                onSuccess = { saved ->
                    stories = listOf(saved) + stories.filterNot { it.slug == saved.slug }
                    storiesError = null
                    lastSpoke = "Last time we spoke — just now. You saved a transcript."
                    core.markSaved()
                    publish()
                },
                onFailure = { error ->
                    storiesError = apiErrorOf(error)
                },
            )
            storiesSaving = false
        }
        return true
    }

    /**
     * Loads the Stories list: `GET /junior/documents`, first page. The
     * backend is the source of truth — no on-device story store exists
     * anymore. Off-main-thread via viewModelScope; a failure maps onto
     * [storiesError] and the previous list stays on screen.
     */
    fun loadStories() {
        storiesJob?.cancel()
        storiesJob = viewModelScope.launch {
            storiesLoading = true
            storiesError = null
            storyTransport.listStories().fold(
                onSuccess = { docs -> stories = docs },
                onFailure = { error -> storiesError = apiErrorOf(error) },
            )
            storiesLoading = false
        }
    }

    /** Re-runs [loadStories] — the retry affordance for an error state. */
    fun retryStories() {
        loadStories()
    }

    /**
     * Loads the conversation surface: first project → its first thread →
     * that thread's history. Off-main-thread via viewModelScope; a failure
     * at any step maps onto [conversationError] and stops the load.
     */
    fun loadConversation() {
        conversationJob?.cancel()
        conversationJob = viewModelScope.launch {
            conversationLoading = true
            conversationError = null
            val firstProject = conversationTransport.projects()
                .getOrElse { failConversation(it); return@launch }
                .firstOrNull()
            if (firstProject == null) {
                project = null
                threads = emptyList()
                activeThread = null
                messages = emptyList()
                conversationLoading = false
                return@launch
            }
            project = firstProject
            val threadList = conversationTransport.threads(firstProject.slug)
                .getOrElse { failConversation(it); return@launch }
            threads = threadList
            activeThread = threadList.firstOrNull()
            loadThreadMessages(firstProject.slug, activeThread?.id)
            conversationLoading = false
        }
    }

    /** Switches the visible thread and reloads its history. */
    fun selectThread(thread: JuniorSharedThreadDto) {
        val slug = project?.slug ?: return
        activeThread = thread
        conversationJob?.cancel()
        conversationJob = viewModelScope.launch {
            conversationLoading = true
            conversationError = null
            loadThreadMessages(slug, thread.id)
            conversationLoading = false
        }
    }

    /** Re-runs [loadConversation] — the retry affordance for an error state. */
    fun retryConversation() {
        loadConversation()
    }

    private suspend fun loadThreadMessages(slug: String, threadId: String?) {
        if (threadId == null) {
            messages = emptyList()
            return
        }
        val rows = conversationTransport.messages(slug, threadId)
            .getOrElse { failConversation(it); return }
        messages = rows.map { it.toConversationMessage() }
    }

    private fun postTypedMessage(text: String) {
        val slug = project?.slug
        val thread = activeThread
        if (slug == null || thread == null) {
            // No real thread loaded yet: keep the turn local so nothing is lost.
            appendLocalMessage(fromJunior = false, text = text)
            appendLocalMessage(fromJunior = true, text = NO_THREAD_REPLY)
            return
        }
        // One send at a time: a new draft supersedes an in-flight post.
        sendJob?.cancel()
        sendJob = viewModelScope.launch {
            conversationTransport.postMessage(slug, thread.id, text).fold(
                onSuccess = { turn ->
                    messages = messages +
                        turn.userMessage.toConversationMessage() +
                        (turn.juniorMessage?.toConversationMessage() ?: emptyList())
                },
                onFailure = { error ->
                    conversationError = apiErrorOf(error)
                    appendLocalMessage(fromJunior = false, text = text)
                    appendLocalMessage(fromJunior = true, text = sendFailedReply(apiErrorOf(error)))
                },
            )
        }
    }

    private fun appendLocalMessage(fromJunior: Boolean, text: String) {
        messages = messages + ConversationMessage(
            id = "local-" + UUID.randomUUID(),
            fromJunior = fromJunior,
            text = text,
        )
    }

    private fun failConversation(error: Throwable) {
        conversationError = apiErrorOf(error)
        conversationLoading = false
    }

    private fun apiErrorOf(throwable: Throwable): ApiError =
        (throwable as? ApiCallException)?.error
            ?: ApiError.Malformed(SerializationException(throwable.message ?: "conversation call failed"))

    private fun conversationBody(): String = buildString {
        messages.forEach { message ->
            append(if (message.fromJunior) "Junior: " else "You: ")
            append(message.text)
            append("\n")
        }
        append(core.transcriptBody())
    }.trim()

    private fun conversationTitle(): String =
        messages.firstOrNull { !it.fromJunior }?.text?.take(42)
            ?: core.transcriptTitle()

    private fun JuniorSharedMessageDto.toConversationMessage(): ConversationMessage =
        ConversationMessage(
            id = id,
            fromJunior = role == ROLE_JUNIOR,
            text = content,
            createdAt = createdAt,
        )

    private fun sendFailedReply(error: ApiError): String = when (error) {
        is ApiError.Offline -> "You're offline — the message stayed on the device. Try again when you're back."
        is ApiError.Unauthorized -> "The app's service token was rejected, so the message could not be saved."
        is ApiError.Http -> "The conversation service answered ${error.code}. Try that again."
        is ApiError.Malformed -> "The reply could not be read. Try that again."
    }

    companion object {
        /** The backend's message roles (junior_shared_memory stores "user" / "junior"). */
        const val ROLE_JUNIOR = "junior"

        private const val NO_THREAD_REPLY =
            "No thread is loaded yet, so this stayed on the device. It will send once a conversation loads."

        /** Max slug length the backend accepts (JuniorDocumentIn.slug max_length=64). */
        private const val SLUG_MAX = 63

        /**
         * Derives a document slug from a story title: lowercase, spaces and
         * runs of non-alphanumerics collapse to single hyphens, trimmed to
         * the backend's 64-char limit. An all-symbol title falls back to
         * "story" so the slug is never empty (the backend rejects it).
         */
        private fun storySlug(title: String): String {
            val cleaned = title.lowercase()
                .map { if (it.isLetterOrDigit()) it else '-' }
                .joinToString("")
                .split('-')
                .filter { it.isNotEmpty() }
                .joinToString("-")
                .take(SLUG_MAX)
                .trim('-')
            return cleaned.ifEmpty { "story" }
        }
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
        // The Talk reply wording stays local on purpose: Talk is a separate
        // venue and slice 3 wired only the typed Conversation path. The
        // voice still comes from the real TTS endpoint.
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
