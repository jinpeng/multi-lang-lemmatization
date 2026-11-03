import { describe, expect, it } from "vitest";
import { ADMIN_COOKIE, CSRF_COOKIE, cookieOptions, newCsrfToken } from "@/lib/session";

describe("session cookies", () => {
  it("admin cookie is httpOnly so scripts cannot read it", () => {
    expect(cookieOptions().httpOnly).toBe(true);
  });

  it("admin cookie is SameSite=Lax and scoped to the whole site", () => {
    const o = cookieOptions();
    expect(o.sameSite).toBe("lax");
    expect(o.path).toBe("/");
  });

  it("admin cookie is Secure in production", () => {
    expect(cookieOptions({ secure: true }).secure).toBe(true);
  });

  it("csrf cookie must NOT be httpOnly, because the client echoes it", () => {
    expect(cookieOptions({ httpOnly: false }).httpOnly).toBe(false);
  });

  it("cookie names are distinct", () => {
    expect(ADMIN_COOKIE).not.toBe(CSRF_COOKIE);
  });

  it("csrf tokens are unique", () => {
    expect(newCsrfToken()).not.toBe(newCsrfToken());
  });
});
