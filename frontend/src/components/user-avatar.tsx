"use client";

import { useState } from "react";
import { avatarInitials, avatarMediaUrl } from "@/lib/user-profile";
import { cn } from "@/lib/utils";

/**
 * Profile photo from the persisted media id.
 *
 * A failed fetch (missing file, expired session, deleted media) falls back to
 * initials rather than leaving a broken image, and no generated stand-in photo
 * is ever substituted.
 */
export function UserAvatar({
  mediaId,
  displayName,
  email,
  className,
  initialsClassName,
}: {
  mediaId: string | null | undefined;
  displayName?: string | null;
  email?: string | null;
  className?: string;
  initialsClassName?: string;
}) {
  const src = avatarMediaUrl(mediaId);
  // Keyed by src so a fresh upload retries without an effect.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const failed = Boolean(src) && failedSrc === src;
  const initials = avatarInitials(displayName, email);

  return (
    <div className={cn("shrink-0 overflow-hidden rounded-full bg-muted", className)}>
      {src && !failed ? (
        <img
          src={src}
          alt={displayName || email || "Profile photo"}
          className="size-full object-cover"
          onError={() => setFailedSrc(src)}
        />
      ) : (
        <span className={cn("flex size-full items-center justify-center font-medium", initialsClassName)}>
          {initials}
        </span>
      )}
    </div>
  );
}
