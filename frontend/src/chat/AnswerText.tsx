import type { ReactNode } from "react";

import type { Source } from "../api";

type Props = {
  text: string;
  sources: Source[];
  onCite: (number: number) => void;
};

const CITATION = /\[(\d+)\]/g;

/**
 * Render model text as plain paragraphs and lists. Text is never parsed as HTML, so
 * anything the model writes is shown as text. Citations like [2] become buttons that
 * open the matching source; numbers with no matching source are dropped.
 */
export function AnswerText({ text, sources, onCite }: Props) {
  const known = new Set(sources.map((s) => s.number));

  const inline = (line: string, key: string): ReactNode[] => {
    const parts: ReactNode[] = [];
    let last = 0;
    const clean = line.replace(/\*\*(.+?)\*\*/g, "$1");
    for (const match of clean.matchAll(CITATION)) {
      const index = match.index ?? 0;
      parts.push(clean.slice(last, index).replace(/\s+$/, index > 0 ? " " : ""));
      const number = Number(match[1]);
      if (known.has(number)) {
        parts.push(
          <button
            key={`${key}-c${index}`}
            type="button"
            onClick={() => onCite(number)}
            className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-blush px-1 align-text-top text-xs font-bold text-ink hover:bg-sage hover:text-enamel focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sage"
            aria-label={`Show source ${number}`}
          >
            {number}
          </button>,
        );
      }
      last = index + match[0].length;
    }
    parts.push(clean.slice(last));
    return parts;
  };

  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flushList = () => {
    if (list.length === 0) return;
    const items = list;
    blocks.push(
      <ul key={`ul${blocks.length}`} className="my-2 list-disc space-y-1 pl-5">
        {items.map((item, i) => (
          <li key={i}>{inline(item, `li${blocks.length}-${i}`)}</li>
        ))}
      </ul>,
    );
    list = [];
  };

  text.split("\n").forEach((raw, i) => {
    const line = raw.trim();
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      list.push(bullet[1] ?? "");
      return;
    }
    flushList();
    if (line) {
      blocks.push(
        <p key={`p${i}`} className="my-1.5 first:mt-0 last:mb-0">
          {inline(line, `p${i}`)}
        </p>,
      );
    }
  });
  flushList();

  return <>{blocks}</>;
}
