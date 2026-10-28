"use client";

import { Check, Copy } from "lucide-react";
import { Fragment, useState, type ReactNode } from "react";

/**
 * A deliberately small, dependency-free Markdown renderer for assistant
 * answers: fenced code blocks (copyable, horizontally scrollable, indentation
 * preserved), headings, bullet/numbered lists, paragraphs, **bold**, `inline
 * code` and `[n]` citation markers.
 *
 * Safety: every piece of text is rendered as a React text node. There is no
 * `dangerouslySetInnerHTML` and no HTML pass-through, so a document (or a
 * model that was talked into it) cannot inject markup or script into the page.
 */

type Block =
  | { kind: "code"; lang: string; text: string }
  | { kind: "heading"; level: number; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "paragraph"; text: string };

const FENCE = /^\s*```\s*([\w+#.-]*)\s*$/;
const HEADING = /^(#{1,4})\s+(.+?)\s*#*\s*$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const ORDERED = /^\s*\d+[.)]\s+(.*)$/;

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const fence = FENCE.exec(line);
    if (fence) {
      const body: string[] = [];
      i += 1;
      // An unterminated fence runs to the end of the answer.
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // closing fence
      blocks.push({ kind: "code", lang: fence[1] ?? "", text: body.join("\n") });
      continue;
    }
    if (line.trim() === "") {
      i += 1;
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      i += 1;
      continue;
    }
    const bullet = BULLET.exec(line);
    const ordered = ORDERED.exec(line);
    if (bullet || ordered) {
      const isOrdered = !bullet;
      const matcher = isOrdered ? ORDERED : BULLET;
      const items: string[] = [];
      while (i < lines.length) {
        const m = matcher.exec(lines[i]);
        if (m) {
          items.push(m[1]);
          i += 1;
        } else if (/^\s{2,}\S/.test(lines[i]) && items.length > 0) {
          items[items.length - 1] += " " + lines[i].trim(); // wrapped item text
          i += 1;
        } else {
          break;
        }
      }
      blocks.push({ kind: "list", ordered: isOrdered, items });
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !FENCE.test(lines[i]) &&
      !HEADING.test(lines[i]) &&
      !BULLET.test(lines[i]) &&
      !ORDERED.test(lines[i])
    ) {
      para.push(lines[i]);
      i += 1;
    }
    blocks.push({ kind: "paragraph", text: para.join("\n") });
  }
  return blocks;
}

const INLINE = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\[\d{1,3}\])/g;

function renderInline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return (
        <code key={index} className="rounded bg-slate-200/70 px-1 py-0.5 font-mono text-[0.85em]">
          {part.slice(1, -1)}
        </code>
      );
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (/^\[\d{1,3}\]$/.test(part)) {
      return (
        <sup key={index} className="mx-0.5 font-medium text-indigo-700">
          {part}
        </sup>
      );
    }
    // Keep single newlines inside a paragraph visible.
    const pieces = part.split("\n");
    return (
      <Fragment key={index}>
        {pieces.map((piece, i) => (
          <Fragment key={i}>
            {i > 0 && <br />}
            {piece}
          </Fragment>
        ))}
      </Fragment>
    );
  });
}

function CodeBlock({ lang, text }: { lang: string; text: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked (permissions / insecure context); the code
      // is still selectable, so fail quietly.
    }
  }

  return (
    <div className="my-2 overflow-hidden rounded-lg border border-slate-700 bg-slate-900 text-slate-100">
      <div className="flex items-center justify-between border-b border-slate-700 px-3 py-1 text-[11px] text-slate-400">
        <span>{lang || "code"}</span>
        <button
          type="button"
          onClick={copy}
          aria-label="Copy code"
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 hover:bg-slate-700 hover:text-white"
        >
          {copied ? <Check className="size-3" aria-hidden="true" /> : <Copy className="size-3" aria-hidden="true" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-xs leading-5">
        <code className="font-mono whitespace-pre">{text}</code>
      </pre>
    </div>
  );
}

export function Markdown({ content }: { content: string }) {
  const blocks = parseBlocks(content);
  return (
    <div className="flex flex-col gap-2 break-words">
      {blocks.map((block, index) => {
        switch (block.kind) {
          case "code":
            return <CodeBlock key={index} lang={block.lang} text={block.text} />;
          case "heading":
            return (
              <p key={index} className="mt-1 font-semibold text-slate-950">
                {renderInline(block.text)}
              </p>
            );
          case "list": {
            const ListTag = block.ordered ? "ol" : "ul";
            return (
              <ListTag
                key={index}
                className={`${block.ordered ? "list-decimal" : "list-disc"} flex flex-col gap-1 pl-5`}
              >
                {block.items.map((item, i) => (
                  <li key={i}>{renderInline(item)}</li>
                ))}
              </ListTag>
            );
          }
          default:
            return <p key={index}>{renderInline(block.text)}</p>;
        }
      })}
    </div>
  );
}
