import type { MessageStatus } from "../api";

export const CATEGORY_LABELS: Record<string, string> = {
  appointment_request: "Appointment request",
  reschedule_or_cancel: "Reschedule or cancel",
  billing_or_insurance: "Billing or insurance",
  clinical_question: "Clinical question",
  complaint: "Complaint",
  urgent: "Urgent",
  general_question: "General question",
  other: "Other",
};

export const STATUS_LABELS: Record<MessageStatus, string> = {
  new: "Sorting",
  needs_review: "Waiting for review",
  triage_failed: "Needs a manual reply",
  sent: "Reply sent",
  rejected: "Closed without reply",
};

export const PRIORITY_STYLES: Record<string, string> = {
  urgent: "bg-alert text-paper",
  high: "bg-amber-soft text-amber",
  normal: "bg-enamel text-ink-soft",
  low: "bg-enamel text-ink-soft",
};
