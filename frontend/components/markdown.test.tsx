import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown, parseBlocks } from "./markdown";

describe("parseBlocks", () => {
  it("keeps code exactly, including indentation and blank lines", () => {
    const source = "Intro\n```c\nint main() {\n    if (x) {\n\n        y();\n    }\n}\n```\nDone";
    const blocks = parseBlocks(source);
    expect(blocks.map((b) => b.kind)).toEqual(["paragraph", "code", "paragraph"]);
    const code = blocks[1];
    expect(code.kind === "code" && code.lang).toBe("c");
    expect(code.kind === "code" && code.text).toBe(
      "int main() {\n    if (x) {\n\n        y();\n    }\n}"
    );
  });

  it("treats an unterminated fence as code to the end", () => {
    const blocks = parseBlocks("```python\nprint('hi')\n    nested");
    expect(blocks).toEqual([{ kind: "code", lang: "python", text: "print('hi')\n    nested" }]);
  });

  it("parses headings, bullets and numbered lists", () => {
    const blocks = parseBlocks("## What it does\n- one\n- two\n\n1. first\n2. second");
    expect(blocks).toEqual([
      { kind: "heading", level: 2, text: "What it does" },
      { kind: "list", ordered: false, items: ["one", "two"] },
      { kind: "list", ordered: true, items: ["first", "second"] },
    ]);
  });
});

describe("Markdown", () => {
  it("renders code in a pre block with a copy button and preserves indentation", () => {
    const { container } = render(<Markdown content={"```c\nif (a) {\n    b();\n}\n```"} />);
    expect(container.querySelector("pre code")?.textContent).toBe("if (a) {\n    b();\n}");
    expect(screen.getByRole("button", { name: "Copy code" })).toBeTruthy();
  });

  it("renders bold, inline code and citation markers", () => {
    const { container } = render(<Markdown content={"Use **MPI_Send** or `MPI_Recv` [2]."} />);
    expect(container.querySelector("strong")?.textContent).toBe("MPI_Send");
    expect(container.querySelector("p code")?.textContent).toBe("MPI_Recv");
    expect(container.querySelector("sup")?.textContent).toBe("[2]");
  });

  it("never turns document or model text into HTML", () => {
    const evil = '<img src=x onerror="alert(1)"> <script>alert(2)</script> [link](javascript:alert(3))';
    const { container } = render(<Markdown content={evil} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("<script>alert(2)</script>");
  });

  it("keeps single newlines inside a paragraph", () => {
    const { container } = render(<Markdown content={"line one\nline two"} />);
    expect(container.querySelectorAll("br")).toHaveLength(1);
  });
});
