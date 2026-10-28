// What gets read aloud: the explanation, not the Markdown (see
// backend/app/voice/speakable.py - kept in step by tests on the same sample).

export const CODE_ON_SCREEN = "The code is shown on screen.";
export const REST_ON_SCREEN = "The rest is on screen.";
const DEFAULT_MAX_CHARS = 1100;

const FENCE = /```[\s\S]*?(?:```|$)/g;
const REFERENCE_SECTION = /\n\s*\*\*(?:Line by line|Original code from the document)\*\*/i;
const CITATION = /\s*\[\d{1,3}\]/g;
const LIST_MARKER = /^\s*(?:[-*•]|\d+[.)])\s+/gm;
const HEADING = /^\s{0,3}#{1,6}\s*/gm;

export function speakableText(markdown: string, maxChars: number = DEFAULT_MAX_CHARS): string {
  const cut = REFERENCE_SECTION.exec(markdown);
  let text = cut ? markdown.slice(0, cut.index) : markdown;
  const hadReferenceSection = cut !== null;

  text = text.replace(FENCE, ` ${CODE_ON_SCREEN} `);
  text = text.replace(/`/g, "").replace(CITATION, "").replace(HEADING, "").replace(LIST_MARKER, "");
  text = text.replace(/\*\*/g, "").replace(/__/g, "");
  text = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => (/[.!?:]$/.test(line) ? line : `${line}.`))
    .join(" ");
  text = text.replace(/\s+/g, " ").trim();
  text = text.replace(new RegExp(`(?:${CODE_ON_SCREEN.replace(/\./g, "\\.")}\\s*){2,}`, "g"), `${CODE_ON_SCREEN} `);

  let truncated = false;
  if (text.length > maxChars) {
    const window = text.slice(0, maxChars);
    let end = -1;
    for (const match of window.matchAll(/[.!?](?=\s)/g)) end = (match.index ?? 0) + 1;
    text = end > 0 ? window.slice(0, end).trim() : window.trimEnd();
    truncated = true;
  }
  if (truncated || hadReferenceSection) text = `${text} ${REST_ON_SCREEN}`.trim();
  return text;
}
