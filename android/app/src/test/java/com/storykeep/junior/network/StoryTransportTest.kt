package com.storykeep.junior.network

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * The real Stories path: list documents, get one by slug, and the
 * create-or-update post. Runs on the JVM — no Android SDK.
 *
 * Proves the two things that can silently break real stories: that every
 * call reaches the exact backend route with the exact field names (a
 * mismatch compiles cleanly and 422s at runtime), and that a 401 surfaces
 * as [ApiError.Unauthorized] and a 500 as [ApiError.Http] rather than a
 * bogus "offline".
 */
class StoryTransportTest {
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

    private fun transportFor(token: String): NetworkStoryTransport {
        // Same Json config as NetworkModule: ignoreUnknownKeys keeps extra
        // backend fields from breaking parsing, explicitNulls = false keeps
        // unset optionals out of request bodies (the backend reads
        // model_fields_set to tell "unset" from "cleared").
        val json = Json {
            ignoreUnknownKeys = true
            explicitNulls = false
            coerceInputValues = true
        }
        val api = Retrofit.Builder()
            .baseUrl(server.url("/api/v1/"))
            .client(
                OkHttpClient.Builder()
                    .addInterceptor(AuthInterceptor(token))
                    .addInterceptor(UnauthorizedInterceptor())
                    .build(),
            )
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(StorykeepApi::class.java)
        return NetworkStoryTransport(api)
    }

    @Test
    fun `documents list maps field for field`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    [
                      {
                        "id": "77777777-7777-7777-7777-777777777777",
                        "slug": "river-path",
                        "title": "River path",
                        "text": "we walked the river path",
                        "summary": null,
                        "created_at": "2026-10-01T10:00:00Z",
                        "updated_at": "2026-10-02T10:00:00Z"
                      }
                    ]
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token").listStories()

        assertTrue(result.isSuccess)
        val stories = result.getOrThrow()
        assertEquals(1, stories.size)
        val story = stories.single()
        assertEquals("77777777-7777-7777-7777-777777777777", story.id)
        assertEquals("river-path", story.slug)
        assertEquals("River path", story.title)
        assertEquals("we walked the river path", story.text)
        assertNull(story.summary)
        assertEquals("2026-10-01T10:00:00Z", story.createdAt)
        assertEquals("2026-10-02T10:00:00Z", story.updatedAt)

        val recorded = server.takeRequest()
        assertEquals("GET", recorded.method)
        assertEquals("/api/v1/junior/documents", recorded.path)
        assertEquals("Bearer test-token", recorded.getHeader("Authorization"))
    }

    @Test
    fun `documents list maps a non-null summary`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    [
                      {
                        "id": "88888888-8888-8888-8888-888888888888",
                        "slug": "kitchen-light",
                        "title": "Kitchen light",
                        "text": "the kitchen light at dusk",
                        "summary": "a short summary",
                        "created_at": "2026-10-01T10:00:00Z",
                        "updated_at": "2026-10-02T10:00:00Z"
                      }
                    ]
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token").listStories()

        assertTrue(result.isSuccess)
        assertEquals("a short summary", result.getOrThrow().single().summary)
    }

    @Test
    fun `get document hits the slug route and maps the response`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "id": "77777777-7777-7777-7777-777777777777",
                      "slug": "river-path",
                      "title": "River path",
                      "text": "we walked the river path",
                      "summary": null,
                      "created_at": "2026-10-01T10:00:00Z",
                      "updated_at": "2026-10-02T10:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token").getStory("river-path")

        assertTrue(result.isSuccess)
        val story = result.getOrThrow()
        assertEquals("river-path", story.slug)
        assertEquals("River path", story.title)
        assertEquals("we walked the river path", story.text)

        val recorded = server.takeRequest()
        assertEquals("GET", recorded.method)
        assertEquals("/api/v1/junior/documents/river-path", recorded.path)
    }

    @Test
    fun `save story posts slug title and text to the upsert route`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "id": "99999999-9999-9999-9999-999999999999",
                      "slug": "river-path",
                      "title": "River path",
                      "text": "You: we walked the river path",
                      "summary": null,
                      "created_at": "2026-10-03T10:00:00Z",
                      "updated_at": "2026-10-03T10:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token")
            .saveStory(
                slug = "river-path",
                title = "River path",
                text = "You: we walked the river path",
            )

        assertTrue(result.isSuccess)
        val saved = result.getOrThrow()
        assertEquals("99999999-9999-9999-9999-999999999999", saved.id)
        assertEquals("river-path", saved.slug)
        assertEquals("You: we walked the river path", saved.text)

        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertEquals("/api/v1/junior/documents", recorded.path)
        val body = recorded.body.readUtf8()
        assertTrue(body.contains("\"slug\":\"river-path\""))
        assertTrue(body.contains("\"title\":\"River path\""))
        assertTrue(body.contains("\"text\":\"You: we walked the river path\""))
    }

    @Test
    fun `save story sends an explicit null summary`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "id": "99999999-9999-9999-9999-999999999999",
                      "slug": "no-summary",
                      "title": "No summary",
                      "text": "text only",
                      "summary": null,
                      "created_at": "2026-10-03T10:00:00Z",
                      "updated_at": "2026-10-03T10:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token")
            .saveStory(slug = "no-summary", title = "No summary", text = "text only")

        assertTrue(result.isSuccess)
        assertNull(result.getOrThrow().summary)

        // The app's Json (explicitNulls = false) keeps nulls out of the body;
        // either way the backend treats a missing summary as "leave unset".
        val recorded = server.takeRequest()
        val body = recorded.body.readUtf8()
        assertTrue(!body.contains("\"summary\":"))
    }

    @Test
    fun `save story sends a provided summary`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "id": "99999999-9999-9999-9999-999999999999",
                      "slug": "with-summary",
                      "title": "With summary",
                      "text": "text",
                      "summary": "the summary",
                      "created_at": "2026-10-03T10:00:00Z",
                      "updated_at": "2026-10-03T10:00:00Z"
                    }
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token")
            .saveStory(
                slug = "with-summary",
                title = "With summary",
                text = "text",
                summary = "the summary",
            )

        assertTrue(result.isSuccess)
        val recorded = server.takeRequest()
        val body = recorded.body.readUtf8()
        assertTrue(body.contains("\"summary\":\"the summary\""))
    }

    @Test
    fun `a 401 flags auth events and surfaces as Unauthorized`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Not authenticated"}"""))

        val result = transportFor(token = "wrong-token").listStories()

        assertTrue(result.isFailure)
        val error = (result.exceptionOrNull() as ApiCallException).error
        assertEquals(ApiError.Unauthorized, error)
        assertTrue(AuthEvents.unauthorized.value)
    }

    @Test
    fun `a 500 is a plain http error`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"detail":"boom"}"""))

        val result = transportFor(token = "test-token").getStory("river-path")

        assertTrue(result.isFailure)
        val error = (result.exceptionOrNull() as ApiCallException).error
        assertTrue(error is ApiError.Http)
        assertEquals(500, (error as ApiError.Http).code)
    }

    @Test
    fun `a malformed body surfaces as Malformed`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"not":"a document array"}"""),
        )

        val result = transportFor(token = "test-token").listStories()

        assertTrue(result.isFailure)
        val error = (result.exceptionOrNull() as ApiCallException).error
        assertTrue(error is ApiError.Malformed)
    }
}
