import assert from "node:assert/strict";
import test from "node:test";
import {
  articleIdFromHref,
  chatArticleClick,
  noteMarkdownHtml,
  parseArticleHash,
  prefixSelectedLines,
  renderMarkdown,
  wrapCodeFence,
  wrapHighlight,
  wrapInline,
  wrapWikilink,
} from "./markdown";

test("wrapHighlight wraps a textarea selection", () => {
  const result = wrapHighlight("The slope of y", 4, 9);
  assert.equal(result.text, "The ==slope== of y");
  assert.equal(result.selectionStart, 6);
  assert.equal(result.selectionEnd, 11);
});

test("wrapHighlight wraps the word at the caret when nothing is selected", () => {
  const result = wrapHighlight("The slope of y", 6, 6);
  assert.equal(result.text, "The ==slope== of y");
  assert.equal(result.selectionStart, 6);
  assert.equal(result.selectionEnd, 11);
});

test("renderMarkdown turns ==text== into mark", () => {
  const html = renderMarkdown("Keep ==the slope== of y.");
  assert.match(html, /<mark>the slope<\/mark>/);
  assert.equal(html.includes("==the slope=="), false);
});

test("renderMarkdown highlights text that contains equals signs", () => {
  const html = renderMarkdown("Keep ==a=b== in the formula.");
  assert.match(html, /<mark>a=b<\/mark>/);
});

test("renderMarkdown highlights multi-line selections", () => {
  const source = [
    "==As you interpret the results of your data, ask yourself the following key questions:",
    "",
    "• Do the data answer the question you asked originally? How?",
    "",
    "• Does the data help you protect yourself against any objections? How?",
    "",
    "• Are there any restriction on your conclusions, any angles that you didn’t consider?==",
  ].join("\n");
  const html = renderMarkdown(source);
  assert.match(html, /<mark class="sk-highlight-block">/);
  assert.match(html, /Do the data answer the question/);
  assert.match(html, /restriction on your conclusions/);
  assert.equal(html.includes("=="), false);
  assert.match(html, /<li>Do the data answer/);
});

test("noteMarkdownHtml keeps composer formatting on correction notes", () => {
  const html = noteMarkdownHtml("Intro\n- **bold** bullet\n==mark== and *italic* and <u>under</u>");
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<mark>mark<\/mark>/);
  assert.match(html, /<em>italic<\/em>/);
  assert.match(html, /<u>under<\/u>/);
  assert.match(html, /<ul>/);
});

test("wrapInline and lists", () => {
  const bold = wrapInline("The slope", 4, 9, "**", "**");
  assert.equal(bold.text, "The **slope**");
  const under = wrapInline("The slope", 4, 9, "<u>", "</u>");
  assert.equal(under.text, "The <u>slope</u>");
  const bullets = prefixSelectedLines("one\ntwo", 0, 7, "ul");
  assert.equal(bullets.text, "- one\n- two");
  const numbered = prefixSelectedLines("one\ntwo", 0, 7, "ol");
  assert.equal(numbered.text, "1. one\n2. two");
  const html = renderMarkdown("**bold** *italic*\n<u>under</u>\n- item\n1. first");
  assert.match(html, /<strong>bold<\/strong>/);
  assert.match(html, /<em>italic<\/em>/);
  assert.match(html, /<u>under<\/u>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<ol>/);
});

test("underscore italics do not wrap snake_case names", () => {
  const html = renderMarkdown("See my_file_name and _emphasis_ here.");
  assert.match(html, /my_file_name/);
  assert.equal(html.includes("<em>file</em>"), false);
  assert.match(html, /<em>emphasis<\/em>/);
});

test("fenced code blocks preserve angle brackets and hash comments", () => {
  const source = ["```python", "print('<div>')", "# comment", "```"].join("\n");
  const html = renderMarkdown(source);
  assert.match(html, /<pre class="sk-code">/);
  assert.match(html, /<span class="sk-code-lang">python<\/span>/);
  assert.match(html, /data-copy>Copy<\/button>/);
  assert.equal(html.includes("data-run"), false);
  assert.match(html, /print\('&lt;div&gt;'\)/);
  assert.match(html, /# comment/);
  assert.equal(html.includes("<div>"), false);
  assert.equal(html.includes("<h"), false);
});

test("code fences skip highlight and heading transforms inside", () => {
  const source = ["```text", "==not highlight==", "# not heading", "```"].join("\n");
  const html = renderMarkdown(source);
  assert.match(html, /==not highlight==/);
  assert.match(html, /# not heading/);
  assert.equal(html.includes("<mark>"), false);
  assert.equal(html.includes("<h1>"), false);
});

test("wrapCodeFence inserts empty fence at caret", () => {
  const result = wrapCodeFence("hello", 5, 5, "python");
  assert.equal(result.text, "hello```python\n\n```");
  assert.equal(result.selectionStart, 5 + "```python\n".length);
  assert.equal(result.selectionEnd, result.selectionStart);
});

test("wrapCodeFence wraps a selection", () => {
  const source = "before code after";
  const result = wrapCodeFence(source, 7, 11, "js");
  assert.equal(result.text, "before ```js\ncode\n``` after");
});

test("wikilinks render as buttons and skip fenced code", () => {
  const resolver = (target: string) =>
    target === "DAT 325 Project One" ? { id: "note-1", title: "DAT 325 Project One" } : null;
  const html = renderMarkdown("Open [[DAT 325 Project One]] or [[No Such|typo]]\n```text\n[[Inside]]\n```", resolver);
  assert.match(html, /class="wikilink" data-wikilink-id="note-1"/);
  assert.match(html, /class="wikilink wikilink-missing" data-wikilink-target="No Such"/);
  assert.match(html, /typo/);
  assert.match(html, /\[\[Inside\]\]/);
  assert.equal(html.includes('data-wikilink-target="Inside"'), false);
});

test("wrapWikilink wraps selection as wiki link", () => {
  const result = wrapWikilink("See Project One here", 4, 15);
  assert.equal(result.text, "See [[Project One]] here");
  assert.equal(result.selectionStart, 6);
  assert.equal(result.selectionEnd, 17);
});

test("Junior Imagine markdown renders a media image with Download picture", () => {
  const id = "11111111-1111-1111-1111-111111111111";
  const html = renderMarkdown(`![a red notebook on a desk](/api/v1/media/${id})`);
  assert.doesNotMatch(html, /Here's the image/);
  assert.match(html, new RegExp(`<img src="/api/v1/media/${id}" alt="a red notebook on a desk" />`));
  assert.match(html, /Download picture/);
  assert.match(html, /aria-label="Download picture"/);
  assert.match(html, new RegExp(`data-media-id="${id}"`));
  assert.match(html, new RegExp(`data-media-url="/api/v1/media/${id}"`));
  assert.doesNotMatch(html, /sk-chat-image-download" href=/);
});

test("Junior Imagine HTML img in the assistant body still renders pixels", () => {
  const id = "11111111-1111-1111-1111-111111111111";
  const html = renderMarkdown(`<img src="/api/v1/media/${id}" alt="aged portrait">`);
  assert.match(html, new RegExp(`<img src="/api/v1/media/${id}" alt="aged portrait" />`));
  assert.match(html, /Download picture/);
  assert.doesNotMatch(html, /implemented and passing/);
});

test("article hash links open in the reader without a publisher href", () => {
  const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const html = renderMarkdown(`- [Five newest](#article/${id})`);
  assert.match(html, new RegExp(`href="#article/${id}"`));
  assert.match(html, /class="sk-article-link"/);
  assert.match(html, new RegExp(`data-article-id="${id}"`));
  assert.match(html, /Open in reader/);
  assert.doesNotMatch(html, /target="_blank"/);
  assert.doesNotMatch(html, /foxnews\.com|newsmax\.com/i);
  assert.equal(parseArticleHash(`#article/${id}`), id);
  assert.equal(articleIdFromHref(`/articles/${id}`), id);
});

test("publisher headline markdown is not an outbound href", () => {
  const html = renderMarkdown("[A Fox headline](https://www.foxnews.com/politics/example)");
  assert.doesNotMatch(html, /href="https:\/\/www\.foxnews\.com/);
  assert.doesNotMatch(html, /target="_blank"/);
  assert.match(html, /class="sk-article-title"/);
  assert.match(html, /A Fox headline/);
});

test("chatArticleClick reads in-app article ids and blocks publisher hosts", () => {
  const id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const link = { getAttribute: (name: string) => (name === "data-article-id" ? id : name === "href" ? `#article/${id}` : null) };
  const closest = () => link;
  assert.deepEqual(chatArticleClick({ closest } as unknown as EventTarget), { kind: "article", id });
  const publisher = {
    getAttribute: (name: string) => (name === "href" ? "https://www.foxnews.com/story" : null),
    closest: function closest() {
      return this;
    },
  };
  assert.deepEqual(chatArticleClick(publisher as unknown as EventTarget), { kind: "stay" });
});
