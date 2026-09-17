import assert from "node:assert/strict";
import test from "node:test";
import { avatarInitials, avatarMediaUrl, mergeUserProfile, normalizeUserProfile } from "./user-profile";
import type { User } from "./types";

const base: User = {
  id: "u1",
  email: "a@example.com",
  display_name: "Ada",
  avatar_media_id: "11111111-1111-1111-1111-111111111111",
  avatar_url: avatarMediaUrl("11111111-1111-1111-1111-111111111111"),
  birthdate: null,
  preferences: {
    appearance: { rail_preset: "navy", font_family: "serif" },
    items_per_page: 40,
  },
  profile_read_only: false,
  created_at: "2026-01-01T00:00:00Z",
};

test("mergeUserProfile keeps preferences when patch omits them", () => {
  const next = mergeUserProfile(base, {
    totp_enabled: false,
    email_otp_enabled: false,
    email_otp_available: false,
    has_backup_codes: false,
  });
  assert.equal(next.avatar_media_id, base.avatar_media_id);
  assert.equal(next.avatar_url, base.avatar_url);
  assert.deepEqual(next.preferences.appearance, { rail_preset: "navy", font_family: "serif" });
});

test("normalizeUserProfile derives avatar_url from avatar_media_id", () => {
  const mediaId = "22222222-2222-2222-2222-222222222222";
  const profile = normalizeUserProfile({
    ...base,
    avatar_media_id: mediaId,
    avatar_url: "blob:http://localhost/dead",
  });
  assert.equal(profile.avatar_media_id, mediaId);
  assert.equal(profile.avatar_url, `/api/v1/media/${mediaId}?v=${mediaId}`);
});

test("normalizeUserProfile drops a blob preview when there is no media id", () => {
  const profile = normalizeUserProfile({
    ...base,
    avatar_media_id: null,
    avatar_url: "blob:http://localhost/dead",
  });
  assert.equal(profile.avatar_url, null);
});

test("mergeUserProfile never inherits a blob avatar url", () => {
  const next = mergeUserProfile(
    { ...base, avatar_media_id: null, avatar_url: "blob:http://localhost/dead" },
    { avatar_media_id: null },
  );
  assert.equal(next.avatar_url, null);
});

test("avatarInitials uses two name parts, then email, then a placeholder glyph", () => {
  assert.equal(avatarInitials("Steve Bitsko", "steve@example.com"), "SB");
  assert.equal(avatarInitials(null, "steve@example.com"), "S");
  assert.equal(avatarInitials(null, null), "?");
});

test("mergeUserProfile derives avatar_url from avatar_media_id", () => {
  const mediaId = "22222222-2222-2222-2222-222222222222";
  const next = mergeUserProfile(base, {
    avatar_media_id: mediaId,
    totp_enabled: false,
    email_otp_enabled: false,
    email_otp_available: false,
    has_backup_codes: false,
  });
  assert.equal(next.avatar_media_id, mediaId);
  assert.equal(next.avatar_url, `/api/v1/media/${mediaId}?v=${mediaId}`);
});

test("avatarMediaUrl skips reserved non-UUID ids so Profile never GETs /media/refresh", () => {
  assert.equal(avatarMediaUrl("refresh"), null);
  assert.equal(avatarMediaUrl("profile"), null);
  assert.equal(avatarMediaUrl(""), null);
  assert.equal(avatarMediaUrl(null), null);
  const mediaId = "22222222-2222-2222-2222-222222222222";
  assert.equal(avatarMediaUrl(mediaId), `/api/v1/media/${mediaId}?v=${mediaId}`);
});

test("normalizeUserProfile drops refresh as an avatar media id", () => {
  const profile = normalizeUserProfile({
    ...base,
    avatar_media_id: "refresh",
    avatar_url: "/api/v1/media/refresh?v=refresh",
  });
  assert.equal(profile.avatar_media_id, null);
  assert.equal(profile.avatar_url, null);
});

test("mergeUserProfile replaces preferences when patch includes them", () => {
  const next = mergeUserProfile(base, {
    preferences: { appearance: { rail_preset: "forest" } },
    totp_enabled: false,
    email_otp_enabled: false,
    email_otp_available: false,
    has_backup_codes: false,
  });
  assert.deepEqual(next.preferences, { appearance: { rail_preset: "forest" } });
});
