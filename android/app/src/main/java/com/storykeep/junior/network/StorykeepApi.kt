package com.storykeep.junior.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import retrofit2.http.GET

/**
 * The Storykeep API surface the Junior app calls.
 *
 * Paths are relative to BuildConfig.BASE_URL (…/api/v1/). This slice adds only
 * the plumbing: one authenticated probe so a fresh install can verify its
 * service token. Talk/Conversation/Stories endpoints land in slices 2–4.
 */
interface StorykeepApi {
    /** Auth probe. Returns 200 with the owner profile, 401 when the token is wrong. */
    @GET("me")
    suspend fun me(): ProfileDto
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
