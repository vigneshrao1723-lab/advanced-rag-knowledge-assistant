import { describe, expect, it } from "vitest";

import { CODE_ON_SCREEN, REST_ON_SCREEN, speakableText } from "@/lib/speakable";

// The same sample as backend/tests/test_speakable.py.
const ANSWER = `**What it does**: Program 3 sorts an array using bubble sort. [1]

### How it works
1. The outer loop runs \`n-1\` times. [1]
2. The inner loop compares neighbours.

\`\`\`c
void bubble_sort(int a[], int n) {
    for (int i = 0; i < n; i++) {}
}
\`\`\`

**Output**: it prints \`1 2 4 5 8\`.

**Line by line**
- \`void bubble_sort(int a[], int n) {\` — Defines the function. [1]

**Original code from the document** [1]
\`\`\`c
void bubble_sort(int a[], int n) {}
\`\`\``;

describe("speakableText", () => {
  it("keeps the explanation and drops markup, citations and code", () => {
    const spoken = speakableText(ANSWER);
    expect(spoken).toContain("Program 3 sorts an array using bubble sort.");
    expect(spoken).toContain("The outer loop runs n-1 times.");
    expect(spoken).toContain("it prints 1 2 4 5 8.");
    for (const noise of ["**", "`", "###", "[1]", "void bubble_sort", "for (int i"]) {
      expect(spoken).not.toContain(noise);
    }
    expect(spoken.split(CODE_ON_SCREEN).length - 1).toBe(1);
  });

  it("stops before the reference sections and says so", () => {
    const spoken = speakableText(ANSWER);
    expect(spoken).not.toContain("Defines the function");
    expect(spoken.endsWith(REST_ON_SCREEN)).toBe(true);
  });

  it("cuts long answers at a sentence boundary", () => {
    const long = Array.from({ length: 200 }, (_, i) => `Sentence number ${i} explains something.`).join(" ");
    const spoken = speakableText(long, 300);
    expect(spoken.endsWith(`explains something. ${REST_ON_SCREEN}`)).toBe(true);
    expect(spoken.length).toBeLessThanOrEqual(300 + REST_ON_SCREEN.length + 1);
  });

  it("leaves short plain text alone, and never reads an unterminated code fence", () => {
    expect(speakableText("The refund window is thirty days.")).toBe("The refund window is thirty days.");
    const spoken = speakableText("Here is the code:\n```c\nint main() {\n    return 0;");
    expect(spoken).not.toContain("int main");
    expect(spoken).toContain(CODE_ON_SCREEN);
    expect(speakableText("")).toBe("");
  });
});
