import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  type MessageDetail,
  type MessageStatus,
  type MessageSummary,
  StaffAuthError,
  type Stats,
  staffRequest,
} from "../api";
import { CATEGORY_LABELS, PRIORITY_STYLES, STATUS_LABELS } from "./labels";

const TOKEN_KEY = "brightside-staff-token";
const REFRESH_MS = 20_000;

function readToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function saveToken(token: string) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable (private mode). The token then lasts until reload.
  }
}

type Filter = "open" | "sent" | "rejected";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "open", label: "To do" },
  { value: "sent", label: "Sent" },
  { value: "rejected", label: "Closed" },
];

const OPEN_STATUSES: MessageStatus[] = ["new", "needs_review", "triage_failed"];

export function StaffApp() {
  const [token, setToken] = useState(readToken);
  const [authError, setAuthError] = useState<string | null>(null);

  const signOut = useCallback((reason?: string) => {
    saveToken("");
    setToken("");
    setAuthError(reason ?? null);
  }, []);

  if (!token) {
    return (
      <SignIn
        error={authError}
        onSignIn={(value) => {
          saveToken(value);
          setAuthError(null);
          setToken(value);
        }}
      />
    );
  }
  return <Inbox token={token} onAuthFailure={signOut} />;
}

function SignIn({ error, onSignIn }: { error: string | null; onSignIn: (token: string) => void }) {
  const [value, setValue] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value.trim()) onSignIn(value.trim());
  };
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-5">
      <h1 className="text-3xl font-bold">Staff inbox</h1>
      <p className="mt-2 text-ink-soft">Enter the staff token set on the server.</p>
      <form onSubmit={submit} className="mt-6">
        <label className="block">
          Staff token
          <input
            type="password"
            autoComplete="current-password"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            className="mt-1 w-full rounded-xl border border-line bg-paper px-3 py-2.5 focus:border-sage focus:outline-none"
          />
        </label>
        {error && (
          <p role="alert" className="mt-3 text-alert">
            {error}
          </p>
        )}
        <button type="submit" className="mt-4 w-full rounded-xl bg-sage px-5 py-3 font-bold text-enamel hover:bg-sage-dark">
          Open inbox
        </button>
      </form>
    </main>
  );
}

function Inbox({ token, onAuthFailure }: { token: string; onAuthFailure: (reason?: string) => void }) {
  const [filter, setFilter] = useState<Filter>("open");
  const [messages, setMessages] = useState<MessageSummary[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const call = useCallback(
    async <T,>(path: string, init?: Parameters<typeof staffRequest>[2]): Promise<T> => {
      try {
        return await staffRequest<T>(token, path, init);
      } catch (error) {
        if (error instanceof StaffAuthError) onAuthFailure(error.message);
        throw error;
      }
    },
    [token, onAuthFailure],
  );

  const refresh = useCallback(() => {
    let active = true;
    Promise.all([call<MessageSummary[]>("/messages"), call<Stats>("/stats")])
      .then(([all, latestStats]) => {
        if (!active) return;
        setMessages(all);
        setStats(latestStats);
        setLoadError(null);
      })
      .catch((error: unknown) => {
        if (active && !(error instanceof StaffAuthError)) setLoadError((error as Error).message);
      });
    return () => {
      active = false;
    };
  }, [call]);

  useEffect(() => {
    let cancelLatest = refresh();
    const timer = window.setInterval(() => {
      cancelLatest();
      cancelLatest = refresh();
    }, REFRESH_MS);
    return () => {
      window.clearInterval(timer);
      cancelLatest();
    };
  }, [refresh]);

  const visible = messages.filter((m) =>
    filter === "open" ? OPEN_STATUSES.includes(m.status) : m.status === filter,
  );
  const waiting = stats ? stats.by_status.needs_review + stats.by_status.triage_failed : 0;

  return (
    <div className="min-h-dvh">
      <header className="border-b border-line bg-paper">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-5 py-4">
          <div>
            <h1 className="text-2xl font-bold">Staff inbox</h1>
            {stats && (
              <p className="text-sm text-ink-soft">
                {waiting} waiting for review. {stats.sent} {stats.sent === 1 ? "reply" : "replies"} sent,{" "}
                {stats.sent_without_edits} without edits to the draft.
              </p>
            )}
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => refresh()} className="rounded-lg border border-line px-3 py-2 hover:bg-enamel">
              Refresh
            </button>
            <button type="button" onClick={() => onAuthFailure()} className="rounded-lg px-3 py-2 text-ink-soft hover:bg-enamel">
              Sign out
            </button>
          </div>
        </div>
      </header>

      {loadError && (
        <p role="alert" className="mx-auto max-w-7xl px-5 pt-4 text-alert">
          {loadError}
        </p>
      )}

      <div className="mx-auto grid max-w-7xl gap-6 px-5 py-6 lg:grid-cols-[380px_1fr]">
        <section aria-label="Messages">
          <div role="tablist" aria-label="Filter messages" className="flex gap-1 rounded-xl bg-paper p-1">
            {FILTERS.map((f) => (
              <button
                key={f.value}
                type="button"
                role="tab"
                aria-selected={filter === f.value}
                onClick={() => setFilter(f.value)}
                className={`flex-1 rounded-lg px-3 py-2 text-sm font-bold ${filter === f.value ? "bg-ink text-enamel" : "text-ink-soft hover:bg-enamel"}`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <ul className="mt-4 space-y-2">
            {visible.length === 0 && (
              <li className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-ink-soft">
                {filter === "open"
                  ? "Nothing to review. New contact form messages appear here."
                  : "No messages here yet."}
              </li>
            )}
            {visible.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => setSelected(m.id)}
                  aria-current={selected === m.id}
                  className={`w-full rounded-xl border px-4 py-3 text-left ${selected === m.id ? "border-sage bg-paper" : "border-line bg-paper/60 hover:border-ink-soft"}`}
                >
                  <span className="flex items-center justify-between gap-3">
                    <span className="font-bold">{m.name}</span>
                    {m.priority && (
                      <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${PRIORITY_STYLES[m.priority] ?? ""}`}>
                        {m.priority}
                      </span>
                    )}
                  </span>
                  <span className="mt-1 block text-sm text-ink-soft">
                    {m.summary ?? m.subject}
                  </span>
                  <span className="mt-1 block text-xs text-ink-soft">
                    {m.category ? CATEGORY_LABELS[m.category] ?? m.category : STATUS_LABELS[m.status]}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section aria-label="Selected message">
          {selected === null ? (
            <p className="rounded-2xl border border-dashed border-line px-6 py-16 text-center text-ink-soft">
              Choose a message to see the original and the drafted reply.
            </p>
          ) : (
            // Remount when the status changes so a draft that finishes in the background shows up.
            <MessagePanel
              key={`${selected}-${messages.find((m) => m.id === selected)?.status ?? ""}`}
              id={selected}
              call={call}
              onChanged={() => refresh()}
            />
          )}
        </section>
      </div>
      <p className="mx-auto max-w-7xl px-5 pb-8 text-sm text-ink-soft">
        Demo: approved replies are saved as sent but no email is delivered.
      </p>
    </div>
  );
}

type Call = <T>(path: string, init?: Parameters<typeof staffRequest>[2]) => Promise<T>;

function MessagePanel({ id, call, onChanged }: { id: number; call: Call; onChanged: () => void }) {
  const [message, setMessage] = useState<MessageDetail | null>(null);
  const [reply, setReply] = useState("");
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let active = true;
    call<MessageDetail>(`/messages/${id}`)
      .then((detail) => {
        if (!active) return;
        setMessage(detail);
        setReply(detail.final_reply ?? detail.draft_reply ?? "");
      })
      .catch((e: unknown) => {
        if (active) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [call, id]);

  useEffect(() => load(), [load]);

  const act = async (path: string, done: string, body?: unknown) => {
    setWorking(true);
    setError(null);
    try {
      const updated = await call<MessageDetail | { status: string }>(`/messages/${id}${path}`, {
        method: "POST",
        body,
      });
      if ("id" in updated) setMessage(updated);
      else load();
      setNotice(done);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  };

  if (!message) {
    return error ? <p role="alert" className="text-alert">{error}</p> : <p className="text-ink-soft">Loading message</p>;
  }

  const reviewable = message.status === "needs_review" || message.status === "triage_failed";

  return (
    <article className="rounded-2xl border border-line bg-paper p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">{message.subject}</h2>
          <p className="mt-1 text-ink-soft">
            From {message.name}, <a className="underline" href={`mailto:${message.email}`}>{message.email}</a>
            {message.phone && <>, {message.phone}</>}
          </p>
          <p className="text-sm text-ink-soft">Received {new Date(message.created_at).toLocaleString()}</p>
        </div>
        <span className="rounded-full bg-enamel px-3 py-1 text-sm font-bold">{STATUS_LABELS[message.status]}</span>
      </header>

      {message.priority === "urgent" && (
        <p role="alert" className="mt-4 rounded-xl border-l-4 border-alert bg-alert-soft px-4 py-3 font-bold text-alert">
          Possible emergency. Call the patient now rather than waiting on email.
        </p>
      )}

      <h3 className="mt-6 text-sm font-bold text-ink-soft">Patient's message</h3>
      <p className="mt-1 rounded-xl bg-enamel px-4 py-3 whitespace-pre-wrap">{message.body}</p>

      {message.summary && (
        <p className="mt-4 text-ink-soft">
          <span className="font-bold text-ink">{CATEGORY_LABELS[message.category ?? ""] ?? message.category}.</span>{" "}
          {message.summary}
        </p>
      )}

      {message.status === "new" && <p className="mt-6 text-ink-soft">The assistant is still drafting a reply. Refresh in a few seconds.</p>}

      {message.status === "triage_failed" && (
        <div className="mt-6 rounded-xl border border-line px-4 py-3">
          <p>The assistant couldn't draft a reply for this message. Write one yourself or try again.</p>
          <button
            type="button"
            disabled={working}
            onClick={() => void act("/retry", "Drafting again")}
            className="mt-2 font-bold text-sage underline disabled:opacity-50"
          >
            Try drafting again
          </button>
        </div>
      )}

      {(reviewable || message.final_reply) && (
        <>
          <label htmlFor="reply" className="mt-6 block text-sm font-bold text-ink-soft">
            {reviewable ? "Reply (edit before sending)" : "Reply that was sent"}
          </label>
          <textarea
            id="reply"
            rows={10}
            maxLength={4000}
            readOnly={!reviewable}
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            className="mt-1 w-full rounded-xl border border-line px-4 py-3 focus:border-sage focus:outline-none read-only:bg-enamel"
          />
        </>
      )}

      {reviewable && (
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            disabled={working || !reply.trim()}
            onClick={() => void act("/approve", "Reply sent", { reply })}
            className="rounded-xl bg-sage px-5 py-3 font-bold text-enamel hover:bg-sage-dark disabled:opacity-40"
          >
            Send reply
          </button>
          <button
            type="button"
            disabled={working}
            onClick={() => void act("/reject", "Closed without reply")}
            className="rounded-xl border border-line px-5 py-3 font-bold hover:bg-enamel disabled:opacity-40"
          >
            Close without reply
          </button>
        </div>
      )}

      {notice && <p role="status" className="mt-4 font-bold text-sage">{notice}</p>}
      {error && <p role="alert" className="mt-4 text-alert">{error}</p>}
    </article>
  );
}
