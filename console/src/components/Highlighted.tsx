"use client";

import { codePointToUtf16 } from "@/lib/offsets";
import type { LemmaItem } from "@/lib/types";

/**
 * Renders the original text with each lemma span marked.
 *
 * Degrades to plain text when the response carried no offsets (token input).
 * `surface` is deliberately not compared against the slice: Korean contracted
 * verbs share one span between two morphemes, so they differ by design.
 */
export function Highlighted({
  text,
  items,
  offsetUnit,
  onHover,
}: {
  text: string;
  items: LemmaItem[];
  offsetUnit: "unicode_code_point" | null;
  onHover?: (item: LemmaItem | null) => void;
}) {
  if (!offsetUnit || items.some((i) => i.start === undefined || i.end === undefined)) {
    return <p className="font-mono text-sm">{text}</p>;
  }

  const marks = items.map((item) => ({
    item,
    start: codePointToUtf16(text, item.start!),
    end: codePointToUtf16(text, item.end!),
  }));

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  for (const [index, mark] of marks.entries()) {
    if (mark.start > cursor) {
      parts.push(<span key={`gap-${index}`}>{text.slice(cursor, mark.start)}</span>);
    }
    parts.push(
      <mark
        key={`mark-${index}`}
        onMouseEnter={() => onHover?.(mark.item)}
        onMouseLeave={() => onHover?.(null)}
        className={
          mark.item.prov === "identity"
            ? "bg-amber-100 text-amber-900"
            : "bg-emerald-100 text-emerald-900"
        }
      >
        {text.slice(mark.start, mark.end)}
      </mark>,
    );
    cursor = Math.max(cursor, mark.end);
  }
  if (cursor < text.length) {
    parts.push(<span key="tail">{text.slice(cursor)}</span>);
  }

  return <p className="font-mono text-sm leading-relaxed">{parts}</p>;
}
