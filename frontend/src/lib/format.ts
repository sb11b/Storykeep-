export function formatRelative(value: string | null | undefined): string {
  if (!value) return "Unknown date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown date";
  const delta = Date.now() - date.getTime();
  const minutes = Math.round(delta / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function stripHtml(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

const ARTICLE_CDN_SUFFIXES = [
  "wp.com",
  "wordpress.com",
  "cloudfront.net",
  "cloudinary.com",
  "imgix.net",
  "akamaized.net",
  "fastly.net",
  "googleusercontent.com",
  "fbcdn.net",
  "twimg.com",
  "cdninstagram.com",
  "media-amazon.com",
  "blazemedia.com",
  "theblaze.com",
];

export function sanitizeHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?>[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?>[\s\S]*?<\/style>/gi, "")
    .replace(/on\w+="[^"]*"/gi, "")
    .replace(/on\w+='[^']*'/gi, "")
    .replace(/javascript:/gi, "");
}

export function isPollutedArticleHtml(html: string): boolean {
  const sample = html.slice(0, 8000).toLowerCase();
  if (/<style[\s>]/i.test(html)) return true;
  if (/box-sizing\s*:\s*border-box/.test(sample)) return true;
  if (/\.widget\s*\{/.test(sample)) return true;
  if (/^\s*[.#@][\w#.\[\](),\s%-]+\s*\{/m.test(html)) return true;
  return false;
}

export function plainTextToArticleHtml(text: string): string {
  const blocks = text
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);
  if (!blocks.length) return "";
  return blocks.map((block) => `<p>${escapeHtml(block).replace(/\n/g, "<br />")}</p>`).join("");
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function resolveArticleImageUrl(imageUrl: string | null | undefined, articleUrl: string): string | null {
  if (!imageUrl?.trim()) return null;
  try {
    return new URL(imageUrl.trim(), articleUrl).href;
  } catch {
    return null;
  }
}

export function isAllowedArticleImage(imageUrl: string, articleUrl: string): boolean {
  try {
    const image = new URL(imageUrl);
    if (!/^https?:$/i.test(image.protocol)) return false;
    const article = new URL(articleUrl);
    if (image.hostname === article.hostname) return true;
    if (image.hostname.endsWith(`.${article.hostname}`)) return true;
    if (article.hostname.endsWith(`.${image.hostname}`)) return true;
    return ARTICLE_CDN_SUFFIXES.some(
      (suffix) => image.hostname === suffix || image.hostname.endsWith(`.${suffix}`),
    );
  } catch {
    return false;
  }
}

export function articleHeroImageUrl(imageUrl: string | null | undefined, articleUrl: string): string | null {
  const resolved = resolveArticleImageUrl(imageUrl, articleUrl);
  if (!resolved) return null;
  return isAllowedArticleImage(resolved, articleUrl) ? resolved : null;
}

export function articleReaderSource(article: {
  content_html: string | null;
  content_text: string | null;
  summary?: string | null;
}): string {
  const html = article.content_html ? sanitizeHtml(article.content_html) : "";
  if (html && !isPollutedArticleHtml(html)) return html;
  if (article.content_text?.trim()) return plainTextToArticleHtml(article.content_text);
  if (html) return html;
  return plainTextToArticleHtml(stripHtml(article.summary));
}
