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
 * The real Conversation path: projects → threads → messages → post. Runs on
 * the JVM — no Android SDK.
 *
 * Proves the two things that can silently break a real conversation: that
 * every call reaches the exact backend route with the exact field names
 * (a mismatch compiles cleanly and 422s at runtime), and that a 401 surfaces
 * as [ApiError.Unauthorized] and a 500 as [ApiError.Http] rather than a
 * bogus "offline".
 */
class ConversationTransportTest {
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

    private fun transportFor(token: String): NetworkConversationTransport {
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
        return NetworkConversationTransport(api)
    }

    @Test
    fun `projects list maps field for field`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    [
                      {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "slug": "storykeep",
                        "display_name": "Storykeep",
                        "kind": "repo",
                        "repo_url": "https://github.com/sb11b/Storykeep-",
                        "default_branch": "main",
                        "notes": "the repo",
                        "meta": {},
                        "created_at": "2026-10-01T10:00:00Z",
                        "updated_at": "2026-10-02T10:00:00Z"
                      }
                    ]
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token").projects()

        assertTrue(result.isSuccess)
        val projects = result.getOrThrow()
        assertEquals(1, projects.size)
        val project = projects.single()
        assertEquals("11111111-1111-1111-1111-111111111111", project.id)
        assertEquals("storykeep", project.slug)
        assertEquals("Storykeep", project.displayName)
        assertEquals("repo", project.kind)
        assertEquals("https://github.com/sb11b/Storykeep-", project.repoUrl)
        assertEquals("main", project.defaultBranch)
        assertEquals("the repo", project.notes)
        assertEquals("2026-10-01T10:00:00Z", project.createdAt)

        val recorded = server.takeRequest()
        assertEquals("GET", recorded.method)
        assertEquals("/api/v1/junior/projects", recorded.path)
        assertEquals("Bearer test-token", recorded.getHeader("Authorization"))
    }

    @Test
    fun `threads list maps venue_last and status`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    [
                      {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "title": null,
                        "venue_last": "junior-android",
                        "status": "open",
                        "summary": null,
                        "created_at": "2026-10-01T10:00:00Z",
                        "updated_at": "2026-10-02T10:00:00Z"
                      }
                    ]
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token").threads("storykeep")

        assertTrue(result.isSuccess)
        val thread = result.getOrThrow().single()
        assertEquals("22222222-2222-2222-2222-222222222222", thread.id)
        assertNull(thread.title)
        assertEquals("junior-android", thread.venueLast)
        assertEquals("open", thread.status)

        val recorded = server.takeRequest()
        assertEquals("GET", recorded.method)
        assertEquals("/api/v1/junior/projects/storykeep/threads", recorded.path)
    }

    @Test
    fun `messages list maps oldest first with user and junior roles`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    [
                      {
                        "id": "33333333-3333-3333-3333-333333333333",
                        "thread_id": "22222222-2222-2222-2222-222222222222",
                        "role": "user",
                        "content": "we walked the river path",
                        "venue": "junior-android",
                        "meta": {},
                        "created_at": "2026-10-01T10:00:00Z"
                      },
                      {
                        "id": "44444444-4444-4444-4444-444444444444",
                        "thread_id": "22222222-2222-2222-2222-222222222222",
                        "role": "junior",
                        "content": "That's a keeper.",
                        "venue": "junior-android",
                        "meta": {},
                        "created_at": "2026-10-01T10:00:01Z"
                      }
                    ]
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token")
            .messages("storykeep", "22222222-2222-2222-2222-222222222222")

        assertTrue(result.isSuccess)
        val messages = result.getOrThrow()
        assertEquals(2, messages.size)
        assertEquals("user", messages[0].role)
        assertEquals("we walked the river path", messages[0].content)
        assertEquals("junior", messages[1].role)
        assertEquals("That's a keeper.", messages[1].content)

        val recorded = server.takeRequest()
        assertEquals("GET", recorded.method)
        assertEquals(
            "/api/v1/junior/projects/storykeep/threads/22222222-2222-2222-2222-222222222222/messages",
            recorded.path,
        )
    }

    @Test
    fun `post message hits the project thread route and returns the stored turn`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "thread_id": "22222222-2222-2222-2222-222222222222",
                      "user_message": {
                        "id": "55555555-5555-5555-5555-555555555555",
                        "thread_id": "22222222-2222-2222-2222-222222222222",
                        "role": "user",
                        "content": "keep the river note",
                        "venue": "junior-android",
                        "meta": {},
                        "created_at": "2026-10-01T10:00:00Z"
                      },
                      "junior_message": {
                        "id": "66666666-6666-6666-6666-666666666666",
                        "thread_id": "22222222-2222-2222-2222-222222222222",
                        "role": "junior",
                        "content": "Noted.",
                        "venue": "junior-android",
                        "meta": {},
                        "created_at": "2026-10-01T10:00:01Z"
                      },
                      "reply_status": "ok",
                      "detail": null
                    }
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token")
            .postMessage("storykeep", "22222222-2222-2222-2222-222222222222", "keep the river note")

        assertTrue(result.isSuccess)
        val turn = result.getOrThrow()
        assertEquals("22222222-2222-2222-2222-222222222222", turn.threadId)
        assertEquals("keep the river note", turn.userMessage.content)
        assertEquals("user", turn.userMessage.role)
        assertEquals("Noted.", turn.juniorMessage?.content)
        assertEquals("junior", turn.juniorMessage?.role)
        assertEquals("ok", turn.replyStatus)

        val recorded = server.takeRequest()
        assertEquals("POST", recorded.method)
        assertEquals(
            "/api/v1/junior/projects/storykeep/threads/22222222-2222-2222-2222-222222222222/messages",
            recorded.path,
        )
        val body = recorded.body.readUtf8()
        assertTrue(body.contains("\"content\":\"keep the river note\""))
    }

    @Test
    fun `a deferred reply still maps with a null junior message`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "thread_id": "22222222-2222-2222-2222-222222222222",
                      "user_message": {
                        "id": "55555555-5555-5555-5555-555555555555",
                        "thread_id": "22222222-2222-2222-2222-222222222222",
                        "role": "user",
                        "content": "hello",
                        "venue": "junior-android",
                        "meta": {},
                        "created_at": "2026-10-01T10:00:00Z"
                      },
                      "junior_message": null,
                      "reply_status": "deferred",
                      "detail": "reply deferred"
                    }
                    """.trimIndent(),
                ),
        )

        val result = transportFor(token = "test-token")
            .postMessage("storykeep", "22222222-2222-2222-2222-222222222222", "hello")

        assertTrue(result.isSuccess)
        val turn = result.getOrThrow()
        assertNull(turn.juniorMessage)
        assertEquals("deferred", turn.replyStatus)
        assertEquals("reply deferred", turn.detail)
    }

    @Test
    fun `a 401 flags auth events and surfaces as Unauthorized`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Not authenticated"}"""))

        val result = transportFor(token = "wrong-token").projects()

        assertTrue(result.isFailure)
        val error = (result.exceptionOrNull() as ApiCallException).error
        assertEquals(ApiError.Unauthorized, error)
        assertTrue(AuthEvents.unauthorized.value)
    }

    @Test
    fun `a 500 is a plain http error`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"detail":"boom"}"""))

        val result = transportFor(token = "test-token")
            .messages("storykeep", "22222222-2222-2222-2222-222222222222")

        assertTrue(result.isFailure)
        val error = (result.exceptionOrNull() as ApiCallException).error
        assertTrue(error is ApiError.Http)
        assertEquals(500, (error as ApiError.Http).code)
    }
}
