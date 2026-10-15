import { useEffect, useState } from "react";

import { Logo } from "../brand/Logo";
import { ChatWidget } from "../chat/ChatWidget";
import { ADDRESS, DAY_NAMES, HOURS, INSURERS, OUT_OF_HOURS_PHONE, PHONE, PHONE_HREF, PRICES } from "../clinic";
import { formatTime, openStatus } from "../lib/hours";
import { ContactForm } from "./ContactForm";

// Show Monday first, the way people read a week of opening hours.
const WEEK_ORDER = [1, 2, 3, 4, 5, 6, 0];

export function LandingPage() {
  const [now, setNow] = useState(() => new Date());
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const status = openStatus(now);
  const today = now.getDay();

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:m-3 focus:rounded focus:bg-paper focus:px-3 focus:py-2">
        Skip to content
      </a>

      <header className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-5">
        <a href="/" aria-label="Brightside Dental home">
          <Logo />
        </a>
        <nav aria-label="Main" className="flex flex-wrap items-center gap-x-6 gap-y-2 text-ink-soft">
          <a href="#prices" className="hover:text-ink">Prices</a>
          <a href="#visit" className="hover:text-ink">Visit us</a>
          <a href="#contact" className="hover:text-ink">Contact</a>
          <a href={PHONE_HREF} className="font-bold text-ink">{PHONE}</a>
        </nav>
      </header>

      <main id="main">
        <section className="mx-auto max-w-6xl px-5 pt-10 pb-16 sm:pt-16 sm:pb-24">
          <p className="max-w-xl text-lg text-ink-soft">
            Family dentistry on Elm Street, upstairs from the pharmacy. Check-ups, fillings, implants and
            clear aligners, with appointments for nervous patients.
          </p>
          <h1 className="mt-6 max-w-4xl text-5xl leading-[1.02] font-bold sm:text-7xl">
            <span
              aria-hidden="true"
              className={`mr-4 inline-block h-[0.42em] w-[0.42em] translate-y-[-0.08em] rounded-full ${status.open ? "bg-sage" : "bg-ink-soft"}`}
            />
            {status.text}.
          </h1>
          <div className="mt-10 flex flex-wrap gap-3">
            <a href={PHONE_HREF} className="rounded-xl bg-sage px-5 py-3 font-bold text-enamel hover:bg-sage-dark">
              Call {PHONE}
            </a>
            <button
              type="button"
              onClick={() => setChatOpen(true)}
              className="rounded-xl border border-ink px-5 py-3 font-bold hover:bg-paper"
            >
              Ask a question
            </button>
          </div>
          <p className="mt-6 text-sm text-ink-soft">
            Out of hours, call {OUT_OF_HOURS_PHONE}. For trouble breathing or swelling spreading to your eye or
            neck, call 911.
          </p>
        </section>

        <section id="prices" className="border-t border-line bg-paper">
          <div className="mx-auto grid max-w-6xl gap-10 px-5 py-16 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <h2 className="text-3xl font-bold sm:text-4xl">Prices</h2>
              <p className="mt-4 max-w-md text-ink-soft">
                Prices without insurance. A dentist confirms your treatment and its price before any work starts.
              </p>
              <h3 className="mt-8 text-xl font-semibold">Insurance</h3>
              <p className="mt-2 max-w-md text-ink-soft">
                In-network with {INSURERS.slice(0, -1).join(", ")} and {INSURERS.at(-1)}. We can also bill most
                other PPO plans. We don't accept HMO or DMO plans.
              </p>
            </div>
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">Prices for common treatments</caption>
              <thead>
                <tr className="border-b-2 border-ink text-sm text-ink-soft">
                  <th scope="col" className="py-2 font-normal">Treatment</th>
                  <th scope="col" className="py-2 text-right font-normal">Price</th>
                </tr>
              </thead>
              <tbody>
                {PRICES.map((row) => (
                  <tr key={row.service} className="border-b border-line">
                    <th scope="row" className="py-3 pr-4 font-normal">
                      {row.service}
                      {row.note && <span className="block text-sm text-ink-soft">{row.note}</span>}
                    </th>
                    <td className="py-3 text-right font-bold whitespace-nowrap tabular-nums">{row.price}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section id="visit" className="border-t border-line">
          <div className="mx-auto grid max-w-6xl gap-10 px-5 py-16 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <h2 className="text-3xl font-bold sm:text-4xl">Visit us</h2>
              <p className="mt-4 text-lg">{ADDRESS}</p>
              <p className="mt-2 max-w-md text-ink-soft">
                First floor, with a lift and step-free entrance. Free parking behind the building.
              </p>
              <h3 className="mt-8 text-xl font-semibold">New patients</h3>
              <p className="mt-2 max-w-md text-ink-soft">
                Bring photo ID, your insurance card and a list of any medicines you take. If dental visits make
                you anxious, tell us when you book and we'll plan a longer, slower appointment.
              </p>
            </div>
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">Opening hours</caption>
              <tbody>
                {WEEK_ORDER.map((day) => {
                  const hours = HOURS[day];
                  const isToday = day === today;
                  return (
                    <tr key={day} className={`border-b border-line ${isToday ? "bg-blush/60" : ""}`}>
                      <th scope="row" className="py-3 pl-3 font-normal">
                        {DAY_NAMES[day]}
                        {isToday && <span className="ml-2 text-sm font-bold text-sage">Today</span>}
                      </th>
                      <td className="py-3 pr-3 text-right tabular-nums">
                        {hours ? `${formatTime(hours.open)} to ${formatTime(hours.close)}` : "Closed"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section id="contact" className="border-t border-line bg-paper">
          <div className="mx-auto grid max-w-6xl gap-10 px-5 py-16 lg:grid-cols-[1fr_1.4fr]">
            <div>
              <h2 className="text-3xl font-bold sm:text-4xl">Send us a message</h2>
              <p className="mt-4 max-w-md text-ink-soft">
                Use this for bookings, changes and billing questions. For anything urgent, call {PHONE} instead.
              </p>
            </div>
            <ContactForm />
          </div>
        </section>
      </main>

      <footer className="mx-auto max-w-6xl px-5 py-10 text-sm text-ink-soft">
        Brightside Dental is a fictional clinic made for a software demo. Nothing on this site is dental advice.
      </footer>

      {!chatOpen && (
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          className="fixed right-5 bottom-5 z-30 rounded-full bg-ink px-5 py-3.5 font-bold text-enamel shadow-[0_8px_24px_-8px_rgb(29_43_58/0.6)] hover:bg-sage-dark"
        >
          Ask a question
        </button>
      )}
      <ChatWidget open={chatOpen} onOpenChange={setChatOpen} />
    </div>
  );
}
