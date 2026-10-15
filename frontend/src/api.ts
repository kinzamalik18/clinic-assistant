import { SSEParser } from "./lib/sse";

export type ReplyKind = "answer" | "not_covered" | "emergency" | "urgent" | "medication";

export type Source = { number: number; id: string; title: string; section: string; text: string };

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatHandlers = {
  onMeta: (kind: ReplyKind, sources: Source[]) => void;
  onText: (text: string) => void;
  onDone: (kind: ReplyKind) => void;
  onError: (message: string) => void;
};

const NETWORK_ERROR = "The assistant couldn't be reached. Check your connection and try again.";

export async function streamChat(
  message: string,
  history: ChatTurn[],
  handlers: ChatHandlers,
  signal: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch("/api/chat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message, history }),
      signal,
    });
  } catch (error) {
    if (!signal.aborted) handlers.onError(NETWORK_ERROR);
    void error;
    return;
  }
  if (response.status === 429) {
    handlers.onError("You've sent a lot of questions in a short time. Wait a minute and try again.");
    return;
  }
  if (!response.ok || !response.body) {
    handlers.onError(NETWORK_ERROR);
    return;
  }

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SSEParser();
  let finished = false;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      for (const { event, data } of parser.push(value)) {
        const payload = data as Record<string, unknown>;
        if (event === "meta") {
          handlers.onMeta(payload.kind as ReplyKind, (payload.sources as Source[]) ?? []);
        } else if (event === "delta") {
          handlers.onText(String(payload.text ?? ""));
        } else if (event === "done") {
          finished = true;
          handlers.onDone(payload.kind as ReplyKind);
        } else if (event === "error") {
          finished = true;
          handlers.onError(String(payload.message ?? NETWORK_ERROR));
        }
      }
    }
  } catch {
    if (signal.aborted) return;
  }
  if (!finished && !signal.aborted) handlers.onError(NETWORK_ERROR);
}

export type ContactForm = {
  name: string;
  email: string;
  phone: string;
  subject: string;
  message: string;
  website: string;
};

export type SubmitResult = { ok: true } | { ok: false; error: string };

export async function submitContact(form: ContactForm): Promise<SubmitResult> {
  let response: Response;
  try {
    response = await fetch("/api/messages", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...form, phone: form.phone || null }),
    });
  } catch {
    return { ok: false, error: "Your message couldn't be sent. Check your connection and try again." };
  }
  if (response.ok) return { ok: true };
  if (response.status === 429) {
    return { ok: false, error: "You've already sent several messages. Please call us instead." };
  }
  if (response.status === 422) {
    return { ok: false, error: "Check the highlighted fields. The message needs at least 10 characters." };
  }
  return { ok: false, error: "Your message couldn't be sent. Please call us instead." };
}

// Staff API

export type MessageSummary = {
  id: number;
  created_at: string;
  name: string;
  subject: string;
  status: MessageStatus;
  category: string | null;
  priority: "urgent" | "high" | "normal" | "low" | null;
  summary: string | null;
};

export type MessageStatus = "new" | "needs_review" | "triage_failed" | "sent" | "rejected";

export type MessageDetail = MessageSummary & {
  email: string;
  phone: string | null;
  body: string;
  draft_reply: string | null;
  final_reply: string | null;
  edited: number | null;
  reviewed_at: string | null;
};

export type Stats = {
  by_status: Record<MessageStatus, number>;
  by_category: Record<string, number>;
  sent: number;
  sent_without_edits: number;
};

export class StaffAuthError extends Error {}

export class StaffApiError extends Error {}

export async function staffRequest<T>(
  token: string,
  path: string,
  init: { method?: "GET" | "POST"; body?: unknown } = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/staff${path}`, {
      method: init.method ?? "GET",
      headers: {
        authorization: `Bearer ${token}`,
        ...(init.body === undefined ? {} : { "content-type": "application/json" }),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new StaffApiError("The server couldn't be reached.");
  }
  if (response.status === 401) throw new StaffAuthError("That staff token isn't valid.");
  if (response.status === 503) {
    throw new StaffAuthError("Staff access is turned off on the server. Set STAFF_TOKEN first.");
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message =
      detail && typeof detail.detail === "string" ? detail.detail : `Request failed (${response.status}).`;
    throw new StaffApiError(message);
  }
  return (await response.json()) as T;
}
