package com.storykeep.junior.network

import okhttp3.Interceptor
import okhttp3.Response

/**
 * Turns a 401 from the API into [UnauthorizedException] and flags [AuthEvents].
 *
 * OkHttp would otherwise hand the 401 straight to Retrofit as a failed
 * response and callers would see a bare HttpException with no idea the token
 * died. A 401 never retries: the service token is static, so replaying the
 * request cannot fix it.
 */
class UnauthorizedInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val response = chain.proceed(chain.request())
        if (response.code == 401) {
            AuthEvents.onUnauthorized()
            response.close()
            throw UnauthorizedException("Not authorized — check STORYKEEP_SERVICE_TOKEN")
        }
        return response
    }
}

/** Thrown when the backend rejects the service token with 401. */
class UnauthorizedException(message: String) : Exception(message)
