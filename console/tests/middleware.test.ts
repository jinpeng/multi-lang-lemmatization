import { describe, expect, it } from "vitest";
import { isProtectedPath, redirectTarget } from "@/middleware";

describe("admin route protection", () => {
  it("protects keys, settings and logs", () => {
    for (const p of ["/keys", "/settings", "/logs"]) {
      expect(isProtectedPath(p)).toBe(true);
    }
  });

  it("leaves the playground, languages and login public", () => {
    for (const p of ["/", "/languages", "/login"]) {
      expect(isProtectedPath(p)).toBe(false);
    }
  });

  it("protects nested paths under a protected prefix", () => {
    expect(isProtectedPath("/keys/new")).toBe(true);
  });

  it("does not treat a lookalike prefix as protected", () => {
    expect(isProtectedPath("/keysomething")).toBe(false);
  });

  it("redirect target preserves the original destination", () => {
    expect(redirectTarget("/settings")).toBe("/login?next=%2Fsettings");
  });
});
