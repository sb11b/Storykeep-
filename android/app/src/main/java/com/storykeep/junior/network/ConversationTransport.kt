package com.storykeep.junior.network

/**
 * The Conversation surface's network calls: projects, project threads,
 * thread messages, and posting a turn.
 *
 * Deliberately an interface so the session can be driven without Android in
 * unit tests; [NetworkConversationTransport] is the Retrofit implementation
 * over [NetworkModule] / [safeApiCall] and the only place the Conversation
 * venue touches the network. Every failure comes back mapped inside
 * [ApiCallException] — never thrown raw.
 *
 * This is the Conversation venue only. The Talk turn keeps its own
 * [TalkTransport]; the two never entangle.
 */
interface ConversationTransport {
    /** The owner's projects; the screen picks the first one. */
    suspend fun projects(): Result<List<JuniorProjectDto>>

    /** Threads on one project, identified by slug. */
    suspend fun threads(slug: String): Result<List<JuniorSharedThreadDto>>

    /** One thread's message history, oldest first. */
    suspend fun messages(slug: String, threadId: String): Result<List<JuniorSharedMessageDto>>

    /** Posts one turn; the response carries the stored messages and reply status. */
    suspend fun postMessage(
        slug: String,
        threadId: String,
        text: String,
    ): Result<JuniorSharedMessagePostOutDto>
}

/**
 * Retrofit implementation of [ConversationTransport]. All calls run through
 * [safeApiCall], so Offline / Unauthorized / Http / Malformed arrive mapped
 * as [ApiError] inside the [Result]'s failure.
 */
class NetworkConversationTransport(
    private val api: StorykeepApi = NetworkModule.api,
) : ConversationTransport {
    override suspend fun projects(): Result<List<JuniorProjectDto>> =
        safeApiCall { api.listProjects() }

    override suspend fun threads(slug: String): Result<List<JuniorSharedThreadDto>> =
        safeApiCall { api.listProjectThreads(slug) }

    override suspend fun messages(
        slug: String,
        threadId: String,
    ): Result<List<JuniorSharedMessageDto>> =
        safeApiCall { api.listProjectThreadMessages(slug, threadId) }

    override suspend fun postMessage(
        slug: String,
        threadId: String,
        text: String,
    ): Result<JuniorSharedMessagePostOutDto> = safeApiCall {
        api.postProjectThreadMessage(
            slug,
            threadId,
            JuniorSharedMessageInDto(content = text, venue = DEFAULT_VENUE),
        )
    }
}
