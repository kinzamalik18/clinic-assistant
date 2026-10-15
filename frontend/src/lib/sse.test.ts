import { describe, expect, it } from "vitest";

import { SSEParser } from "./sse";

describe("SSEParser", () => {
  it("parses events split across chunks", () => {
    const parser = new SSEParser();
    expect(parser.push('event: delta\ndata: {"te')).toEqual([]);
    expect(parser.push('xt":"Hi"}\n\nevent: done\ndata: {}\n\n')).toEqual([
      { event: "delta", data: { text: "Hi" } },
      { event: "done", data: {} },
    ]);
  });

  it("handles CRLF line endings and skips bad JSON", () => {
    const parser = new SSEParser();
    expect(parser.push("event: a\r\ndata: nope\r\n\r\nevent: b\r\ndata: 1\r\n\r\n")).toEqual([
      { event: "b", data: 1 },
    ]);
  });
});
