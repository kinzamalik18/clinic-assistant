import { useCallback, useEffect, useId, useRef, useState } from "react";

import { type BookingOffer, type ChatTurn, type ReplyKind, type Source, streamChat } from "../api";
import { LogoMark } from "../brand/Logo";
import { PHONE, PHONE_HREF } from "../clinic";
import { AnswerText } from "./AnswerText";
import { SlotPicker } from "./SlotPicker";

type Entry = {
  id: number;
  role: "user" | "assistant";
  text: string;
  kind?: ReplyKind;
  sources: Source[];
  offer?: BookingOffer;
  state: "streaming" | "done" | "error";
};

const STARTERS = [
  "How much is a cleaning?",
  "Which insurance plans do you take?",
  "What should I bring to my first visit?",
];

const BOOK_PROMPT = "I'd like to book an appointment";

const HISTORY_TURNS = 6;

function toHistory(entries: Entry[]): ChatTurn[] {
  return entries
    .filter((e) => e.state === "done" && e.text)
    .slice(-HISTORY_TURNS)
    .map((e) => ({ role: e.role, content: e.text.slice(0, 1000) }));
}

export function ChatWidget({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [openSource, setOpenSource] = useState<{ entry: number; number: number } | null>(null);
  const nextId = useRef(1);
  const abort = useRef<AbortController | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  useEffect(() => () => abort.current?.abort(), []);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [entries]);

  const update = useCallback((id: number, change: Partial<Entry> | ((e: Entry) => Partial<Entry>)) => {
    setEntries((all) =>
      all.map((e) => (e.id === id ? { ...e, ...(typeof change === "function" ? change(e) : change) } : e)),
    );
  }, []);

  const ask = async (question: string, mode: "chat" | "book" = "chat") => {
    const text = question.trim();
    if (!text || busy) return;
    const history = toHistory(entries);
    const userId = nextId.current++;
    const replyId = nextId.current++;
    setEntries((all) => [
      ...all,
      { id: userId, role: "user", text, sources: [], state: "done" },
      { id: replyId, role: "assistant", text: "", sources: [], state: "streaming" },
    ]);
    setDraft("");
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    await streamChat(
      text,
      history,
      {
        onMeta: (kind, sources) => update(replyId, { kind, sources }),
        onText: (piece) => update(replyId, (e) => ({ text: e.text + piece })),
        onSlots: (offer) => update(replyId, { offer }),
        onDone: (kind) =>
          update(replyId, (e) => ({ kind, state: "done", sources: kind === "answer" ? e.sources : [] })),
        onError: (message) => update(replyId, { text: message, state: "error", sources: [] }),
      },
      controller.signal,
      mode,
    );
    setBusy(false);
    input.current?.focus();
  };

  if (!open) return null;

  return (
    <section
      role="dialog"
      aria-labelledby={titleId}
      onKeyDown={(e) => e.key === "Escape" && onOpenChange(false)}
      className="fixed inset-x-0 bottom-0 z-40 flex h-[85dvh] flex-col border border-line bg-paper shadow-[0_12px_40px_-12px_rgb(29_43_58/0.35)] sm:inset-x-auto sm:right-6 sm:bottom-6 sm:h-[min(640px,calc(100dvh-3rem))] sm:w-[400px] sm:rounded-2xl"
    >
      <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
        <div className="flex items-start gap-3">
          <LogoMark size={32} />
          <div>
            <h2 id={titleId} className="text-lg font-semibold">
              Ask Brightside Dental
            </h2>
            <p className="text-sm text-ink-soft">Answers come from the clinic's own information.</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className="rounded-lg px-2 py-1 text-sm text-ink-soft hover:bg-enamel"
        >
          Close
        </button>
      </header>

      <div ref={log} aria-live="polite" className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {entries.length === 0 && (
          <div>
            <p className="text-ink-soft">
              Ask about prices, opening hours, insurance or your first visit. For pain, swelling or an injury,
              call us on{" "}
              <a href={PHONE_HREF} className="font-bold text-sage underline">
                {PHONE}
              </a>
              .
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void ask(BOOK_PROMPT, "book")}
                className="rounded-full bg-sage px-3 py-1.5 text-left text-sm font-bold text-enamel hover:bg-sage-dark"
              >
                Book an appointment
              </button>
              {STARTERS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => void ask(q)}
                  className="rounded-full border border-line px-3 py-1.5 text-left text-sm hover:border-sage hover:text-sage"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {entries.map((entry) =>
          entry.role === "user" ? (
            <p key={entry.id} className="ml-10 rounded-2xl rounded-br-sm bg-blush px-4 py-2.5 whitespace-pre-wrap">
              {entry.text}
            </p>
          ) : (
            <AssistantEntry
              key={entry.id}
              entry={entry}
              onChooseService={(label) => void ask(`I'd like to book: ${label}`, "book")}
              openSource={openSource?.entry === entry.id ? openSource.number : null}
              onCite={(number) =>
                setOpenSource((current) =>
                  current?.entry === entry.id && current.number === number ? null : { entry: entry.id, number },
                )
              }
            />
          ),
        )}
      </div>

      <form
        className="flex items-end gap-2 border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(draft);
        }}
      >
        <label htmlFor={`${titleId}-input`} className="sr-only">
          Your question
        </label>
        <textarea
          id={`${titleId}-input`}
          ref={input}
          rows={1}
          maxLength={500}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void ask(draft);
            }
          }}
          placeholder="Type your question"
          className="max-h-32 min-h-11 flex-1 resize-none rounded-xl border border-line bg-enamel px-3 py-2.5 focus:border-sage focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="h-11 rounded-xl bg-sage px-4 font-bold text-enamel hover:bg-sage-dark disabled:opacity-40"
        >
          Send
        </button>
      </form>
      <p className="px-5 pb-3 text-xs text-ink-soft">
        Demo assistant for a fictional clinic. Don't share personal health details.
      </p>
    </section>
  );
}

function AssistantEntry({
  entry,
  openSource,
  onCite,
  onChooseService,
}: {
  entry: Entry;
  openSource: number | null;
  onCite: (number: number) => void;
  onChooseService: (label: string) => void;
}) {
  const source = entry.sources.find((s) => s.number === openSource);

  if (entry.kind === "emergency" || entry.kind === "urgent") {
    const emergency = entry.kind === "emergency";
    return (
      <div
        role="alert"
        className={`rounded-xl border-l-4 px-4 py-3 ${emergency ? "border-alert bg-alert-soft" : "border-amber bg-amber-soft"}`}
      >
        <p className={`font-display text-lg font-semibold ${emergency ? "text-alert" : "text-amber"}`}>
          {emergency ? "Call 911 now" : "Call the clinic today"}
        </p>
        <p className="mt-1">{entry.text}</p>
        {!emergency && (
          <a
            href={PHONE_HREF}
            className="mt-3 inline-block rounded-lg bg-amber px-3 py-2 text-sm font-bold text-paper"
          >
            Call {PHONE}
          </a>
        )}
      </div>
    );
  }

  return (
    <div className="mr-6">
      <div className={entry.state === "error" ? "text-alert" : undefined}>
        {entry.text ? (
          <AnswerText text={entry.text} sources={entry.sources} onCite={onCite} />
        ) : (
          <p className="text-ink-soft">Looking that up</p>
        )}
      </div>
      {entry.offer && <SlotPicker offer={entry.offer} onChooseService={onChooseService} />}
      {source && (
        <figure className="mt-3 rounded-xl border border-line bg-enamel px-4 py-3 text-sm">
          <figcaption className="font-bold">
            {source.title}: {source.section}
          </figcaption>
          <p className="mt-1 whitespace-pre-line text-ink-soft">{source.text}</p>
        </figure>
      )}
    </div>
  );
}
