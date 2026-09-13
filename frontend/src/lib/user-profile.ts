import type { Profile, User } from "./types";

export function avatarMediaUrl(mediaId: string | null | undefined): string | null {
  if (!mediaId) return null;
  return `/api/v1/media/${mediaId}`;
}

/** Ensure avatar fields always use the persisted media id, never a stale blob URL. */
export function normalizeUserProfile<T extends Pick<Profile, "avatar_media_id" | "avatar_url">>(
  profile: T,
): T {
  const avatar_media_id = profile.avatar_media_id ?? null;
  return {
    ...profile,
    avatar_media_id,
    avatar_url: avatarMediaUrl(avatar_media_id) ?? profile.avatar_url ?? null,
  };
}

/** Merge a partial profile/me response into the library user without dropping preferences or avatar. */
export function mergeUserProfile(base: User, patch: Partial<Profile>): User {
  const avatar_media_id =
    patch.avatar_media_id !== undefined ? patch.avatar_media_id : (base.avatar_media_id ?? null);
  const avatar_url = avatarMediaUrl(avatar_media_id) ?? patch.avatar_url ?? base.avatar_url ?? null;
  return normalizeUserProfile({
    ...base,
    ...patch,
    avatar_media_id,
    avatar_url,
    preferences: patch.preferences ?? base.preferences ?? {},
  });
}
