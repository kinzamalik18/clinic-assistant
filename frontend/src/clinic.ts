// Facts shown on the website. Keep them in sync with backend/data/clinic, which is what
// the chatbot answers from.

export const PHONE = "(555) 010-2400";
export const PHONE_HREF = "tel:+15550102400";
export const OUT_OF_HOURS_PHONE = "(555) 010-2499";
export const ADDRESS = "14 Elm Street, Riverside";

export type OpeningHours = { open: string; close: string } | null;

// Indexed by Date.getDay(): 0 is Sunday.
export const HOURS: readonly OpeningHours[] = [
  null,
  { open: "08:00", close: "18:00" },
  { open: "08:00", close: "18:00" },
  { open: "08:00", close: "18:00" },
  { open: "08:00", close: "18:00" },
  { open: "08:00", close: "16:00" },
  { open: "09:00", close: "13:00" },
];

export const DAY_NAMES = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
] as const;

export const PRICES: readonly { service: string; price: string; note?: string }[] = [
  { service: "New patient examination", price: "$120", note: "About 45 minutes" },
  { service: "Check-up", price: "$75" },
  { service: "Cleaning with a hygienist", price: "$95" },
  { service: "Check-up and cleaning", price: "$150" },
  { service: "Children's check-up (under 16)", price: "$45" },
  { service: "Tooth-coloured filling", price: "from $140" },
  { service: "Simple extraction", price: "$150" },
  { service: "In-clinic whitening", price: "$380" },
  { service: "Single implant with crown", price: "from $3,200" },
  { service: "Urgent appointment", price: "$95", note: "Plus any treatment" },
];

export const INSURERS = ["Delta Dental PPO", "Cigna Dental PPO", "MetLife PDP", "Aetna Dental PPO"];
