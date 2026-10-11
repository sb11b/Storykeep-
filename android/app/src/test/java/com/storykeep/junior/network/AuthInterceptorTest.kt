package com.storykeep.junior.network

import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * Auth plumbing for the network layer. Runs on the JVM — no Android SDK.
 *
 * Covers the two things that can silently break a real client: a missing
 * bearer header, and a 401 that nobody notices.
 */
class AuthInterceptorTest {
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

    private fun apiFor(token: String): StorykeepApi = Retrofit.Builder()
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

    @Test
    fun `request carries the bearer token and hits the right path`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":"6b1f","email":"owner@example.com","display_name":"Steve"}"""),
        )

        apiFor(token = "test-token").me()

        val recorded = server.takeRequest()
        assertEquals("/api/v1/me", recorded.path)
        assertEquals("Bearer test-token", recorded.getHeader("Authorization"))
    }

    @Test
    fun `401 flags auth events and surfaces as Unauthorized`() = runBlocking {
        server.enqueue(
            MockResponse().setResponseCode(401).setBody("""{"detail":"Not authenticated"}"""),
        )

        val result = safeApiCall { apiFor(token = "wrong-token").me() }

        assertTrue(result.isFailure)
        val error = (result.exceptionOrNull() as ApiCallException).error
        assertEquals(ApiError.Unauthorized, error)
        assertTrue(AuthEvents.unauthorized.value)
    }

    @Test
    fun `200 leaves auth events clear`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"id":"6b1f","email":"owner@example.com"}"""),
        )

        val result = safeApiCall { apiFor(token = "test-token").me() }

        assertTrue(result.isSuccess)
        assertEquals("owner@example.com", result.getOrNull()?.email)
        assertFalse(AuthEvents.unauthorized.value)
    }

    @Test
    fun `403 is a plain http error, not unauthorized`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(403).setBody("""{"detail":"demo locked"}"""))

        val result = safeApiCall { apiFor(token = "test-token").me() }

        val error = (result.exceptionOrNull() as ApiCallException).error
        assertTrue(error is ApiError.Http)
        assertEquals(403, (error as ApiError.Http).code)
    }
}
