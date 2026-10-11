package com.storykeep.junior.network

import com.storykeep.junior.audio.WavClip
import java.util.Base64
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * The real Talk path: clip → STT, text → TTS. Runs on the JVM — no Android SDK.
 *
 * Proves the two things that can silently break a real Talk turn: that the
 * clip actually reaches the backend STT route and the real transcript comes
 * back (the fake path is gone), and that a 401 surfaces as
 * [ApiError.Unauthorized] rather than a bogus "offline".
 */
class TalkTransportTest {
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        AuthEvents.clear()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun transportFor(token: String): NetworkTalkTransport {
        val api = Retrofit.Builder()
            .baseUrl(server.url("/api/v1/"))
            .client(
                OkHttpClient.Builder()
                    .addInterceptor(AuthInterceptor(token))
                    .addInterceptor(UnauthorizedInterceptor())
                    .build(),
            )
            .addConverterFactory(Json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(StorykeepApi::class.java)
        return NetworkTalkTransport(api)
    }

    private fun clip(): ByteArray = WavClip.encode(ByteArray(32_000) { 7 })

    @Test
    fun `stt clip reaches the backend and returns the real transcript`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"text":"we walked the river path","bytes":32044,"mime":"audio/wav"}"""),
        )

        val result = transportFor(token = "test-token").transcribe(clip())

        assertTrue(result is TalkResult.Heard)
        assertEquals("we walked the river path", (result as TalkResult.Heard).text)

        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertEquals("/api/v1/stt", recorded.path)
        assertEquals("Bearer test-token", recorded.getHeader("Authorization"))
        // Multipart with the part named "file", exactly as the route expects.
        assertTrue(
            recorded.getHeader("Content-Type")!!.startsWith("multipart/form-data"),
        )
        val body = recorded.body.readUtf8()
        assertTrue(body.contains("name=\"file\""))
        assertTrue(body.contains("filename=\"clip.wav\""))
        assertTrue(body.contains("RIFF"))
    }

    @Test
    fun `an unheard clip is nothing heard, not a failure`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"text":"","error":"empty transcript","bytes":32044,"mime":"audio/wav"}"""),
        )

        val result = transportFor(token = "test-token").transcribe(clip())

        assertEquals(TalkResult.NothingHeard, result)
        assertFalse(AuthEvents.unauthorized.value)
    }

    @Test
    fun `stt 401 flags auth events and surfaces as Unauthorized`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Not authenticated"}"""))

        val result = transportFor(token = "wrong-token").transcribe(clip())

        assertTrue(result is TalkResult.Failed)
        val error = (result as TalkResult.Failed).error
        assertEquals(ApiError.Unauthorized, error)
        assertTrue(AuthEvents.unauthorized.value)
    }

    @Test
    fun `stt offline surfaces as Offline so Talk can die on network loss`() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(DISCONNECT_AT_START))

        val result = transportFor(token = "test-token").transcribe(clip())

        assertTrue(result is TalkResult.Failed)
        assertTrue((result as TalkResult.Failed).error is ApiError.Offline)
    }

    @Test
    fun `tts speaks the reply and returns decoded audio`() = runBlocking {
        val audioBytes = byteArrayOf(1, 2, 3, 4, 5)
        val encoded = Base64.getEncoder().encodeToString(audioBytes)
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """{"audio":"$encoded","content_type":"audio/mpeg","chunks":1,"chunk":0}""",
                ),
        )

        val result = transportFor(token = "test-token").speak("I heard: we walked the river path.")

        assertTrue(result is TalkResult.Spoken)
        val spoken = result as TalkResult.Spoken
        assertArrayEquals(audioBytes, spoken.audio)
        assertEquals("audio/mpeg", spoken.contentType)

        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertEquals("/api/v1/tts/message", recorded.path)
        val body = recorded.body.readUtf8()
        assertTrue(body.contains("\"visible_text\":\"I heard: we walked the river path.\""))
        assertTrue(body.contains("\"message_id\":"))
    }

    @Test
    fun `tts 500 is a plain http error`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"detail":"boom"}"""))

        val result = transportFor(token = "test-token").speak("hello")

        assertTrue(result is TalkResult.Failed)
        val error = (result as TalkResult.Failed).error
        assertTrue(error is ApiError.Http)
        assertEquals(500, (error as ApiError.Http).code)
    }

    @Test
    fun `tts response without audio is malformed`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"chunks":0}"""),
        )

        val result = transportFor(token = "test-token").speak("hello")

        assertTrue(result is TalkResult.Failed)
        assertTrue((result as TalkResult.Failed).error is ApiError.Malformed)
    }

    private companion object {
        const val DISCONNECT_AT_START =
            okhttp3.mockwebserver.SocketPolicy.DISCONNECT_AT_START
    }
}
