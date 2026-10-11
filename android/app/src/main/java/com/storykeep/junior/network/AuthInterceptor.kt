package com.storykeep.junior.network

import com.storykeep.junior.BuildConfig
import okhttp3.Interceptor
import okhttp3.Response

/**
 * Adds the static service-token bearer header to every request.
 *
 * The token comes from BuildConfig.SERVICE_TOKEN, wired from
 * `android/local.properties` (gitignored) or a `-P` gradle property — never
 * committed. When it is blank the header is still sent so the backend answers
 * 401 (visible through [AuthEvents]) rather than a confusing "Not
 * authenticated", and a missing token is a build-time setup problem, not a
 * silent no-op.
 */
class AuthInterceptor(
    private val token: String = BuildConfig.SERVICE_TOKEN,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request().newBuilder()
            .header("Authorization", "Bearer $token")
            .header("Accept", "application/json")
            .build()
        return chain.proceed(request)
    }
}
