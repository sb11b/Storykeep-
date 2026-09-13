"use client";

import { useState } from "react";

/**
 * Article art that removes itself when the publisher CDN refuses the request,
 * so a hotlink block leaves no broken-image placeholder in the layout.
 */
export function ArticleImage({
  src,
  className,
  eager,
}: {
  src: string;
  className?: string;
  eager?: boolean;
}) {
  // Keyed by src so a new article resets the failure without an effect.
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  if (failedSrc === src) return null;

  return (
    <img
      src={src}
      alt=""
      loading={eager ? "eager" : "lazy"}
      referrerPolicy="no-referrer"
      className={className}
      onError={() => setFailedSrc(src)}
    />
  );
}
