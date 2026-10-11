package com.storykeep.junior.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

/**
 * The Storykeep API surface the Junior app calls.
 *
 * Paths are relative to BuildConfig.BASE_URL (…/api/v1/). Slice 1 added the
 * auth probe; this slice adds the two Talk endpoints — clip STT in, TTS
 * audio out. Conversation and Stories endpoints land in slices 3–4.
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
