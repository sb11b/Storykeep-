package com.storykeep.junior.network

/**
 * The Stories surface's network calls: the document list, one document by
 * slug, and saving (create-or-update) a story.
 *
 * Deliberately an interface so the session can be driven without Android in
 * unit tests; [NetworkStoryTransport] is the Retrofit implementation over
 * [NetworkModule] / [safeApiCall] and the only place the Stories venue
 * touches the network. Every failure comes back mapped inside
 * [ApiCallException] — never thrown raw.
 *
 * This is the Stories venue only. Talk keeps its own [TalkTransport] and
 * Conversation its own [ConversationTransport]; the three never entangle.
 */
interface StoryTransport {
    /** The owner's saved stories (documents), first page. */
    suspend fun listStories(): Result<List<JuniorDocumentDto>>

    /** One story by slug; a 404 (not yours) surfaces as [ApiError.Http]. */
    suspend fun getStory(slug: String): Result<JuniorDocumentDto>

    /**
     * Creates or updates one story. The backend upserts by slug, so this is
     * both the "save a new story" and "edit a story" call. The returned
     * document is the stored truth for that slug.
     */
    suspend fun saveStory(
        slug: String,
        title: String,
        text: String,
        summary: String? = null,
    ): Result<JuniorDocumentDto>
}

/**
 * Retrofit implementation of [StoryTransport]. All calls run through
 * [safeApiCall], so Offline / Unauthorized / Http / Malformed arrive mapped
 * as [ApiError] inside the [Result]'s failure.
 */
class NetworkStoryTransport(
    private val api: StorykeepApi = NetworkModule.api,
) : StoryTransport {
    override suspend fun listStories(): Result<List<JuniorDocumentDto>> =
        safeApiCall { api.listDocuments() }

    override suspend fun getStory(slug: String): Result<JuniorDocumentDto> =
        safeApiCall { api.getDocument(slug) }

    override suspend fun saveStory(
        slug: String,
        title: String,
        text: String,
        summary: String?,
    ): Result<JuniorDocumentDto> = safeApiCall {
        api.createOrUpdateDocument(
            JuniorDocumentInDto(slug = slug, title = title, text = text, summary = summary),
        )
    }
}
