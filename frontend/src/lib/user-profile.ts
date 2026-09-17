import { isUuid } from "@/lib/api-errors";
import type { Profile, User } from "./types";

/**
 * Persisted avatar source. Always the media id route — never a `blob:` preview,
 * which dies on reload. The id doubles as the cache-bust token so a new upload
 * bypasses any cached response for the previous photo.
 */
export function avatarMediaId(mediaId: string | null | undefined): string | null {
  const trimmed = mediaId?.trim() || "";
  if (!isUuid(trimmed)) return null;
  return trimmed;
}

export function avatarMediaUrl(mediaId: string | null | undefined): string | null {
  const id = avatarMediaId(mediaId);
  if (!id) return null;
  return `/api/v1/media/${id}?v=${id}`;
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

function reusableAvatarUrl(existing: string | null | undefined): string | null {
  if (!existing || existing.startsWith("blob:")) return null;
  const match = existing.match(/\/api\/v1\/media\/([^/?#]+)/i);
  if (match && !isUuid(decodeURIComponent(match[1]))) return null;
  return existing;
}

/** Ensure avatar fields always use the persisted media id, never a stale blob URL. */
export function normalizeUserProfile<T extends Pick<Profile, "avatar_media_id" | "avatar_url">>(
  profile: T,
): T {
  const avatar_media_id = avatarMediaId(profile.avatar_media_id);
  return {
    ...profile,
    avatar_media_id,
    avatar_url: avatarMediaUrl(avatar_media_id) ?? reusableAvatarUrl(profile.avatar_url),
  };
}

/** Merge a partial profile/me response into the library user without dropping preferences or avatar. */
export function mergeUserProfile(base: User, patch: Partial<Profile>): User {
  const avatar_media_id =
    patch.avatar_media_id !== undefined ? avatarMediaId(patch.avatar_media_id) : avatarMediaId(base.avatar_media_id);
  const inherited = patch.avatar_url ?? base.avatar_url ?? null;
  const avatar_url = avatarMediaUrl(avatar_media_id) ?? reusableAvatarUrl(inherited);
  return normalizeUserProfile({
    ...base,
    ...patch,
    avatar_media_id,
    avatar_url,
    preferences: patch.preferences ?? base.preferences ?? {},
  });
}
