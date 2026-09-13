import type { Profile, User } from "./types";

/**
 * Persisted avatar source. Always the media id route — never a `blob:` preview,
 * which dies on reload. The id doubles as the cache-bust token so a new upload
 * bypasses any cached response for the previous photo.
 */
export function avatarMediaUrl(mediaId: string | null | undefined): string | null {
  if (!mediaId) return null;
  return `/api/v1/media/${mediaId}?v=${mediaId}`;
}

/** Initials for the fallback shown when there is no avatar, or it fails to load. */
export function avatarInitials(displayName?: string | null, email?: string | null): string {
  const name = displayName?.trim();
  if (name) {
    const parts = name.split(/\s+/).filter(Boolean);
    const letters = parts.slice(0, 2).map((part) => part[0]!).join("");
    if (letters) return letters.toUpperCase();
  }
  const handle = email?.trim();
  if (handle) return handle.slice(0, 1).toUpperCase();
  return "?";
}

/** Ensure avatar fields always use the persisted media id, never a stale blob URL. */
export function normalizeUserProfile<T extends Pick<Profile, "avatar_media_id" | "avatar_url">>(
  profile: T,
): T {
  const avatar_media_id = profile.avatar_media_id ?? null;
  const existing = profile.avatar_url;
  const reusable = existing && !existing.startsWith("blob:") ? existing : null;
  return {
    ...profile,
    avatar_media_id,
    avatar_url: avatarMediaUrl(avatar_media_id) ?? reusable,
  };
}

/** Merge a partial profile/me response into the library user without dropping preferences or avatar. */
export function mergeUserProfile(base: User, patch: Partial<Profile>): User {
  const avatar_media_id =
    patch.avatar_media_id !== undefined ? patch.avatar_media_id : (base.avatar_media_id ?? null);
  const inherited = patch.avatar_url ?? base.avatar_url ?? null;
  const avatar_url =
    avatarMediaUrl(avatar_media_id) ?? (inherited && !inherited.startsWith("blob:") ? inherited : null);
  return normalizeUserProfile({
    ...base,
    ...patch,
    avatar_media_id,
    avatar_url,
    preferences: patch.preferences ?? base.preferences ?? {},
  });
}
