import { describe, expect, it } from "vitest";
import { codePointToUtf16 } from "@/lib/offsets";

describe("codePointToUtf16", () => {
  it("is identity for pure BMP text", () => {
    const t = "東京へ行く";
    for (let i = 0; i <= t.length; i++) expect(codePointToUtf16(t, i)).toBe(i);
  });

  it("accounts for a surrogate pair before the offset", () => {
    const t = "𝕏東京"; // 𝕏 is U+1D54F, 2 UTF-16 units
    expect(t.length).toBe(4); // what JS indexes
    expect([...t].length).toBe(3); // what Python counts
    expect(codePointToUtf16(t, 0)).toBe(0);
    expect(codePointToUtf16(t, 1)).toBe(2);
    expect(codePointToUtf16(t, 2)).toBe(3);
    expect(codePointToUtf16(t, 3)).toBe(4);
  });

  it("lets you slice the right substring back out", () => {
    const t = "𝕏東京";
    const start = codePointToUtf16(t, 1);
    const end = codePointToUtf16(t, 3);
    expect(t.slice(start, end)).toBe("東京");
  });

  it("handles emoji", () => {
    const t = "a😂b";
    expect(codePointToUtf16(t, 2)).toBe(3);
    expect(t.slice(codePointToUtf16(t, 1), codePointToUtf16(t, 2))).toBe("😂");
  });

  it("clamps past the end", () => {
    expect(codePointToUtf16("abc", 99)).toBe(3);
  });
});
