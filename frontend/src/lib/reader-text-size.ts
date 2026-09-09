export type ArticleTextSize = "sm" | "md" | "lg" | "xl";

export const ARTICLE_TEXT_SIZE_OPTIONS: { value: ArticleTextSize; label: string }[] = [
  { value: "sm", label: "Small" },
  { value: "md", label: "Normal" },
  { value: "lg", label: "Large" },
  { value: "xl", label: "Extra large" },
];

const STORAGE_KEY = "storykeep-reader-text-size";

export function readArticleTextSize(): ArticleTextSize {
  if (typeof window === "undefined") return "md";
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === "sm" || value === "md" || value === "lg" || value === "xl") return value;
  } catch {
    /* ignore */
  }
  return "md";
}

export function writeArticleTextSize(size: ArticleTextSize) {
  try {
    window.localStorage.setItem(STORAGE_KEY, size);
  } catch {
    /* ignore */
  }
}

export function articleTextSizeClass(size: ArticleTextSize): string {
  return size === "md" ? "" : `article-size-${size}`;
}
