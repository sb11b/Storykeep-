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

const CTA_LINE =
  /^\s*(?:want to leave a tip|leave a tip|support us|sign up|cookie settings|subscribe(?:\s+to|\s+for|\s+now)?|support our|become a member|donate now|we use cookies|accept cookies|manage cookies)/i;

export function isCtaOnlyArticleText(text: string | null | undefined): boolean {
  if (!text?.trim()) return true;
  const blocks = text
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);
  if (!blocks.length) return true;
  const substantive = blocks.filter((block) => block.length >= 40 && !CTA_LINE.test(block) && !/leave a tip|support us|sign up|cookie settings/i.test(block));
  return substantive.length === 0;
}

export function isPollutedArticleText(text: string): boolean {
  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return false;
  const cssish = lines.filter(
    (line) => /^\s*[.#@][\w#.\[\](),\s%-]+\s*\{/.test(line) || (line.includes("{") && /box-sizing|\.widget|display\s*:/.test(line)),
  ).length;
  return cssish >= Math.max(2, Math.ceil(lines.length / 2));
}

export function isPollutedArticleHtml(html: string): boolean {
  const sample = html.slice(0, 12000).toLowerCase();
  if (/<style[\s>]/i.test(html)) return true;
  if (/box-sizing\s*:\s*border-box/.test(sample)) return true;
  if (/\.widget\s*\{/.test(sample)) return true;
  if (/\{box-sizing/i.test(sample)) return true;
  if (/#footer\s*\{/.test(sample)) return true;
  if (/display\s*:\s*flex/.test(sample) && sample.includes("{")) return true;
  const cssRuleCount = (html.match(/[.#][\w-]+\s*\{/g) || []).length;
  if (cssRuleCount >= 2) return true;
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

function readerBodyFromFields(content_html: string | null, content_text: string | null): string {
  const text = content_text?.trim() || "";
  const html = content_html ? sanitizeHtml(content_html) : "";
  if (text.length >= 40 && !isPollutedArticleText(text) && !isCtaOnlyArticleText(text) && (!html || isPollutedArticleHtml(html))) {
    return plainTextToArticleHtml(text);
  }
  if (html && !isPollutedArticleHtml(html) && !isCtaOnlyArticleText(stripHtml(html))) return html;
  if (text && !isPollutedArticleText(text) && !isCtaOnlyArticleText(text)) return plainTextToArticleHtml(text);
  return "";
}

export function articleReaderSource(article: {
  content_html: string | null;
  content_text: string | null;
  feed_html?: string | null;
  summary?: string | null;
}): string {
  const primary = readerBodyFromFields(article.content_html, article.content_text);
  if (primary) return primary;
  if (article.feed_html) {
    const feedBody = readerBodyFromFields(article.feed_html, stripHtml(article.feed_html));
    if (feedBody) return feedBody;
  }
  const summaryText = stripHtml(article.summary);
  if (summaryText && summaryText.length >= 80 && !isCtaOnlyArticleText(summaryText) && !isPollutedArticleHtml(summaryText)) {
    return plainTextToArticleHtml(summaryText);
  }
  return "";
}

export function mergeExtractArticle(previous: {
  content_html: string | null;
  content_text: string | null;
  image_url?: string | null;
}, next: {
  content_html: string | null;
  content_text: string | null;
  image_url?: string | null;
}) {
  const nextText = next.content_text?.trim() ?? "";
  const content_text =
    nextText && !isCtaOnlyArticleText(nextText) && !isPollutedArticleText(nextText)
      ? next.content_text
      : previous.content_text;
  let content_html = next.content_html?.trim() ? next.content_html : previous.content_html;
  if (content_html && isCtaOnlyArticleText(stripHtml(content_html))) {
    content_html = previous.content_html;
  }
  if (content_html && isPollutedArticleHtml(content_html)) {
    content_html = content_text ? plainTextToArticleHtml(content_text) : previous.content_html;
  }
  const image_url = next.image_url?.trim() ? next.image_url : previous.image_url ?? null;
  return { content_text, content_html, image_url };
}
