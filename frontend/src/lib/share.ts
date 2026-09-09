export type ArticleShareTarget = "email" | "sms" | "facebook" | "x" | "reddit";

export type ShareArticle = {
  id: string;
  title: string;
  url: string | null;
};

export function shareUrlForArticle(article: ShareArticle, origin?: string): string {
  const url = (article.url || "").trim();
  if (/^https?:\/\//i.test(url)) return url;
  const base = origin || (typeof window !== "undefined" ? window.location.origin : "");
  if (base && article.id) {
    return `${base.replace(/\/$/, "")}/?article=${encodeURIComponent(article.id)}`;
  }
  return url;
}

export function shareTextForArticle(article: ShareArticle): string {
  return (article.title || "").trim() || "Story from StoryKeep";
}

export function articleShareBody(article: ShareArticle, origin?: string): string {
  const title = shareTextForArticle(article);
  const link = shareUrlForArticle(article, origin);
  return link ? `${title}\n\n${link}` : title;
}

export function articleShareHref(target: ArticleShareTarget, article: ShareArticle, origin?: string): string {
  const link = shareUrlForArticle(article, origin);
  const title = shareTextForArticle(article);
  const body = articleShareBody(article, origin);
  const encUrl = encodeURIComponent(link);
  const encTitle = encodeURIComponent(title);
  const encBody = encodeURIComponent(body);

  switch (target) {
    case "email":
      return `mailto:?subject=${encTitle}&body=${encBody}`;
    case "sms":
      return `sms:?&body=${encBody}`;
    case "facebook":
      return `https://www.facebook.com/sharer/sharer.php?u=${encUrl}`;
    case "x":
      return `https://twitter.com/intent/tweet?url=${encUrl}&text=${encTitle}`;
    case "reddit":
      return `https://www.reddit.com/submit?url=${encUrl}&title=${encTitle}`;
  }
}

export function openArticleShare(target: ArticleShareTarget, article: ShareArticle): void {
  const href = articleShareHref(target, article);
  if (target === "email" || target === "sms") {
    window.location.href = href;
    return;
  }
  window.open(href, "_blank", "noopener,noreferrer");
}
