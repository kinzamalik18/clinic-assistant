import { DAY_NAMES, HOURS } from "../clinic";

function minutes(hhmm: string): number {
  const [h = "0", m = "0"] = hhmm.split(":");
  return Number(h) * 60 + Number(m);
}

export function formatTime(hhmm: string): string {
  const total = minutes(hhmm);
  const h = Math.floor(total / 60);
  const m = total % 60;
  const suffix = h >= 12 ? "pm" : "am";
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export type OpenStatus = { open: boolean; text: string };

/** Describe whether the clinic is open at `now`, using the visitor's local clock. */
export function openStatus(now: Date): OpenStatus {
  const day = now.getDay();
  const current = now.getHours() * 60 + now.getMinutes();
  const today = HOURS[day];

  if (today && current >= minutes(today.open) && current < minutes(today.close)) {
    return { open: true, text: `Open today until ${formatTime(today.close)}` };
  }
  if (today && current < minutes(today.open)) {
    return { open: false, text: `Opens today at ${formatTime(today.open)}` };
  }
  for (let offset = 1; offset <= 7; offset++) {
    const next = (day + offset) % 7;
    const hours = HOURS[next];
    if (hours) {
      const when = offset === 1 ? "tomorrow" : DAY_NAMES[next];
      return { open: false, text: `Closed now. Opens ${when} at ${formatTime(hours.open)}` };
    }
  }
  return { open: false, text: "Closed now" };
}
