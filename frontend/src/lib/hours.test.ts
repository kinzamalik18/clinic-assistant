import { describe, expect, it } from "vitest";

import { formatTime, openStatus } from "./hours";

// 2026-10-12 is a Monday.
const at = (day: number, time: string) => new Date(`2026-10-${12 + day}T${time}:00`);

describe("openStatus", () => {
  it("is open during opening hours", () => {
    expect(openStatus(at(0, "10:30"))).toEqual({ open: true, text: "Open today until 6:00 pm" });
  });

  it("says when it opens later today", () => {
    expect(openStatus(at(0, "07:15")).text).toBe("Opens today at 8:00 am");
  });

  it("treats closing time as closed", () => {
    expect(openStatus(at(4, "16:00")).text).toBe("Closed now. Opens tomorrow at 9:00 am");
  });

  it("skips Sunday after Saturday closes", () => {
    expect(openStatus(at(5, "14:00")).text).toBe("Closed now. Opens Monday at 8:00 am");
  });
});

describe("formatTime", () => {
  it("formats noon and midnight", () => {
    expect(formatTime("12:00")).toBe("12:00 pm");
    expect(formatTime("00:30")).toBe("12:30 am");
  });
});
