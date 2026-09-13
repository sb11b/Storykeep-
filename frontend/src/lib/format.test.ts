import assert from "node:assert/strict";
import test from "node:test";
import { articleHeroImageUrl, isUsableArticleBody, mergeExtractArticle } from "./format";

const LONG_PARA =
  "Full article paragraph with enough prose to count as readable article text for regression tests. ".repeat(
    8,
  );
const LONG_BODY = {
  content_html: `<p>${LONG_PARA}</p><p>${LONG_PARA}</p><p>${LONG_PARA}</p>`,
  content_text: `${LONG_PARA.trim()}\n\n${LONG_PARA.trim()}\n\n${LONG_PARA.trim()}`,
};

test("mergeExtractArticle grows short-body article when extract succeeds", () => {
  const dek = "These four Naruto characters prove you can surpass Kage-level strength without becoming Hokage.";
  const previous = {
    content_html: `<p>${dek}</p>`,
    content_text: dek,
    image_url: null,
  };
  const merged = mergeExtractArticle(previous, LONG_BODY);
  assert.ok((merged.content_text || "").length > dek.length);
  assert.ok(isUsableArticleBody(merged.content_html, merged.content_text));
});

test("articleHeroImageUrl allows Fox News CDN hosts", () => {
  const articleUrl = "https://www.foxnews.com/politics/example-story";
  const imageUrl = "https://static.foxnews.com/fox-news/images/hero.jpg";
  assert.equal(articleHeroImageUrl(imageUrl, articleUrl), imageUrl);
});

test("articleHeroImageUrl allows http Fox CDN images for RSS articles", () => {
  const articleUrl = "https://www.foxnews.com/politics/example-story";
  const imageUrl = "http://a57.foxnews.com/images/hero.jpg";
  assert.equal(articleHeroImageUrl(imageUrl, articleUrl), imageUrl);
});

test("articleHeroImageUrl allows any publisher CDN, not just a fixed list", () => {
  const articleUrl = "https://www.cbr.com/naruto-strongest-characters/";
  for (const imageUrl of [
    "https://static0.cbrimages.com/wordpress/wp-content/uploads/2024/01/hero.jpg",
    "https://www.theblaze.com/media-library/image.jpg",
    "https://unknown-publisher-cdn.example.org/photo.webp",
  ]) {
    assert.equal(articleHeroImageUrl(imageUrl, articleUrl), imageUrl);
  }
});

test("articleHeroImageUrl resolves protocol-relative and root-relative feed art", () => {
  const articleUrl = "https://www.cbr.com/naruto-strongest-characters/";
  assert.equal(
    articleHeroImageUrl("//static0.cbrimages.com/hero.jpg", articleUrl),
    "https://static0.cbrimages.com/hero.jpg",
  );
  assert.equal(
    articleHeroImageUrl("/wp-content/uploads/hero.jpg", articleUrl),
    "https://www.cbr.com/wp-content/uploads/hero.jpg",
  );
});

test("articleHeroImageUrl still rejects non-http schemes", () => {
  const articleUrl = "https://www.cbr.com/story/";
  assert.equal(articleHeroImageUrl("data:image/png;base64,AAAA", articleUrl), null);
  assert.equal(articleHeroImageUrl("javascript:alert(1)", articleUrl), null);
});

test("mergeExtractArticle keeps previous body when extract returns worse text", () => {
  const previous = {
    ...LONG_BODY,
    image_url: "https://cdn.example.com/hero.jpg",
  };
  const worse = {
    content_html: "<p>Want to leave a tip?</p>",
    content_text: "Want to leave a tip?",
    image_url: null,
  };
  const merged = mergeExtractArticle(previous, worse);
  assert.equal(merged.content_text, previous.content_text);
  assert.equal(merged.content_html, previous.content_html);
  assert.equal(merged.image_url, previous.image_url);
});
