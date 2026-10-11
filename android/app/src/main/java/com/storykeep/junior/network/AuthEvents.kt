package com.storykeep.junior.network

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Process-wide signal that the backend rejected our credentials with 401.
 *
 * The service token is static (see BuildConfig.SERVICE_TOKEN), so there is
 * nothing to refresh: a 401 means the token is missing, wrong, or revoked.
 * Screens and the session observe [unauthorized] and surface a re-auth
 * message instead of retrying the call.
 */
object AuthEvents {
    private val _unauthorized = MutableStateFlow(false)
    val unauthorized: StateFlow<Boolean> = _unauthorized.asStateFlow()

    fun onUnauthorized() {
        _unauthorized.value = true
    }

    fun clear() {
        _unauthorized.value = false
    }
}
