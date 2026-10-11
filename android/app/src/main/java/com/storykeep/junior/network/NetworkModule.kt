package com.storykeep.junior.network

import com.storykeep.junior.BuildConfig
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.serialization.SerializationException
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory

/**
 * The single Retrofit client for the Storykeep API.
 *
 * Base URL and service token are BuildConfig fields (see app/build.gradle.kts),
 * so nothing secret is compiled from a committed file. Every request carries
 * the bearer token; a 401 becomes [UnauthorizedException] via
 * [UnauthorizedInterceptor] so callers can react instead of retrying.
 */
object NetworkModule {
    val json: Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    private val loggingInterceptor = HttpLoggingInterceptor().apply {
        // BASIC logs request lines and response codes only — headers would
        // print the bearer token into logcat.
        level = if (BuildConfig.DEBUG) {
            HttpLoggingInterceptor.Level.BASIC
        } else {
            HttpLoggingInterceptor.Level.NONE
        }
    }

    private val okHttpClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            .connectTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .readTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .writeTimeout(TIMEOUT_SECONDS, TimeUnit.SECONDS)
            .addInterceptor(loggingInterceptor)
            .addInterceptor(AuthInterceptor())
            .addInterceptor(UnauthorizedInterceptor())
            .build()
    }

    private val retrofit: Retrofit by lazy {
        Retrofit.Builder()
            .baseUrl(BuildConfig.BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
    }

    val api: StorykeepApi by lazy { retrofit.create(StorykeepApi::class.java) }

    private const val TIMEOUT_SECONDS = 30L
}

/** Failure categories a caller can branch on. */
sealed interface ApiError {
    /** The service token was missing, wrong, or revoked (HTTP 401). */
    data object Unauthorized : ApiError

    /** Any other non-2xx response; [code] is the HTTP status. */
    data class Http(val code: Int, val message: String) : ApiError

    /** Socket / DNS / TLS failure — treat as "no network". */
    data class Offline(val cause: IOException) : ApiError

    /** Response body did not parse. */
    data class Malformed(val cause: SerializationException) : ApiError
}

/**
 * Runs an API call and maps failures onto [ApiError] inside an [ApiCallException].
 *
 * A 401 already raised [UnauthorizedException] from the interceptor; it is
 * re-wrapped here so one catch site covers every failure shape, and
 * [AuthEvents] has been flagged for the UI.
 */
suspend fun <T> safeApiCall(block: suspend () -> T): Result<T> = try {
    Result.success(block())
} catch (e: UnauthorizedException) {
    Result.failure(ApiCallException(ApiError.Unauthorized, e.message))
} catch (e: HttpException) {
    Result.failure(ApiCallException(ApiError.Http(e.code(), e.message.orEmpty())))
} catch (e: IOException) {
    Result.failure(ApiCallException(ApiError.Offline(e), e.message))
} catch (e: SerializationException) {
    Result.failure(ApiCallException(ApiError.Malformed(e), e.message))
}

/** Wraps a mapped [ApiError] so callers can tell API failures from programming bugs. */
class ApiCallException(val error: ApiError, message: String? = null) :
    Exception(message ?: error.toString())
