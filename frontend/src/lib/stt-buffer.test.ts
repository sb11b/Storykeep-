import assert from "node:assert/strict";
import test from "node:test";
import { collapseRestatedSpeech, foldSpeech, lastCommittedSentence, newFinalSegment, normalizeSpoken } from "./stt-buffer";

test("normalizeSpoken collapses whitespace", () => {
  assert.equal(normalizeSpoken("  Hello   there\n"), "Hello there");
});

test("newFinalSegment inserts the first final in full", () => {
  assert.equal(newFinalSegment("The slope is steep.", "", ""), "The slope is steep.");
});

test("newFinalSegment skips a repeat of the committed utterance", () => {
  assert.equal(newFinalSegment("The slope is steep.", "The slope is steep.", "The slope is steep."), "");
});

test("newFinalSegment keeps only the remainder of a cumulative final", () => {
  const have = "The slope is steep.";
  const incoming = "The slope is steep. The derivative is the slope.";
  assert.equal(newFinalSegment(incoming, have, have), "The derivative is the slope.");
});

test("newFinalSegment does not re-insert a prefix already committed", () => {
  const have = "Hello there how are you";
  assert.equal(newFinalSegment("Hello there", have, have), "");
});

test("newFinalSegment uses the last committed sentence as the dedup prefix", () => {
  const have = "Hello there. How are you";
  assert.equal(newFinalSegment("How are you today", have, have), "today");
});

test("lastCommittedSentence splits on punctuation", () => {
  assert.equal(lastCommittedSentence("One. Two! Three"), "Three");
});

test("newFinalSegment skips text already sitting at the end of the field", () => {
  assert.equal(newFinalSegment("curve", "", "The slope of the curve"), "");
});

test("newFinalSegment peels stacked copies of the same paragraph", () => {
  const para =
    "The GDPR requires a lawful basis for processing personal data of EU residents including consent contract legal obligation and legitimate interests.";
  const stacked = `${para} ${para} ${para} And a new clause.`;
  assert.equal(newFinalSegment(stacked, para, para), "And a new clause.");
});

test("newFinalSegment ignores an exact duplicate of the last paragraph", () => {
  const para = "The GDPR requires a lawful basis for processing personal data.";
  assert.equal(newFinalSegment(para, para, para), "");
  assert.equal(newFinalSegment(`${para} ${para}`, para, para), "");
});

const GDPR_RAW_DUMP = `Every user is informed about their privacy rights under GDPR with a data protection policy which includes :
- right to process the data at any time,
- right to view and access their personal data.
- right to get the copy of the stored data.
- Right to remove the stored data under certain circumstances. Every user is informed about their privacy rights under GDPR with a data protection policy which includes: right to process the data at any time, right to view and access their personal data, right to get the copy of the stored data, right to remove the stored data under certain circumstances. Right to file complaints That protection is an important part of corporate social responsibility in a digital market. It is also required for an institutional risk and an essential compliance function for those organizations that collect, use, or share personal information or other potentially sensitive consumer data. GDPR is a legal framework setting guidelines for the collection and processing of personal data within the EU. It has some principles for data management and the rights of the end Data protection is an important part of corporate social responsibility in a digital market. It is also required for an institutional risk and an essential compliance function for those organizations that collect, use, or share personal information or other potentially sensitive consumer data. GDPR is a legal framework setting guidelines for the collection and processing of personal data within the EU. It has some principles for data management and the rights of the individual. All companies that deal with data of EU citizens should follow the GDPR law, as it is critical regulation for corporate compliance officers in many financial sectors. Some of the types of privacy data that are protected by the GDPR include, but aren't limited to Basic identity information of an individual. Name, address, and ID numbers. Web data, location, IP address, cookie data, etc.`;

function countFolded(haystack: string, needle: string): number {
  const h = foldSpeech(haystack);
  const n = foldSpeech(needle);
  let count = 0;
  let index = 0;
  while (n && (index = h.indexOf(n, index)) !== -1) {
    count += 1;
    index += n.length;
  }
  return count;
}

test("GDPR session dump keeps one copy of each restated paragraph", () => {
  const merged = collapseRestatedSpeech(GDPR_RAW_DUMP);
  assert.equal(countFolded(merged, "Every user is informed"), 1);
  assert.equal(countFolded(merged, "protection is an important part of corporate social responsibility"), 1);
  assert.equal(countFolded(merged, "Data protection is an important part"), 0);
  assert.equal(countFolded(merged, "right to view and access their personal data") >= 1, true);
  assert.match(merged, /right to file complaints/i);
  assert.equal(countFolded(merged, "it has some principles for data management"), 1);
  assert.match(merged, /rights of the individual/i);
  const delta = newFinalSegment(GDPR_RAW_DUMP, "", "");
  assert.equal(countFolded(delta, "Every user is informed"), 1);
  assert.equal(countFolded(delta, "protection is an important part of corporate social responsibility"), 1);
  assert.equal(countFolded(delta, "Data protection is an important part"), 0);
});

test("newFinalSegment keeps only new words after a punctuation-ignoring committed tail", () => {
  const have = "The GDPR replaces the EU's Data Protection Directive established in 1995.";
  const incoming =
    "the gdpr replaces the eu s data protection directive established in 1995\nIt is based on recommendations proposed by the OECD.";
  const out = newFinalSegment(incoming, have, have);
  assert.equal(countFolded(out, "the gdpr replaces"), 0);
  assert.match(foldSpeech(out), /it is based on recommendations proposed by the oecd/);
});

test("Data Protection Directive heading does not leak into the OECD sentence", () => {
  const committed = `Here are a few:
Data Protection Directive: A directive that regulates the processing of personal data within the EU. It is an important component of EU privacy and human rights law. The GDPR replaces the EU's Data Protection Directive established in 1995.`;
  const incoming =
    "It is based on recommendations proposed by the Organization for Economic Here are a few: Data Cooperation and development. OECD. The seven principles governing the OECD's recommendations for the protection of personal data were noticed, purpose, consent, security, disclosure, access and accountability.";
  const out = newFinalSegment(incoming, committed, committed);
  assert.equal(countFolded(out, "here are a few"), 0);
  assert.doesNotMatch(out, /Here are a few:/i);
  assert.match(foldSpeech(out), /organization for economic/);
  assert.match(out, /noticed|notice/i);
});
