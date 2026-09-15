import { parseSections } from "@/lib/include-chunk";

export const WORK_IN_JUNIOR_EVENT = "storykeep-work-in-junior";

export type WorkInJuniorDetail = {
  noteId: string;
  title?: string;
};

export function openWorkInJunior(detail: WorkInJuniorDetail) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<WorkInJuniorDetail>(WORK_IN_JUNIOR_EVENT, { detail }));
}

export function headingFromInstruction(message: string, body: string): string | null {
  const text = (message || "").toLowerCase();
  if (!text.trim() || !body) return null;
  const sections = parseSections(body);
  for (const section of sections) {
    const label = section.title.toLowerCase();
    if (label !== "opening" && label && text.includes(label)) return section.title;
  }
  const numbered = text.match(/section\s+(\d+)/i);
  if (!numbered) return null;
  const index = Number(numbered[1]);
  const headings = [...body.matchAll(/^(#{2,6})\s+(.+?)\s*$/gm)].map((match) => (match[2] || "").trim()).filter(Boolean);
  if (index >= 1 && index <= headings.length) return headings[index - 1]!;
  return null;
}
