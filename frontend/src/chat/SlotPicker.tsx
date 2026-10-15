import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import { type BookingOffer, type SlotOffer, requestBooking } from "../api";

type Props = {
  offer: BookingOffer;
  onChooseService: (label: string) => void;
};

function withArticle(noun: string): string {
  return `${/^[aeiou]/i.test(noun) ? "an" : "a"} ${noun}`;
}

const field =
  "mt-1 w-full rounded-lg border border-line bg-paper px-3 py-2 text-base focus:border-sage focus:outline-none";

export function SlotPicker({ offer, onChooseService }: Props) {
  const [chosen, setChosen] = useState<SlotOffer | null>(null);
  const [taken, setTaken] = useState<string[]>([]);
  const [form, setForm] = useState({ name: "", email: "", phone: "", website: "" });
  const [state, setState] = useState<"idle" | "sending" | "held">("idle");
  const [error, setError] = useState<string | null>(null);
  const [held, setHeld] = useState<string | null>(null);
  const id = useId();
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    // Opening the form can push it below the visible part of the chat.
    if (chosen) formRef.current?.scrollIntoView({ block: "nearest" });
  }, [chosen]);

  if (offer.choices.length > 0) {
    return (
      <div className="mt-3 flex flex-wrap gap-2">
        {offer.choices.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => onChooseService(c.label)}
            className="rounded-full border border-line px-3 py-1.5 text-sm hover:border-sage hover:text-sage"
          >
            {c.label}
          </button>
        ))}
      </div>
    );
  }

  if (!offer.service || offer.slots.length === 0) return null;

  if (state === "held" && held) {
    return (
      <div role="status" className="mt-3 rounded-xl border border-sage bg-paper px-4 py-3">
        <p className="font-bold">
          {offer.service_label}, {held}
        </p>
        <p className="mt-1 text-sm text-ink-soft">
          We're holding this time for you. The front desk will confirm it by email within one working day.
        </p>
      </div>
    );
  }

  const set = (key: keyof typeof form) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!chosen || !offer.service) return;
    setState("sending");
    setError(null);
    const result = await requestBooking({ service: offer.service, start: chosen.start, ...form });
    if (result.ok) {
      setHeld(result.when);
      setState("held");
      return;
    }
    if (result.taken) {
      setTaken((t) => [...t, chosen.start]);
      setChosen(null);
    }
    setError(result.error);
    setState("idle");
  };

  const open = offer.slots.filter((s) => !taken.includes(s.start));

  return (
    <div className="mt-3">
      <fieldset>
        <legend className="sr-only">Open times for {offer.service_label}</legend>
        <div className="flex flex-col gap-2">
          {open.map((slot) => {
            const selected = chosen?.start === slot.start;
            return (
              <button
                key={slot.start}
                type="button"
                aria-pressed={selected}
                onClick={() => {
                  setChosen(slot);
                  setError(null);
                }}
                className={`rounded-xl border px-4 py-2.5 text-left font-bold tabular-nums ${selected ? "border-sage bg-sage text-enamel" : "border-line bg-paper hover:border-sage"}`}
              >
                {slot.label}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-ink-soft">Times are in clinic time.</p>
      </fieldset>

      {open.length === 0 && (
        <p className="mt-2 text-sm">All of these times have been taken. Ask again to see new ones.</p>
      )}

      {chosen && (
        <form ref={formRef} onSubmit={(e) => void submit(e)} className="mt-4 space-y-3 rounded-xl border border-line bg-enamel p-4">
          <p className="font-bold">
            Hold {chosen.label} for {withArticle((offer.service_label ?? "appointment").toLowerCase())}
          </p>
          <label className="block text-sm">
            Full name
            <input required maxLength={100} autoComplete="name" value={form.name} onChange={set("name")} className={field} />
          </label>
          <label className="block text-sm">
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
          <label className="block text-sm">
            Phone <span className="text-ink-soft">(optional)</span>
            <input type="tel" maxLength={30} autoComplete="tel" value={form.phone} onChange={set("phone")} className={field} />
          </label>
          <div aria-hidden="true" className="absolute -left-[9999px] h-px w-px overflow-hidden">
            <label htmlFor={`${id}-website`}>Website</label>
            <input id={`${id}-website`} tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
          </div>
          <button
            type="submit"
            disabled={state === "sending"}
            className="w-full rounded-xl bg-sage px-4 py-2.5 font-bold text-enamel hover:bg-sage-dark disabled:opacity-50"
          >
            {state === "sending" ? "Holding this time" : "Hold this time"}
          </button>
        </form>
      )}

      {error && (
        <p role="alert" className="mt-2 text-sm text-alert">
          {error}
        </p>
      )}
    </div>
  );
}
