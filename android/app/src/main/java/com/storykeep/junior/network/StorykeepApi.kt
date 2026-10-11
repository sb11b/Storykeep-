package com.storykeep.junior.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path

/**
 * The Storykeep API surface the Junior app calls.
 *
 * Paths are relative to BuildConfig.BASE_URL (…/api/v1/). Slice 1 added the
 * auth probe; slice 2 the two Talk endpoints (clip STT in, TTS audio out);
 * slice 3 the shared-memory conversation surface — projects, project threads,
 * thread messages, and posting a turn. Stories land in slice 4.
 */
interface StorykeepApi {
    /** Auth probe. Returns 200 with the owner profile, 401 when the token is wrong. */
    @GET("me")
    suspend fun me(): ProfileDto

    /**
     * Clip speech-to-text (backend/app/routers/stt.py: `file: UploadFile`).
     *
     * One multipart part named `file`; the backend derives the format from
     * the part's content type. A 200 carries {"text", "bytes", "mime"}; a
     * clip it could not hear still answers 200 with an empty text plus an
     * "error" key, so callers must read a blank text as "nothing heard",
     * not as a transport failure.
     */
    @Multipart
    @POST("stt")
    suspend fun transcribeClip(@Part audio: MultipartBody.Part): SttClipDto

    /**
     * Junior's spoken reply (backend/app/routers/tts.py `POST /tts/message`).
     *
     * Text in, audio out: the encoded audio comes back base64 inside the
     * JSON body. A failure body ({"ok": false, ...}) arrives with a non-2xx
     * status, so it surfaces as [ApiError.Http].
     */
    @POST("tts/message")
    suspend fun speakMessage(@Body body: ChatSpeechInDto): ChatSpeechDto

    // ---- Conversation (slice 3): shared-memory projects / threads / messages ----

    /**
     * The owner's Junior projects (junior_shared_projects.list_projects →
     * `GET /junior/projects`). The Conversation screen picks the first one.
     */
    @GET("junior/projects")
    suspend fun listProjects(): List<JuniorProjectDto>

    /**
     * Threads on one project (junior_shared_projects.list_project_threads →
     * `GET /junior/projects/{slug}/threads`).
     */
    @GET("junior/projects/{slug}/threads")
    suspend fun listProjectThreads(@Path("slug") slug: String): List<JuniorSharedThreadDto>

    /**
     * One thread's message history, oldest first
     * (junior_shared_projects.list_project_thread_messages →
     * `GET /junior/projects/{slug}/threads/{thread_id}/messages`).
     */
    @GET("junior/projects/{slug}/threads/{threadId}/messages")
    suspend fun listProjectThreadMessages(
        @Path("slug") slug: String,
        @Path("threadId") threadId: String,
    ): List<JuniorSharedMessageDto>

    /**
     * Posts one turn on a project thread
     * (junior_shared_projects.create_project_thread_message →
     * `POST /junior/projects/{slug}/threads/{thread_id}/messages`).
     *
     * The response carries the stored user message plus Junior's reply when
     * the backend produced one; [JuniorSharedMessagePostOutDto.juniorMessage]
     * is null when the reply was deferred.
     */
    @POST("junior/projects/{slug}/threads/{threadId}/messages")
    suspend fun postProjectThreadMessage(
        @Path("slug") slug: String,
        @Path("threadId") threadId: String,
        @Body body: JuniorSharedMessageInDto,
    ): JuniorSharedMessagePostOutDto

    // ---- Stories (slice 4): shared-memory documents ----

    /**
     * The owner's saved stories (junior_shared_documents.list_documents →
     * `GET /junior/documents`). The Stories screen is this list.
     *
     * The backend defaults to limit=50 and sets X-Has-More / X-Next-Cursor
     * response headers for pagination; those are deliberately not modelled
     * here yet — the screen shows the first page only until paging is asked
     * for.
     */
    @GET("junior/documents")
    suspend fun listDocuments(): List<JuniorDocumentDto>

    /**
     * One story by slug (junior_shared_documents.get_document →
     * `GET /junior/documents/{slug}`). A 404 means the slug is not yours.
     */
    @GET("junior/documents/{slug}")
    suspend fun getDocument(@Path("slug") slug: String): JuniorDocumentDto

    /**
     * Creates or updates one story (junior_shared_documents.create_or_update_document →
     * `POST /junior/documents`). The same call creates and updates — the
     * backend upserts by slug — so saving from Conversation posts here and
     * the returned document becomes the truth for that slug.
     */
    @POST("junior/documents")
    suspend fun createOrUpdateDocument(@Body body: JuniorDocumentInDto): JuniorDocumentDto
}

/** Mirrors ProfileOut from backend/app/schemas.py. */
@Serializable
data class ProfileDto(
    val id: String,
    val email: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("legal_name") val legalName: String? = null,
    @SerialName("school_name") val schoolName: String? = null,
    @SerialName("avatar_media_id") val avatarMediaId: String? = null,
)

/** Response of POST /stt. [text] is the real transcript; blank means nothing heard. */
@Serializable
data class SttClipDto(
    val text: String = "",
    val bytes: Int? = null,
    val mime: String? = null,
    val error: String? = null,
)

/** Request body of POST /tts/message — mirrors ChatSpeechIn from schemas.py. */
@Serializable
data class ChatSpeechInDto(
    @SerialName("visible_text") val visibleText: String,
    @SerialName("voice_id") val voiceId: String? = null,
    @SerialName("message_id") val messageId: String,
)

/** Response of POST /tts/message. [audio] is base64-encoded encoded audio. */
@Serializable
data class ChatSpeechDto(
    val audio: String? = null,
    @SerialName("content_type") val contentType: String? = null,
    val chunks: Int? = null,
    val chunk: Int? = null,
    val duration: Double? = null,
)

// ---- Conversation DTOs (slice 3) ----
//
// Every class below mirrors its Pydantic model in backend/app/schemas.py
// field for field: same JSON names, same nullability, same defaults.
// UUIDs and datetimes travel as JSON strings; `meta` is free-form JSON.

/** Mirrors JuniorProjectOut (schemas.py). */
@Serializable
data class JuniorProjectDto(
    val id: String,
    val slug: String,
    @SerialName("display_name") val displayName: String,
    val kind: String,
    @SerialName("repo_url") val repoUrl: String? = null,
    @SerialName("default_branch") val defaultBranch: String,
    val notes: String? = null,
    val meta: Map<String, JsonElement> = emptyMap(),
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

/** Mirrors JuniorSharedThreadOut (schemas.py). */
@Serializable
data class JuniorSharedThreadDto(
    val id: String,
    val title: String? = null,
    @SerialName("venue_last") val venueLast: String,
    val status: String,
    val summary: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

/** Mirrors JuniorSharedMessageOut (schemas.py). [role] is "user" or "junior". */
@Serializable
data class JuniorSharedMessageDto(
    val id: String,
    @SerialName("thread_id") val threadId: String,
    val role: String,
    val content: String,
    val venue: String,
    val meta: Map<String, JsonElement> = emptyMap(),
    @SerialName("created_at") val createdAt: String,
)

/** Request body of a project-thread message post — mirrors JuniorSharedMessageIn (schemas.py). */
@Serializable
data class JuniorSharedMessageInDto(
    val content: String? = null,
    val text: String? = null,
    @SerialName("thread_id") val threadId: String? = null,
    val venue: String? = DEFAULT_VENUE,
    val meta: Map<String, JsonElement> = emptyMap(),
    @SerialName("device_label") val deviceLabel: String? = null,
)

/** Mirrors JuniorSharedMessagePostOut (schemas.py). */
@Serializable
data class JuniorSharedMessagePostOutDto(
    @SerialName("thread_id") val threadId: String,
    @SerialName("user_message") val userMessage: JuniorSharedMessageDto,
    @SerialName("junior_message") val juniorMessage: JuniorSharedMessageDto? = null,
    @SerialName("reply_status") val replyStatus: String,
    val detail: String? = null,
)

/** The backend's default venue (JuniorSharedMessageIn.venue default). */
const val DEFAULT_VENUE = "storykeep"

// ---- Stories DTOs (slice 4) ----
//
// Every class below mirrors its Pydantic model in backend/app/schemas.py
// field for field: same JSON names, same nullability, same defaults.
// UUIDs and datetimes travel as JSON strings.

/**
 * Request body of POST /junior/documents — mirrors JuniorDocumentIn
 * (schemas.py). [slug] identifies the document (1–64 chars); the backend
 * upserts by slug, so a second post with the same slug updates it.
 * [text] defaults to ""; [summary] is optional.
 */
@Serializable
data class JuniorDocumentInDto(
    val slug: String,
    val title: String,
    val text: String = "",
    val summary: String? = null,
)

/**
 * Mirrors JuniorDocumentOut (schemas.py). The list, get, and create/update
 * responses all carry this shape: [id], [createdAt], and [updatedAt] are
 * backend-generated; [summary] is null when none was set.
 */
@Serializable
data class JuniorDocumentDto(
    val id: String,
    val slug: String,
    val title: String,
    val text: String,
    val summary: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)
