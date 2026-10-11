package com.storykeep.junior.network

import kotlinx.serialization.SerializationException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.Base64
import java.util.UUID

/**
 * The Talk turn's two network calls: clip STT in, TTS audio out.
 *
 * Deliberately an interface so the session can be driven without Android
 * in unit tests; [NetworkTalkTransport] is the Retrofit implementation and
 * the only place Talk touches the network.
 */
interface TalkTransport {
    /** Sends one recorded clip; [TalkResult.Heard] carries the real transcript. */
    suspend fun transcribe(clip: ByteArray): TalkResult

    /** Speaks [text] through the backend TTS voice. */
    suspend fun speak(text: String): TalkResult
}

/** What a Talk turn can come back as. Every failure shape is [Failed]. */
sealed interface TalkResult {
    /** The clip was understood; [text] is the real transcript. */
    data class Heard(val text: String) : TalkResult

    /** The service answered 200 but heard nothing (silence, clip too short). */
    data object NothingHeard : TalkResult

    /** The reply was synthesized; [audio] is the encoded audio bytes. */
    data class Spoken(val audio: ByteArray, val contentType: String) : TalkResult

    /** A mapped [ApiError] — offline, 401, or any other non-2xx. */
    data class Failed(val error: ApiError) : TalkResult
}

/**
 * Retrofit implementation of [TalkTransport], on top of NetworkModule and
 * [safeApiCall]. All failures come back mapped, never thrown.
 */
class NetworkTalkTransport(
    private val api: StorykeepApi = NetworkModule.api,
) : TalkTransport {

    override suspend fun transcribe(clip: ByteArray): TalkResult {
        val part = MultipartBody.Part.createFormData(
            name = "file",
            filename = "clip.wav",
            body = clip.toRequestBody("audio/wav".toMediaType()),
        )
        return safeApiCall { api.transcribeClip(part) }.fold(
            onSuccess = { dto ->
                if (dto.text.isBlank()) {
                    TalkResult.NothingHeard
                } else {
                    TalkResult.Heard(dto.text)
                }
            },
            onFailure = { throwable -> TalkResult.Failed(apiErrorOf(throwable)) },
        )
    }

    override suspend fun speak(text: String): TalkResult {
        val body = ChatSpeechInDto(
            visibleText = text,
            messageId = UUID.randomUUID().toString(),
        )
        return safeApiCall { api.speakMessage(body) }.fold(
            onSuccess = { dto ->
                val encoded = dto.audio
                if (encoded.isNullOrBlank()) {
                    TalkResult.Failed(
                        ApiError.Malformed(SerializationException("tts response carried no audio")),
                    )
                } else {
                    TalkResult.Spoken(
                        audio = Base64.getDecoder().decode(encoded),
                        contentType = dto.contentType ?: DEFAULT_AUDIO_CONTENT_TYPE,
                    )
                }
            },
            onFailure = { throwable -> TalkResult.Failed(apiErrorOf(throwable)) },
        )
    }

    private fun apiErrorOf(throwable: Throwable): ApiError =
        (throwable as? ApiCallException)?.error
            ?: ApiError.Malformed(SerializationException(throwable.message ?: "talk call failed"))

    private companion object {
        const val DEFAULT_AUDIO_CONTENT_TYPE = "audio/mpeg"
    }
}
