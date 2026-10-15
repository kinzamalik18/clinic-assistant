import { useCallback, useEffect, useState } from "react";

import { type Booking, type BookingStatus, StaffAuthError } from "../api";
import type { Call } from "./types";

type View = "requested" | "confirmed" | "closed";

const VIEWS: { value: View; label: string }[] = [
  { value: "requested", label: "To confirm" },
  { value: "confirmed", label: "Confirmed" },
  { value: "closed", label: "Declined or cancelled" },
];

const CLOSED: BookingStatus[] = ["declined", "cancelled"];
const REFRESH_MS = 20_000;

const ACTION_DONE: Record<string, string> = {
  confirm: "Appointment confirmed",
  decline: "Request declined",
  cancel: "Appointment cancelled",
};

export function Appointments({ call, reloadKey }: { call: Call; reloadKey: number }) {
  const [view, setView] = useState<View>("requested");
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [working, setWorking] = useState<number | null>(null);

  const load = useCallback(() => {
    let active = true;
    call<Booking[]>("/bookings")
      .then((all) => {
        if (!active) return;
        setBookings(all);
        setError(null);
      })
      .catch((e: unknown) => {
        if (active && !(e instanceof StaffAuthError)) setError((e as Error).message);
      });
    return () => {
      active = false;
    };
  }, [call]);

  useEffect(() => {
    void reloadKey;
    let cancel = load();
    const timer = window.setInterval(() => {
      cancel();
      cancel = load();
    }, REFRESH_MS);
    return () => {
      window.clearInterval(timer);
      cancel();
    };
  }, [load, reloadKey]);

  const act = async (booking: Booking, action: "confirm" | "decline" | "cancel") => {
    setWorking(booking.id);
    setError(null);
    try {
      await call<Booking>(`/bookings/${booking.id}/${action}`, { method: "POST" });
      setNotice(`${ACTION_DONE[action]}: ${booking.name}, ${booking.when}`);
      load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(null);
    }
  };

  const visible = bookings.filter((b) =>
    view === "closed" ? CLOSED.includes(b.status) : b.status === view,
  );
  const toConfirm = bookings.filter((b) => b.status === "requested").length;

  return (
    <section aria-label="Appointments" className="mx-auto max-w-4xl px-5 py-6">
      <p className="text-ink-soft">
        {toConfirm === 0
          ? "No appointment requests waiting."
          : `${toConfirm} appointment ${toConfirm === 1 ? "request" : "requests"} waiting to be confirmed.`}{" "}
        Requested times stay held until you confirm or decline them.
      </p>

      <div role="tablist" aria-label="Filter appointments" className="mt-4 flex gap-1 rounded-xl bg-paper p-1">
        {VIEWS.map((v) => (
          <button
            key={v.value}
            type="button"
            role="tab"
            aria-selected={view === v.value}
            onClick={() => setView(v.value)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm font-bold ${view === v.value ? "bg-ink text-enamel" : "text-ink-soft hover:bg-enamel"}`}
          >
            {v.label}
          </button>
        ))}
      </div>

      {notice && (
        <p role="status" className="mt-4 font-bold text-sage">
          {notice}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 text-alert">
          {error}
        </p>
      )}

      <ul className="mt-4 space-y-3">
        {visible.length === 0 && (
          <li className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-ink-soft">
            {view === "requested"
              ? "Nothing to confirm. Times patients pick in the chat appear here."
              : "No appointments here yet."}
          </li>
        )}
        {visible.map((b) => (
          <li key={b.id} className="rounded-2xl border border-line bg-paper p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="font-display text-xl font-semibold tabular-nums">{b.when}</p>
                <p className="mt-0.5">
                  {b.service_label}, room {b.room}
                </p>
                <p className="mt-2 text-ink-soft">
                  {b.name},{" "}
                  <a className="underline" href={`mailto:${b.email}`}>
                    {b.email}
                  </a>
                  {b.phone && <>, {b.phone}</>}
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {b.status === "requested" && (
                  <>
                    <button
                      type="button"
                      disabled={working === b.id}
                      onClick={() => void act(b, "confirm")}
                      className="rounded-xl bg-sage px-4 py-2.5 font-bold text-enamel hover:bg-sage-dark disabled:opacity-40"
                    >
                      Confirm
                    </button>
                    <button
                      type="button"
                      disabled={working === b.id}
                      onClick={() => void act(b, "decline")}
                      className="rounded-xl border border-line px-4 py-2.5 font-bold hover:bg-enamel disabled:opacity-40"
                    >
                      Decline
                    </button>
                  </>
                )}
                {b.status === "confirmed" && (
                  <button
                    type="button"
                    disabled={working === b.id}
                    onClick={() => void act(b, "cancel")}
                    className="rounded-xl border border-line px-4 py-2.5 font-bold hover:bg-enamel disabled:opacity-40"
                  >
                    Cancel appointment
                  </button>
                )}
                {CLOSED.includes(b.status) && (
                  <span className="rounded-full bg-enamel px-3 py-1 text-sm font-bold text-ink-soft">
                    {b.status === "declined" ? "Declined" : "Cancelled"}
                  </span>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
