import { type FormEvent, useId, useState } from "react";

import { type ContactForm as Form, submitContact } from "../api";

const EMPTY: Form = { name: "", email: "", phone: "", subject: "", message: "", website: "" };

const field =
  "mt-1 w-full rounded-xl border border-line bg-paper px-3 py-2.5 focus:border-sage focus:outline-none";

export function ContactForm() {
  const [form, setForm] = useState<Form>(EMPTY);
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  const set = (key: keyof Form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setState("sending");
    setError(null);
    const result = await submitContact(form);
    if (result.ok) {
      setForm(EMPTY);
      setState("sent");
    } else {
      setError(result.error);
      setState("idle");
    }
  };

  if (state === "sent") {
    return (
      <div role="status" className="rounded-2xl border border-sage bg-paper p-6">
        <p className="font-display text-xl font-semibold">Message sent</p>
        <p className="mt-2 text-ink-soft">The front desk replies within one working day.</p>
        <button type="button" onClick={() => setState("idle")} className="mt-4 font-bold text-sage underline">
          Send another message
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="grid gap-4 sm:grid-cols-2" noValidate={false}>
      <label className="block">
        Name
        <input required maxLength={100} autoComplete="name" value={form.name} onChange={set("name")} className={field} />
      </label>
      <label className="block">
        Email
        <input
          required
          type="email"
          maxLength={254}
          autoComplete="email"
          value={form.email}
          onChange={set("email")}
          className={field}
        />
      </label>
      <label className="block">
        Phone <span className="text-ink-soft">(optional)</span>
        <input type="tel" maxLength={30} autoComplete="tel" value={form.phone} onChange={set("phone")} className={field} />
      </label>
      <label className="block">
        Subject
        <input required maxLength={150} value={form.subject} onChange={set("subject")} className={field} />
      </label>
      <label className="block sm:col-span-2">
        Message
        <textarea
          required
          minLength={10}
          maxLength={3000}
          rows={5}
          value={form.message}
          onChange={set("message")}
          aria-describedby={`${id}-hint`}
          className={field}
        />
        <span id={`${id}-hint`} className="mt-1 block text-sm text-ink-soft">
          Please don't include card numbers or detailed medical history.
        </span>
      </label>
      {/* Hidden from people; spam bots that fill every field get dropped by the server. */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
        <label>
          Website
          <input tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
        </label>
      </div>
      {error && (
        <p role="alert" className="text-alert sm:col-span-2">
          {error}
        </p>
      )}
      <div className="sm:col-span-2">
        <button
          type="submit"
          disabled={state === "sending"}
          className="rounded-xl bg-sage px-5 py-3 font-bold text-enamel hover:bg-sage-dark disabled:opacity-50"
        >
          {state === "sending" ? "Sending" : "Send message"}
        </button>
      </div>
    </form>
  );
}
