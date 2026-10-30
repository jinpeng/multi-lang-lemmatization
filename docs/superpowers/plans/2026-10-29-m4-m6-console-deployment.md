# M4+M6 Console and Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js web console — Playground demo, language capability matrix, API key management, settings/diagnostics, audit log — plus Docker images and a one-command compose stack.

**Architecture:** Next.js App Router as a Backend-for-Frontend. The browser only ever talks to Next.js. Server Components and Route Handlers hold `LEMMA_SERVICE_TOKEN` and the admin token; the admin token lives in an httpOnly cookie, the service token never leaves the server. The Playground calls the Python API with a server-injected demo key, so no credential reaches the browser — and at the same time shows the equivalent `curl`, so the demo still teaches the real API.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4, Vitest, Playwright. Docker + docker-compose.

**Spec:** `docs/superpowers/specs/2026-10-29-multilingual-lemmatization-design.md` §8, §9
**Depends on:** Plan 1 (backends) and Plan 2 (auth, admin routes, settings).

---

## Verification already performed

The console's pure-logic modules (env validation, API client, curl builder, CSRF helper) were extracted into a scratch project and **executed** with Vitest before this plan was published:

| Verified | Result |
|---|---|
| Tasks 2, 4, 6 test suites | **16 passed** |
| `NEXT_PUBLIC_` leak guard | mutation-tested: removing it fails the suite |
| Missing `Authorization` header | mutation-tested: removing it fails the suite |
| Credential mixing (Bearer on admin calls) | mutation-tested: adding it fails the suite |
| Service-token leak into a thrown error | **initially not caught** — see below |

**Defect found by mutation testing and fixed here:** the original "does not leak the service token" test called `client.lemmatize()`, which sends only the bearer credential — the service token is never in that request. The assertion therefore could not fail, and a mutation that attached the full `RequestInit` (including `X-Service-Token`) to every thrown `ApiError` passed all tests. Rewritten to assert against an admin method, which is the only path that carries the token, plus a second test asserting the bearer secret never appears. Both now fail under the mutation.

**Second defect found and fixed:** the `docker-compose.yml` as originally drafted was **invalid YAML**. Its `${VAR:?generate with: python -c "..."}` fail-fast messages contained `: `, which terminates an unquoted YAML scalar, so `docker compose config` would have failed before starting anything. Messages rewritten without a colon. The file now parses, and its security properties were asserted: `api` has no host `ports` (only `expose`), `LEMMA_AUTH_ENABLED=1`, `LEMMA_REQUIRE_AUTH=1`, and `console` waits on `service_healthy`.

> `JSON.stringify(new Error(...))` includes only own enumerable properties (`code`, `status`, `details`, `name`) — not `message`. Tests that assert on a thrown error must concatenate `.message` explicitly or they will silently miss it.

**Not verified here:** Tasks 7–14 (pages, Server Actions, Docker, Playwright) need a full Next.js build and a running stack. Task 14 states explicitly that the E2E suite must not be claimed as passing unless it was actually run.
---

## Scope note

| Plan | Covers | Status |
|---|---|---|
| Plan 1 | M1+M2 — 7 backends, three `/v1/*` endpoints | verified, 108 tests |
| Plan 2 | M3+M5 — Key/Secret, HMAC, SQLite, settings, audit | written, crypto verified by mutation |
| **This plan** | M4+M6 — console, BFF, Playground, Docker, ops docs | being written now |

---

## Security invariants this plan must not break

Restating them because every task below is judged against this list:

1. **No secret reaches the browser.** Not the API secret, not the service token, not the admin token (it is httpOnly), not `LEMMA_MASTER_KEY`.
2. **`LEMMA_SERVICE_TOKEN` is server-only.** Never prefixed `NEXT_PUBLIC_`, never in a Client Component, never serialized into props.
3. **The console never becomes a credential oracle.** Creating a key returns its secret to the operator exactly once; the browser shows it, then it must be gone from server memory and from the DOM on navigation.
4. **CSRF on every mutating request.** Cookies are `SameSite=Lax` plus a double-submit token, because `Lax` alone does not stop top-level form POSTs.
5. **Diagnostics is read-only.** Plan 2 makes the API enforce this; the UI must not imply otherwise.

---

## File structure

| File | Responsibility |
|---|---|
| `console/package.json` | deps, scripts |
| `console/next.config.ts` | server-only env sanity check at boot |
| `console/src/lib/env.ts` | reads and validates server env, fails fast |
| `console/src/lib/api.ts` | typed fetch wrapper for the Python API |
| `console/src/lib/session.ts` | admin cookie read/write/clear, CSRF token |
| `console/src/lib/types.ts` | shared response types |
| `console/src/app/layout.tsx` | shell, nav |
| `console/src/app/page.tsx` | Playground (Server Component + form) |
| `console/src/app/actions/lemmatize.ts` | Server Action calling the API with the demo key |
| `console/src/app/languages/page.tsx` | capability matrix |
| `console/src/app/login/page.tsx` | passphrase form |
| `console/src/app/actions/session.ts` | Server Action: login, logout |
| `console/src/app/keys/page.tsx` | key list |
| `console/src/app/keys/actions.ts` | create/rotate/revoke Server Actions |
| `console/src/app/keys/NewKeySecret.tsx` | one-time secret display |
| `console/src/app/settings/page.tsx` | diagnostics (read-only) + settings (editable) |
| `console/src/app/settings/actions.ts` | patch setting |
| `console/src/app/logs/page.tsx` | audit + recent requests |
| `console/src/components/*` | Badge, Table, Card, CopyButton |
| `console/src/middleware.ts` | redirect unauthenticated admin routes to /login |
| `console/tests/*.test.ts` | Vitest unit tests |
| `console/e2e/*.spec.ts` | Playwright |
| `deploy/api.Dockerfile` | Python image |
| `deploy/console.Dockerfile` | Next.js standalone image |
| `deploy/docker-compose.yml` | both services, volume, env |
| `deploy/README.md` | ops runbook |

---

## Task 1: Console scaffold

**Files:**
- Create: `console/` (via create-next-app)
- Modify: `console/package.json`

- [ ] **Step 1: Scaffold**

Run:
```bash
cd console 2>/dev/null || cd .
npx create-next-app@latest console --typescript --tailwind --app --src-dir --no-eslint --no-turbopack --use-npm --yes
cd console
npm pkg set scripts.test="vitest run"
npm pkg set scripts.e2e="playwright test"
npm i -D vitest @vitejs/plugin-react jsdom @testing-library/react @testing-library/jest-dom @playwright/test
```

Expected: `console/` exists with `src/app/`, `next.config.ts`.

- [ ] **Step 2: Verify the scaffold builds**

Run: `cd console && npm run build`
Expected: build succeeds. If it fails, resolve before continuing — every later task assumes a working build.

- [ ] **Step 3: Add Vitest config**

```typescript
// console/vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
});
```

```typescript
// console/tests/setup.ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: Commit**

```bash
git add console/
git commit -m "chore: scaffold Next.js console with Vitest"
```

---

## Task 2: Server env validation

**Files:**
- Create: `console/src/lib/env.ts`
- Test: `console/tests/env.test.ts`

Failing fast at boot is the point: a console that starts without `LEMMA_SERVICE_TOKEN` will fail every admin call at runtime, which looks like a permissions bug rather than a config bug.

- [ ] **Step 1: Write the failing test**

```typescript
// console/tests/env.test.ts
import { describe, expect, it } from "vitest";
import { readEnv } from "@/lib/env";

const good = {
  LEMMA_API_URL: "http://api:8000",
  LEMMA_SERVICE_TOKEN: "svc",
  LEMMA_DEMO_KEY: "lk_x.ls_y",
};

describe("readEnv", () => {
  it("accepts a complete environment", () => {
    const env = readEnv(good);
    expect(env.apiUrl).toBe("http://api:8000");
    expect(env.serviceToken).toBe("svc");
    expect(env.demoKey).toBe("lk_x.ls_y");
  });

  it("rejects a missing service token", () => {
    const { LEMMA_SERVICE_TOKEN, ...rest } = good;
    expect(() => readEnv(rest)).toThrow(/LEMMA_SERVICE_TOKEN/);
  });

  it("rejects a missing api url", () => {
    const { LEMMA_API_URL, ...rest } = good;
    expect(() => readEnv(rest)).toThrow(/LEMMA_API_URL/);
  });

  it("rejects a non-http api url", () => {
    expect(() => readEnv({ ...good, LEMMA_API_URL: "ftp://api" })).toThrow(/http/);
  });

  it("rejects a NEXT_PUBLIC_-prefixed service token", () => {
    expect(() =>
      readEnv({ ...good, NEXT_PUBLIC_LEMMA_SERVICE_TOKEN: "leaked" }),
    ).toThrow(/NEXT_PUBLIC_/);
  });

  it("allows the demo key to be absent", () => {
    const { LEMMA_DEMO_KEY, ...rest } = good;
    expect(readEnv(rest).demoKey).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd console && npx vitest run tests/env.test.ts`
Expected: FAIL — cannot resolve `@/lib/env`.

- [ ] **Step 3: Write `console/src/lib/env.ts`**

```typescript
/**
 * Server-only environment. Imported exclusively from Server Components,
 * Route Handlers and Server Actions.
 *
 * Anything secret must be a plain env var, never NEXT_PUBLIC_*: Next.js inlines
 * NEXT_PUBLIC_* into the client bundle at build time, which would ship the
 * service token to every browser.
 */

export type ServerEnv = {
  apiUrl: string;
  serviceToken: string;
  demoKey?: string;
};

export function readEnv(source: Record<string, string | undefined>): ServerEnv {
  const leaked = Object.keys(source).filter((k) => k.startsWith("NEXT_PUBLIC_"));
  if (leaked.length > 0) {
    throw new Error(
      `NEXT_PUBLIC_ variables are client-visible and must not be used for secrets: ${leaked.join(", ")}`,
    );
  }

  const apiUrl = source.LEMMA_API_URL;
  if (!apiUrl) throw new Error("LEMMA_API_URL is required");
  if (!/^https?:\/\//.test(apiUrl)) {
    throw new Error(`LEMMA_API_URL must be an http(s) URL, got ${apiUrl}`);
  }

  const serviceToken = source.LEMMA_SERVICE_TOKEN;
  if (!serviceToken) throw new Error("LEMMA_SERVICE_TOKEN is required");

  return { apiUrl: apiUrl.replace(/\/$/, ""), serviceToken, demoKey: source.LEMMA_DEMO_KEY };
}

let cached: ServerEnv | undefined;

export function env(): ServerEnv {
  cached ??= readEnv(process.env);
  return cached;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd console && npx vitest run tests/env.test.ts`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add console/src/lib/env.ts console/tests/env.test.ts
git commit -m "feat: add fail-fast server env validation"
```

---

## Task 3: Session and CSRF

**Files:**
- Create: `console/src/lib/session.ts`
- Test: `console/tests/session.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// console/tests/session.test.ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd console && npx vitest run tests/session.test.ts`
Expected: FAIL — cannot resolve `@/lib/session`.

- [ ] **Step 3: Write `console/src/lib/session.ts`**

```typescript
import { cookies } from "next/headers";
import { randomBytes } from "node:crypto";

export const ADMIN_COOKIE = "lemma_admin";
export const CSRF_COOKIE = "lemma_csrf";

export type CookieOptions = {
  httpOnly: boolean;
  sameSite: "lax" | "strict" | "none";
  secure: boolean;
  path: string;
  maxAge: number;
};

export function cookieOptions(
  overrides: Partial<CookieOptions> = {},
): CookieOptions {
  return {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 60 * 60 * 2,
    ...overrides,
  };
}

export function newCsrfToken(): string {
  return randomBytes(32).toString("base64url");
}

export async function getAdminToken(): Promise<string | undefined> {
  return (await cookies()).get(ADMIN_COOKIE)?.value;
}

export async function setSession(adminToken: string): Promise<void> {
  const jar = await cookies();
  jar.set(ADMIN_COOKIE, adminToken, cookieOptions());
  // Readable by the client on purpose: the double-submit pattern requires the
  // browser to echo this value in a header while the cookie proves it came
  // from us. A non-httpOnly CSRF token is safe; a non-httpOnly admin token is not.
  jar.set(CSRF_COOKIE, newCsrfToken(), cookieOptions({ httpOnly: false }));
}

export async function clearSession(): Promise<void> {
  const jar = await cookies();
  jar.delete(ADMIN_COOKIE);
  jar.delete(CSRF_COOKIE);
}

export async function assertCsrf(formToken: string | undefined): Promise<void> {
  const expected = (await cookies()).get(CSRF_COOKIE)?.value;
  if (!expected || !formToken || expected !== formToken) {
    throw new Error("CSRF token mismatch");
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd console && npx vitest run tests/session.test.ts`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add console/src/lib/session.ts console/tests/session.test.ts
git commit -m "feat: add admin session cookies and CSRF token helpers"
```

---

## Task 4: Typed API client

**Files:**
- Create: `console/src/lib/types.ts`
- Create: `console/src/lib/api.ts`
- Test: `console/tests/api.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// console/tests/api.test.ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "@/lib/api";

const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

const client = new ApiClient({ apiUrl: "http://api:8000", serviceToken: "svc" });

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

describe("ApiClient", () => {
  it("lemmatize sends the demo key as a bearer credential", async () => {
    fetchMock.mockReturnValue(json({ items: [] }));
    await client.lemmatize("lk_a.ls_b", { lang: "de", tokens: ["x"] });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api:8000/v1/lemmatize");
    expect(init.headers.Authorization).toBe("Bearer lk_a.ls_b");
  });

  it("admin calls send service and admin tokens, never the demo key", async () => {
    fetchMock.mockReturnValue(json({ keys: [] }));
    await client.listKeys("admin-token");
    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["X-Service-Token"]).toBe("svc");
    expect(init.headers["X-Admin-Token"]).toBe("admin-token");
    expect(init.headers.Authorization).toBeUndefined();
  });

  it("turns an API error envelope into a thrown ApiError", async () => {
    fetchMock.mockReturnValue(
      json({ error: { code: "LANG_FORBIDDEN", message: "nope", details: {} } }, 403),
    );
    await expect(client.lemmatize("k", { lang: "x", tokens: ["y"] })).rejects.toMatchObject({
      code: "LANG_FORBIDDEN",
      status: 403,
    });
  });

  it("does not leak the service token into a thrown error from an admin call", async () => {
    // Must use an ADMIN method: only those carry X-Service-Token, so only those
    // can leak it. Asserting against lemmatize() would pass vacuously.
    fetchMock.mockReturnValue(json({ error: { code: "X", message: "m", details: {} } }, 500));
    let caught: unknown;
    try {
      await client.listKeys("admin-token");
    } catch (error) {
      caught = error;
    }
    const serialized = JSON.stringify(caught) + String((caught as Error)?.message ?? "");
    expect(serialized).not.toContain("svc");
    expect(serialized).not.toContain("admin-token");
  });

  it("does not leak the bearer secret into a thrown error", async () => {
    fetchMock.mockReturnValue(json({ error: { code: "X", message: "m", details: {} } }, 500));
    let caught: unknown;
    try {
      await client.lemmatize("lk_secretkey.ls_supersecret", { lang: "x", tokens: ["y"] });
    } catch (error) {
      caught = error;
    }
    expect(JSON.stringify(caught)).not.toContain("ls_supersecret");
  });

  it("loginPosts the passphrase without auth headers", async () => {
    fetchMock.mockReturnValue(json({ admin_token: "t", expires_at: 1 }));
    await client.login("pw");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ passphrase: "pw" });
    expect(init.headers["X-Service-Token"]).toBe("svc");
    expect(init.headers["X-Admin-Token"]).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd console && npx vitest run tests/api.test.ts`
Expected: FAIL — cannot resolve `@/lib/api`.

- [ ] **Step 3: Write `console/src/lib/types.ts` and `console/src/lib/api.ts`**

`console/src/lib/types.ts`:
```typescript
export type Capabilities = {
  pos: boolean;
  pos_accepted: boolean;
  pos_required: boolean;
  candidates: boolean;
  reading: boolean;
  mwt: boolean;
  tokenizes: boolean;
};

export type LanguageEntry = {
  lang: string;
  status: "ok" | "unavailable";
  backend: { name: string; version: string } | null;
  reason: string | null;
  pos_scheme: string | null;
  capabilities: Capabilities;
  options: Record<string, { type: string; default: unknown; values?: string[] }>;
};

export type LemmaItem = {
  surface: string;
  lemma: string;
  pos: string | null;
  prov: string;
  reading?: string;
  candidates?: string[];
};

export type LemmatizeResponse = {
  request_id: string;
  lang: string;
  backend: { name: string; version: string };
  segmented_by: "input" | "backend";
  capabilities: Capabilities;
  items: LemmaItem[];
  warnings: { code: string; surface: string }[];
  elapsed_ms: number;
};

export type KeyRecord = {
  key_id: string;
  name: string;
  secret_fingerprint: string;
  scopes: string[];
  langs: string[];
  allow_hmac: boolean;
  rate_limit_rpm: number;
  created_at: string;
  created_by: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

export type CreatedKey = {
  key_id: string;
  secret: string;
  secret_fingerprint: string;
  name?: string;
};

export type SettingRow = {
  key: string;
  value: unknown;
  default: unknown;
  kind: string;
  hot: boolean;
  min: number | null;
  max: number | null;
  values: string[];
  overridden: boolean;
};

export type AuditEntry = {
  id: number;
  at: string;
  actor: string;
  action: string;
  target: string;
  before_json: string | null;
  after_json: string | null;
};
```

`console/src/lib/api.ts`:
```typescript
import type {
  AuditEntry, CreatedKey, KeyRecord, LanguageEntry, LemmatizeResponse, SettingRow,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    readonly code: string,
    readonly status: number,
    message: string,
    readonly details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export type ClientConfig = { apiUrl: string; serviceToken: string };

export class ApiClient {
  constructor(private readonly config: ClientConfig) {}

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const response = await fetch(`${this.config.apiUrl}${path}`, init);
    const text = await response.text();
    const body = text ? JSON.parse(text) : {};
    if (!response.ok) {
      const envelope = body.error ?? {};
      // Deliberately does not include `init`: the headers carry the service token.
      throw new ApiError(
        envelope.code ?? "INTERNAL",
        response.status,
        envelope.message ?? "request failed",
        envelope.details ?? {},
      );
    }
    return body as T;
  }

  lemmatize(
    bearer: string,
    payload: { lang: string; text?: string; tokens?: string[]; pos?: unknown; options?: unknown },
  ): Promise<LemmatizeResponse> {
    return this.request("/v1/lemmatize", {
      method: "POST",
      headers: { "content-type": "application/json", Authorization: `Bearer ${bearer}` },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
  }

  async languages(): Promise<LanguageEntry[]> {
    const body = await this.request<{ languages: LanguageEntry[] }>("/v1/languages", {
      cache: "no-store",
    });
    return body.languages;
  }

  async health(): Promise<{ status: string; backends: Record<string, unknown> }> {
    return this.request("/v1/health", { cache: "no-store" });
  }

  private adminHeaders(adminToken: string): Record<string, string> {
    return {
      "content-type": "application/json",
      "X-Service-Token": this.config.serviceToken,
      "X-Admin-Token": adminToken,
    };
  }

  async login(passphrase: string): Promise<{ admin_token: string; expires_at: number }> {
    return this.request("/admin/session", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "X-Service-Token": this.config.serviceToken,
      },
      body: JSON.stringify({ passphrase }),
    });
  }

  async listKeys(adminToken: string): Promise<KeyRecord[]> {
    const body = await this.request<{ keys: KeyRecord[] }>("/admin/keys", {
      headers: this.adminHeaders(adminToken),
      cache: "no-store",
    });
    return body.keys;
  }

  createKey(adminToken: string, payload: Record<string, unknown>): Promise<CreatedKey> {
    return this.request("/admin/keys", {
      method: "POST",
      headers: this.adminHeaders(adminToken),
      body: JSON.stringify(payload),
    });
  }

  rotateKey(adminToken: string, keyId: string): Promise<CreatedKey> {
    return this.request(`/admin/keys/${encodeURIComponent(keyId)}/rotate`, {
      method: "POST",
      headers: this.adminHeaders(adminToken),
    });
  }

  async revokeKey(adminToken: string, keyId: string): Promise<void> {
    await this.request(`/admin/keys/${encodeURIComponent(keyId)}`, {
      method: "DELETE",
      headers: this.adminHeaders(adminToken),
    });
  }

  async readSettings(adminToken: string): Promise<SettingRow[]> {
    const body = await this.request<{ settings: SettingRow[] }>("/admin/settings", {
      headers: this.adminHeaders(adminToken),
      cache: "no-store",
    });
    return body.settings;
  }

  patchSetting(adminToken: string, key: string, value: unknown): Promise<unknown> {
    return this.request("/admin/settings", {
      method: "PATCH",
      headers: this.adminHeaders(adminToken),
      body: JSON.stringify({ key, value }),
    });
  }

  async readAudit(adminToken: string, limit = 50, offset = 0): Promise<AuditEntry[]> {
    const body = await this.request<{ entries: AuditEntry[] }>(
      `/admin/audit?limit=${limit}&offset=${offset}`,
      { headers: this.adminHeaders(adminToken), cache: "no-store" },
    );
    return body.entries;
  }

  diagnostics(adminToken: string): Promise<Record<string, unknown>> {
    return this.request("/admin/diagnostics", {
      headers: this.adminHeaders(adminToken),
      cache: "no-store",
    });
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd console && npx vitest run tests/api.test.ts`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add console/src/lib/types.ts console/src/lib/api.ts console/tests/api.test.ts
git commit -m "feat: add typed API client with service-token isolation"
```

---

## Task 5: API client factory and middleware

**Files:**
- Create: `console/src/lib/server.ts`
- Create: `console/src/middleware.ts`
- Test: `console/tests/middleware.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// console/tests/middleware.test.ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd console && npx vitest run tests/middleware.test.ts`
Expected: FAIL — cannot resolve `@/middleware`.

- [ ] **Step 3: Write the two modules**

`console/src/lib/server.ts`:
```typescript
import "server-only";
import { ApiClient } from "@/lib/api";
import { env } from "@/lib/env";

/** Server-only singleton. The `server-only` import makes a client import a build error. */
export function api(): ApiClient {
  const e = env();
  return new ApiClient({ apiUrl: e.apiUrl, serviceToken: e.serviceToken });
}

export function demoKey(): string | undefined {
  return env().demoKey;
}
```

`console/src/middleware.ts`:
```typescript
import { NextResponse, type NextRequest } from "next/server";

const PROTECTED = ["/keys", "/settings", "/logs"];
export const ADMIN_COOKIE = "lemma_admin";

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function redirectTarget(pathname: string): string {
  return `/login?next=${encodeURIComponent(pathname)}`;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!isProtectedPath(pathname)) return NextResponse.next();

  if (!request.cookies.get(ADMIN_COOKIE)?.value) {
    return NextResponse.redirect(new URL(redirectTarget(pathname), request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/keys/:path*", "/settings/:path*", "/logs/:path*"] };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd console && npx vitest run tests/middleware.test.ts`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add console/src/lib/server.ts console/src/middleware.ts console/tests/middleware.test.ts
git commit -m "feat: add server-only API factory and admin route middleware"
```

---

## Task 6: Playground

**Files:**
- Create: `console/src/app/actions/lemmatize.ts`
- Create: `console/src/app/page.tsx`
- Create: `console/src/components/*`
- Test: `console/tests/curl.test.ts`

The Playground has two obligations that pull in opposite directions: it must be a *demo* (no credential in the browser) and it must *teach the real API* (so the user can leave and call it themselves). Server-side demo key + rendered `curl` satisfies both.

- [ ] **Step 1: Write the failing test**

```typescript
// console/tests/curl.test.ts
import { describe, expect, it } from "vitest";
import { buildCurl } from "@/lib/curl";

describe("buildCurl", () => {
  it("renders a copy-pasteable curl for a tokens request", () => {
    const out = buildCurl("https://lemma.example.com", { lang: "de", tokens: ["Häuser"] });
    expect(out).toContain("curl -s https://lemma.example.com/v1/lemmatize");
    expect(out).toContain("-H 'Authorization: Bearer $LEMMA_API_KEY'");
    expect(out).toContain(`-d '{"lang":"de","tokens":["Häuser"]}'`);
  });

  it("never embeds a literal secret", () => {
    const out = buildCurl("https://x", { lang: "de", tokens: ["a"] });
    expect(out).not.toMatch(/ls_[A-Za-z0-9]/);
  });

  it("preserves non-ascii payloads", () => {
    const out = buildCurl("https://x", { lang: "ja", text: "食べました" });
    expect(out).toContain("食べました");
  });

  it("includes pos when supplied", () => {
    const out = buildCurl("https://x", { lang: "en", tokens: ["left"], pos: ["VERB"] });
    expect(out).toContain('"pos":["VERB"]');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd console && npx vitest run tests/curl.test.ts`
Expected: FAIL — cannot resolve `@/lib/curl`.

- [ ] **Step 3: Write `console/src/lib/curl.ts`**

```typescript
export type CurlPayload = {
  lang: string;
  text?: string;
  tokens?: string[];
  pos?: string[];
};

export function buildCurl(baseUrl: string, payload: CurlPayload): string {
  const body = JSON.stringify(payload);
  return [
    `curl -s ${baseUrl.replace(/\/$/, "")}/v1/lemmatize`,
    "  -H 'content-type: application/json'",
    "  -H 'Authorization: Bearer $LEMMA_API_KEY'",
    `  -d '${body}'`,
  ].join(" \\\n");
}
```

- [ ] **Step 4: Write the Playground page and Server Action**

`console/src/app/actions/lemmatize.ts`:
```typescript
"use server";

import { api, demoKey } from "@/lib/server";
import { ApiError } from "@/lib/api";
import type { LemmatizeResponse } from "@/lib/types";

export type PlaygroundState =
  | { kind: "idle" }
  | { kind: "ok"; response: LemmatizeResponse; curl: string }
  | { kind: "error"; message: string; code: string };

export async function runLemmatize(
  _prev: PlaygroundState,
  formData: FormData,
): Promise<PlaygroundState> {
  const lang = String(formData.get("lang") ?? "");
  const text = String(formData.get("text") ?? "").trim();
  const posRaw = String(formData.get("pos") ?? "").trim();

  if (!lang || !text) {
    return { kind: "error", code: "INVALID_REQUEST", message: "Choose a language and enter text." };
  }

  const key = demoKey();
  if (!key) {
    return {
      kind: "error",
      code: "NO_DEMO_KEY",
      message: "LEMMA_DEMO_KEY is not configured on the server.",
    };
  }

  // Two modes so the demo can show both halves of the contract:
  // a single word exercises dictionary lookup, a sentence exercises segmentation.
  const isSingleWord = !/\s/.test(text);
  const payload = {
    lang,
    ...(isSingleWord ? { tokens: [text] } : { text }),
    ...(isSingleWord && posRaw ? { pos: [posRaw] } : {}),
  };

  try {
    const response = await api().lemmatize(key, payload);
    const { buildCurl } = await import("@/lib/curl");
    const publicBase = process.env.LEMMA_PUBLIC_API_URL ?? "https://your-host";
    return { kind: "ok", response, curl: buildCurl(publicBase, payload) };
  } catch (error) {
    if (error instanceof ApiError) {
      return { kind: "error", code: error.code, message: error.message };
    }
    return { kind: "error", code: "INTERNAL", message: "Unexpected error contacting the API." };
  }
}
```

`console/src/app/page.tsx`:
```tsx
import { api } from "@/lib/server";
import { Playground } from "@/components/Playground";
import type { LanguageEntry } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let languages: LanguageEntry[] = [];
  let loadError: string | undefined;
  try {
    languages = await api().languages();
  } catch {
    loadError = "The API is unreachable. Check that the api service is running.";
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Lemmatization Playground</h1>
      <p className="mt-2 text-sm text-slate-600">
        Runs against the live API with a server-side demo key, so nothing is exposed to your
        browser. The equivalent <code>curl</code> is shown with each result.
      </p>
      {loadError ? (
        <div className="mt-6 rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
          {loadError}
        </div>
      ) : (
        <Playground languages={languages} />
      )}
    </main>
  );
}
```

- [ ] **Step 5: Write `console/src/components/Playground.tsx`**

```tsx
"use client";

import { useActionState } from "react";
import { runLemmatize, type PlaygroundState } from "@/app/actions/lemmatize";
import type { LanguageEntry } from "@/lib/types";
import { ResultTable } from "@/components/ResultTable";
import { CopyButton } from "@/components/CopyButton";

const initial: PlaygroundState = { kind: "idle" };

export function Playground({ languages }: { languages: LanguageEntry[] }) {
  const [state, action, pending] = useActionState(runLemmatize, initial);

  return (
    <div className="mt-6 space-y-6">
      <form action={action} className="space-y-4 rounded-xl border border-slate-200 p-5">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="text-sm">
            <span className="block font-medium text-slate-700">Language</span>
            <select name="lang" defaultValue="de" className="mt-1 w-full rounded-md border border-slate-300 p-2">
              {languages.map((l) => (
                <option key={l.lang} value={l.lang} disabled={l.status !== "ok"}>
                  {l.lang} — {l.backend?.name ?? "unavailable"}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm sm:col-span-2">
            <span className="block font-medium text-slate-700">
              Text <span className="font-normal text-slate-500">(one word or a sentence)</span>
            </span>
            <input
              name="text"
              defaultValue="Häuser"
              className="mt-1 w-full rounded-md border border-slate-300 p-2"
            />
          </label>
        </div>
        <label className="block text-sm">
          <span className="block font-medium text-slate-700">
            POS <span className="font-normal text-slate-500">(optional, single word only)</span>
          </span>
          <input
            name="pos"
            placeholder="VERB"
            className="mt-1 w-full rounded-md border border-slate-300 p-2 sm:w-48"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "Lemmatizing…" : "Lemmatize"}
        </button>
      </form>

      {state.kind === "error" && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm">
          <div className="font-mono text-xs text-rose-700">{state.code}</div>
          <div className="mt-1 text-rose-900">{state.message}</div>
        </div>
      )}

      {state.kind === "ok" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
            <span className="rounded bg-slate-100 px-2 py-1 font-mono">
              {state.response.backend.name} {state.response.backend.version}
            </span>
            <span className="rounded bg-slate-100 px-2 py-1 font-mono">
              segmented_by: {state.response.segmented_by}
            </span>
            <span>{state.response.elapsed_ms} ms</span>
            <span className="font-mono">{state.response.request_id}</span>
          </div>
          <ResultTable response={state.response} />
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-slate-700">Equivalent request</h2>
              <CopyButton text={state.curl} />
            </div>
            <pre className="mt-2 overflow-x-auto text-xs leading-relaxed text-slate-800">
              {state.curl}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Write the three small components**

`console/src/components/ResultTable.tsx`:
```tsx
import type { LemmatizeResponse } from "@/lib/types";

export function ResultTable({ response }: { response: LemmatizeResponse }) {
  const hasReading = response.capabilities.reading;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Surface</th>
            <th className="px-4 py-2">Lemma</th>
            <th className="px-4 py-2">POS</th>
            {hasReading && <th className="px-4 py-2">Reading</th>}
            <th className="px-4 py-2">Prov</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {response.items.map((item, i) => (
            <tr key={`${item.surface}-${i}`} className={item.prov === "identity" ? "bg-amber-50/50" : ""}>
              <td className="px-4 py-2 font-mono">{item.surface}</td>
              <td className="px-4 py-2 font-mono font-medium">{item.lemma}</td>
              <td className="px-4 py-2 text-slate-600">
                {item.pos ?? <span className="text-slate-400">null</span>}
              </td>
              {hasReading && <td className="px-4 py-2 text-slate-600">{item.reading ?? "—"}</td>}
              <td className="px-4 py-2">
                <span
                  className={
                    item.prov === "identity"
                      ? "rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800"
                      : "rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800"
                  }
                >
                  {item.prov}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

`console/src/components/CopyButton.tsx`:
```tsx
"use client";

import { useState } from "react";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-700"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
```

`console/src/components/Badge.tsx`:
```tsx
export function Badge({ tone, children }: { tone: "ok" | "warn" | "muted"; children: React.ReactNode }) {
  const tones = {
    ok: "bg-emerald-100 text-emerald-800",
    warn: "bg-amber-100 text-amber-800",
    muted: "bg-slate-100 text-slate-600",
  } as const;
  return <span className={`rounded px-2 py-0.5 text-xs ${tones[tone]}`}>{children}</span>;
}
```

- [ ] **Step 7: Run tests and build**

Run: `cd console && npx vitest run tests/curl.test.ts && npm run build`
Expected: 4 passed, build succeeds.

- [ ] **Step 8: Commit**

```bash
git add console/src/app console/src/components console/src/lib/curl.ts console/tests/curl.test.ts
git commit -m "feat: add Playground with server-side demo key and rendered curl"
```

---

## Task 7: Languages capability matrix

**Files:**
- Create: `console/src/app/languages/page.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { api } from "@/lib/server";
import { Badge } from "@/components/Badge";
import type { LanguageEntry } from "@/lib/types";

export const dynamic = "force-dynamic";

function Flag({ on }: { on: boolean }) {
  return on ? <span className="text-emerald-600">●</span> : <span className="text-slate-300">○</span>;
}

export default async function LanguagesPage() {
  const languages: LanguageEntry[] = await api().languages();

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Language capabilities</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">
        <strong>pos</strong> means the backend emits a tag. <strong>pos_accepted</strong> means it
        uses one you send. English accepts a tag but emits none; Russian emits one but ignores
        yours. Modelling these as one flag would hide that difference.
      </p>

      <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Lang</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Backend</th>
              <th className="px-4 py-2">POS scheme</th>
              <th className="px-4 py-2">pos</th>
              <th className="px-4 py-2">pos_accepted</th>
              <th className="px-4 py-2">reading</th>
              <th className="px-4 py-2">tokenizes</th>
              <th className="px-4 py-2">Options</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {languages.map((l) => (
              <tr key={l.lang} className={l.status !== "ok" ? "bg-rose-50/40" : ""}>
                <td className="px-4 py-2 font-mono font-medium">{l.lang}</td>
                <td className="px-4 py-2">
                  <Badge tone={l.status === "ok" ? "ok" : "warn"}>{l.status}</Badge>
                </td>
                <td className="px-4 py-2 text-slate-600">
                  {l.backend ? `${l.backend.name} ${l.backend.version}` : "—"}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-slate-600">
                  {l.pos_scheme ?? "—"}
                </td>
                <td className="px-4 py-2"><Flag on={l.capabilities.pos} /></td>
                <td className="px-4 py-2"><Flag on={l.capabilities.pos_accepted} /></td>
                <td className="px-4 py-2"><Flag on={l.capabilities.reading} /></td>
                <td className="px-4 py-2"><Flag on={l.capabilities.tokenizes} /></td>
                <td className="px-4 py-2 text-xs text-slate-600">
                  {Object.keys(l.options).length === 0
                    ? "—"
                    : Object.entries(l.options)
                        .map(([k, v]) => `${k}=${String(v.default)}`)
                        .join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {languages.some((l) => l.status !== "ok") && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          Some backends failed to initialise. Requests for those languages return{" "}
          <code>503 LANGUAGE_UNAVAILABLE</code> with the reason recorded in{" "}
          <a className="underline" href="/settings">Settings → Diagnostics</a>.
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd console && npm run build`
Expected: succeeds.

- [ ] **Step 3: Commit**

```bash
git add console/src/app/languages
git commit -m "feat: add language capability matrix page"
```

---

## Task 8: Login and logout

**Files:**
- Create: `console/src/app/login/page.tsx`
- Create: `console/src/app/actions/session.ts`
- Create: `console/src/components/Nav.tsx`
- Modify: `console/src/app/layout.tsx`

- [ ] **Step 1: Write the session actions**

```typescript
// console/src/app/actions/session.ts
"use server";

import { redirect } from "next/navigation";
import { ApiError } from "@/lib/api";
import { api } from "@/lib/server";
import { clearSession, setSession } from "@/lib/session";

export type LoginState = { kind: "idle" } | { kind: "error"; message: string };

export async function login(_prev: LoginState, formData: FormData): Promise<LoginState> {
  const passphrase = String(formData.get("passphrase") ?? "");
  const next = String(formData.get("next") ?? "/keys");

  if (!passphrase) return { kind: "error", message: "Enter the admin passphrase." };

  try {
    const { admin_token } = await api().login(passphrase);
    await setSession(admin_token);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return { kind: "error", message: "Incorrect passphrase." };
    }
    return { kind: "error", message: "Could not reach the API." };
  }
  redirect(next.startsWith("/") ? next : "/keys");
}

export async function logout(): Promise<void> {
  await clearSession();
  redirect("/login");
}
```

- [ ] **Step 2: Write the login page**

```tsx
// console/src/app/login/page.tsx
"use client";

import { useActionState } from "react";
import { login, type LoginState } from "@/app/actions/session";

const initial: LoginState = { kind: "idle" };

export default function LoginPage() {
  const [state, action, pending] = useActionState(login, initial);
  return (
    <main className="mx-auto flex max-w-md flex-col px-6 py-20">
      <h1 className="text-2xl font-semibold tracking-tight">Admin sign-in</h1>
      <p className="mt-2 text-sm text-slate-600">
        The passphrase is verified server-side and never stored in the browser. The resulting
        session token is httpOnly.
      </p>
      <form action={action} className="mt-6 space-y-4">
        <input type="hidden" name="next" value="/keys" />
        <label className="block text-sm">
          <span className="block font-medium text-slate-700">Passphrase</span>
          <input
            name="passphrase"
            type="password"
            autoComplete="current-password"
            className="mt-1 w-full rounded-md border border-slate-300 p-2"
          />
        </label>
        {state.kind === "error" && (
          <p className="text-sm text-rose-700">{state.message}</p>
        )}
        <button
          type="submit"
          disabled={pending}
          className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
```

- [ ] **Step 3: Write Nav and update layout**

```tsx
// console/src/components/Nav.tsx
import Link from "next/link";
import { logout } from "@/app/actions/session";
import { getAdminToken } from "@/lib/session";

export async function Nav() {
  const signedIn = Boolean(await getAdminToken());
  return (
    <header className="border-b border-slate-200">
      <nav className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3 text-sm">
        <Link href="/" className="font-semibold tracking-tight">Lemma</Link>
        <Link href="/" className="text-slate-600 hover:text-slate-900">Playground</Link>
        <Link href="/languages" className="text-slate-600 hover:text-slate-900">Languages</Link>
        {signedIn && (
          <>
            <Link href="/keys" className="text-slate-600 hover:text-slate-900">Keys</Link>
            <Link href="/settings" className="text-slate-600 hover:text-slate-900">Settings</Link>
            <Link href="/logs" className="text-slate-600 hover:text-slate-900">Logs</Link>
          </>
        )}
        <span className="ml-auto">
          {signedIn ? (
            <form action={logout}>
              <button className="text-slate-600 hover:text-slate-900">Sign out</button>
            </form>
          ) : (
            <Link href="/login" className="text-slate-600 hover:text-slate-900">Sign in</Link>
          )}
        </span>
      </nav>
    </header>
  );
}
```

`console/src/app/layout.tsx`:
```tsx
import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = { title: "Lemma Console", description: "Multilingual lemmatization" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-white text-slate-900 antialiased">
        <Nav />
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Build**

Run: `cd console && npm run build`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add console/src/app/login console/src/app/actions/session.ts console/src/components/Nav.tsx console/src/app/layout.tsx
git commit -m "feat: add admin login/logout with httpOnly session cookie"
```

---

## Task 9: Key management page

**Files:**
- Create: `console/src/app/keys/page.tsx`
- Create: `console/src/app/keys/actions.ts`
- Create: `console/src/app/keys/NewKeySecret.tsx`
- Test: `console/tests/keys-actions.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// console/tests/keys-actions.test.ts
import { describe, expect, it } from "vitest";
import { parseLangs, validateKeyName } from "@/app/keys/validate";

describe("key form validation", () => {
  it("rejects an empty name", () => {
    expect(() => validateKeyName("")).toThrow(/name/i);
    expect(() => validateKeyName("   ")).toThrow(/name/i);
  });

  it("accepts a normal name", () => {
    expect(validateKeyName("production-crawler")).toBe("production-crawler");
  });

  it("parses a comma-separated language list", () => {
    expect(parseLangs("de, fr ,es")).toEqual(["de", "fr", "es"]);
  });

  it("treats blank as no restriction", () => {
    expect(parseLangs("")).toEqual([]);
  });

  it("rejects an unknown language code", () => {
    expect(() => parseLangs("de,zz")).toThrow(/zz/);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd console && npx vitest run tests/keys-actions.test.ts`
Expected: FAIL — cannot resolve `@/app/keys/validate`.

- [ ] **Step 3: Write `console/src/app/keys/validate.ts`**

```typescript
export const KNOWN_LANGS = ["en", "de", "fr", "es", "ru", "ja", "ko"] as const;

export function validateKeyName(raw: string): string {
  const name = raw.trim();
  if (!name) throw new Error("Key name is required");
  if (name.length > 100) throw new Error("Key name must be 100 characters or fewer");
  return name;
}

export function parseLangs(raw: string): string[] {
  const langs = raw.split(",").map((x) => x.trim()).filter(Boolean);
  const unknown = langs.filter((l) => !(KNOWN_LANGS as readonly string[]).includes(l));
  if (unknown.length > 0) {
    throw new Error(`Unknown language code(s): ${unknown.join(", ")}`);
  }
  return langs;
}
```

- [ ] **Step 4: Write the Server Actions**

```typescript
// console/src/app/keys/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { ApiError } from "@/lib/api";
import { api } from "@/lib/server";
import { assertCsrf, getAdminToken } from "@/lib/session";
import { parseLangs, validateKeyName } from "@/app/keys/validate";

export type KeyActionResult =
  | { kind: "idle" }
  | { kind: "created"; keyId: string; secret: string; fingerprint: string }
  | { kind: "error"; message: string };

async function adminTokenOrThrow(): Promise<string> {
  const token = await getAdminToken();
  if (!token) throw new Error("Not signed in");
  return token;
}

export async function createKey(
  _prev: KeyActionResult,
  formData: FormData,
): Promise<KeyActionResult> {
  try {
    await assertCsrf(String(formData.get("csrf") ?? ""));
    const name = validateKeyName(String(formData.get("name") ?? ""));
    const langs = parseLangs(String(formData.get("langs") ?? ""));
    const allowHmac = formData.get("allow_hmac") === "on";

    const created = await api().createKey(await adminTokenOrThrow(), {
      name, langs, allow_hmac: allowHmac,
    });
    revalidatePath("/keys");
    return {
      kind: "created",
      keyId: created.key_id,
      secret: created.secret,
      fingerprint: created.secret_fingerprint,
    };
  } catch (error) {
    if (error instanceof ApiError) return { kind: "error", message: `${error.code}: ${error.message}` };
    return { kind: "error", message: error instanceof Error ? error.message : "Failed" };
  }
}

export async function rotateKey(formData: FormData): Promise<void> {
  await assertCsrf(String(formData.get("csrf") ?? ""));
  const keyId = String(formData.get("key_id") ?? "");
  await api().rotateKey(await adminTokenOrThrow(), keyId);
  revalidatePath("/keys");
}

export async function revokeKey(formData: FormData): Promise<void> {
  await assertCsrf(String(formData.get("csrf") ?? ""));
  const keyId = String(formData.get("key_id") ?? "");
  await api().revokeKey(await adminTokenOrThrow(), keyId);
  revalidatePath("/keys");
}
```

- [ ] **Step 5: Write `NewKeySecret.tsx` and the page**

```tsx
// console/src/app/keys/NewKeySecret.tsx
"use client";

import { CopyButton } from "@/components/CopyButton";

export function NewKeySecret({ keyId, secret, fingerprint }: {
  keyId: string; secret: string; fingerprint: string;
}) {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h2 className="text-sm font-semibold text-amber-900">
        Copy this secret now — it will not be shown again
      </h2>
      <p className="mt-1 text-xs text-amber-800">
        Only an encrypted copy is stored. If you lose it you must rotate the key.
      </p>
      <dl className="mt-4 space-y-2 text-sm">
        <div className="flex items-baseline gap-3">
          <dt className="w-24 shrink-0 text-xs uppercase tracking-wide text-amber-700">key_id</dt>
          <dd className="font-mono">{keyId}</dd>
        </div>
        <div className="flex items-baseline gap-3">
          <dt className="w-24 shrink-0 text-xs uppercase tracking-wide text-amber-700">secret</dt>
          <dd className="break-all font-mono">{secret}</dd>
        </div>
        <div className="flex items-baseline gap-3">
          <dt className="w-24 shrink-0 text-xs uppercase tracking-wide text-amber-700">fingerprint</dt>
          <dd className="font-mono text-slate-600">{fingerprint}</dd>
        </div>
      </dl>
      <div className="mt-4 flex gap-2">
        <CopyButton text={`${keyId}.${secret}`} />
        <CopyButton text={secret} />
      </div>
    </div>
  );
}
```

```tsx
// console/src/app/keys/page.tsx
import { api } from "@/lib/server";
import { getAdminToken } from "@/lib/session";
import { Badge } from "@/components/Badge";
import { KeyForm } from "@/app/keys/KeyForm";
import { rotateKey, revokeKey } from "@/app/keys/actions";
import type { KeyRecord } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function KeysPage() {
  const token = await getAdminToken();
  if (!token) return null; // middleware already redirects; this satisfies types
  const keys: KeyRecord[] = await api().listKeys(token);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">API keys</h1>
      <KeyForm />

      <div className="mt-8 overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Name</th>
              <th className="px-4 py-2">key_id</th>
              <th className="px-4 py-2">Fingerprint</th>
              <th className="px-4 py-2">Langs</th>
              <th className="px-4 py-2">HMAC</th>
              <th className="px-4 py-2">rpm</th>
              <th className="px-4 py-2">Last used</th>
              <th className="px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {keys.map((k) => (
              <tr key={k.key_id} className={k.revoked_at ? "bg-slate-50 text-slate-400" : ""}>
                <td className="px-4 py-2 font-medium">{k.name}</td>
                <td className="px-4 py-2 font-mono text-xs">{k.key_id}</td>
                <td className="px-4 py-2 font-mono text-xs">{k.secret_fingerprint}</td>
                <td className="px-4 py-2 text-xs">
                  {k.langs.length === 0 ? <em>all</em> : k.langs.join(", ")}
                </td>
                <td className="px-4 py-2">
                  <Badge tone={k.allow_hmac ? "ok" : "muted"}>{k.allow_hmac ? "yes" : "no"}</Badge>
                </td>
                <td className="px-4 py-2 text-xs">{k.rate_limit_rpm}</td>
                <td className="px-4 py-2 text-xs">{k.last_used_at ?? "never"}</td>
                <td className="px-4 py-2">
                  {k.revoked_at ? (
                    <Badge tone="warn">revoked</Badge>
                  ) : (
                    <div className="flex gap-2">
                      <form action={rotateKey}>
                        <input type="hidden" name="key_id" value={k.key_id} />
                        <button className="text-xs text-slate-600 underline">rotate</button>
                      </form>
                      <form action={revokeKey}>
                        <input type="hidden" name="key_id" value={k.key_id} />
                        <button className="text-xs text-rose-600 underline">revoke</button>
                      </form>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
```

- [ ] **Step 6: Write `KeyForm.tsx` with the one-time secret surface**

```tsx
// console/src/app/keys/KeyForm.tsx
"use client";

import { useActionState, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createKey, type KeyActionResult } from "@/app/keys/actions";
import { NewKeySecret } from "@/app/keys/NewKeySecret";
import { readCsrfToken } from "@/lib/csrf-client";

const initial: KeyActionResult = { kind: "idle" };

export function KeyForm() {
  const [state, action, pending] = useActionState(createKey, initial);
  const [csrf, setCsrf] = useState("");
  const router = useRouter();

  useEffect(() => setCsrf(readCsrfToken()), []);

  // Clear the secret from the UI as soon as the operator navigates away.
  useEffect(() => () => { if (state.kind === "created") router.refresh(); }, [state, router]);

  return (
    <section className="mt-6 space-y-4">
      <form action={action} className="grid gap-3 rounded-xl border border-slate-200 p-5 sm:grid-cols-4">
        <input type="hidden" name="csrf" value={csrf} />
        <label className="text-sm sm:col-span-2">
          <span className="block font-medium text-slate-700">Name</span>
          <input name="name" placeholder="production-crawler"
            className="mt-1 w-full rounded-md border border-slate-300 p-2" />
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Restrict langs</span>
          <input name="langs" placeholder="de,fr (blank = all)"
            className="mt-1 w-full rounded-md border border-slate-300 p-2" />
        </label>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input name="allow_hmac" type="checkbox" />
          <span className="text-slate-700">Allow HMAC</span>
        </label>
        <div className="sm:col-span-4">
          <button type="submit" disabled={pending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {pending ? "Creating…" : "Create key"}
          </button>
        </div>
      </form>

      {state.kind === "error" && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-900">
          {state.message}
        </div>
      )}
      {state.kind === "created" && (
        <NewKeySecret keyId={state.keyId} secret={state.secret} fingerprint={state.fingerprint} />
      )}
    </section>
  );
}
```

- [ ] **Step 7: Write `console/src/lib/csrf-client.ts`**

```typescript
/**
 * Reads the CSRF cookie in the browser. This is the double-submit half: the
 * cookie proves the request came from our origin, the echoed form field proves
 * the page saw the cookie. Only the CSRF cookie is client-readable by design.
 */
export function readCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)lemma_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}
```

- [ ] **Step 8: Run tests and build**

Run: `cd console && npx vitest run && npm run build`
Expected: all tests pass, build succeeds.

- [ ] **Step 9: Commit**

```bash
git add console/src/app/keys console/src/lib/csrf-client.ts console/tests/keys-actions.test.ts
git commit -m "feat: add key management with one-time secret display and CSRF"
```

---

## Task 10: Settings and diagnostics page

**Files:**
- Create: `console/src/app/settings/page.tsx`
- Create: `console/src/app/settings/actions.ts`
- Create: `console/src/app/settings/SettingRow.tsx`

The page has two visually separate halves. Diagnostics is read-only and must stay that way — merging it into the editable settings table is how a console becomes able to brick its own service.

- [ ] **Step 1: Write the settings action**

```typescript
// console/src/app/settings/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { ApiError } from "@/lib/api";
import { api } from "@/lib/server";
import { assertCsrf, getAdminToken } from "@/lib/session";

export async function updateSetting(formData: FormData): Promise<void> {
  await assertCsrf(String(formData.get("csrf") ?? ""));
  const token = await getAdminToken();
  if (!token) throw new Error("Not signed in");

  const key = String(formData.get("key") ?? "");
  const raw = String(formData.get("value") ?? "");
  const kind = String(formData.get("kind") ?? "string");

  const value =
    kind === "bool" ? raw === "true"
    : kind === "int" ? Number.parseInt(raw, 10)
    : kind === "lang_set" ? raw.split(",").map((s) => s.trim()).filter(Boolean)
    : raw;

  try {
    await api().patchSetting(token, key, value);
  } catch (error) {
    if (error instanceof ApiError) throw new Error(`${error.code}: ${error.message}`);
    throw error;
  }
  revalidatePath("/settings");
}
```

- [ ] **Step 2: Write the page**

```tsx
// console/src/app/settings/page.tsx
import { api } from "@/lib/server";
import { getAdminToken } from "@/lib/session";
import { Badge } from "@/components/Badge";
import { SettingRow } from "@/app/settings/SettingRow";
import type { SettingRow as Row } from "@/lib/types";

export const dynamic = "force-dynamic";

type Diagnostics = {
  backends: Record<string, { status: string; backend: string | null; version: string | null; reason: string | null }>;
  master_key: string;
  service_token: string;
  db_url_kind: string;
};

export default async function SettingsPage() {
  const token = await getAdminToken();
  if (!token) return null;

  const [settings, diagnostics] = await Promise.all([
    api().readSettings(token),
    api().diagnostics(token) as Promise<Diagnostics>,
  ]);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 space-y-12">
      <section>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">Diagnostics</h1>
          <Badge tone="muted">read-only</Badge>
        </div>
        <p className="mt-1 text-sm text-slate-600">
          Deployment facts. These cannot be changed here — doing so from a web UI is how a console
          makes its own service unreachable.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-200 p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">Master key</div>
            <div className="mt-1 font-mono text-sm">{diagnostics.master_key}</div>
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">Service token</div>
            <div className="mt-1 font-mono text-sm">{diagnostics.service_token}</div>
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500">Storage</div>
            <div className="mt-1 font-mono text-sm">{diagnostics.db_url_kind}</div>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Lang</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Backend</th>
                <th className="px-4 py-2">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(diagnostics.backends).map(([lang, info]) => (
                <tr key={lang}>
                  <td className="px-4 py-2 font-mono">{lang}</td>
                  <td className="px-4 py-2">
                    <Badge tone={info.status === "ok" ? "ok" : "warn"}>{info.status}</Badge>
                  </td>
                  <td className="px-4 py-2 text-slate-600">
                    {info.backend ? `${info.backend} ${info.version}` : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-rose-700">{info.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">Settings</h2>
        <p className="mt-1 text-sm text-slate-600">
          Only whitelisted keys are editable. Entries marked <Badge tone="warn">restart</Badge>{" "}
          take effect after the API restarts.
        </p>

        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Key</th>
                <th className="px-4 py-2">Value</th>
                <th className="px-4 py-2">Default</th>
                <th className="px-4 py-2">Applied</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(settings as Row[]).map((row) => (
                <SettingRow key={row.key} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
```

- [ ] **Step 3: Write `SettingRow.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import { updateSetting } from "@/app/settings/actions";
import { Badge } from "@/components/Badge";
import { readCsrfToken } from "@/lib/csrf-client";
import type { SettingRow as Row } from "@/lib/types";

function asInputValue(row: Row): string {
  if (row.kind === "lang_set") return (row.value as string[]).join(",");
  return String(row.value);
}

export function SettingRow({ row }: { row: Row }) {
  const [csrf, setCsrf] = useState("");
  useEffect(() => setCsrf(readCsrfToken()), []);

  return (
    <tr>
      <td className="px-4 py-2 font-mono text-xs">{row.key}</td>
      <td className="px-4 py-2">
        <form action={updateSetting} className="flex items-center gap-2">
          <input type="hidden" name="csrf" value={csrf} />
          <input type="hidden" name="key" value={row.key} />
          <input type="hidden" name="kind" value={row.kind} />

          {row.kind === "bool" ? (
            <select name="value" defaultValue={String(row.value)}
              className="rounded border border-slate-300 p-1 text-xs">
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : row.kind === "enum" ? (
            <select name="value" defaultValue={String(row.value)}
              className="rounded border border-slate-300 p-1 text-xs">
              {row.values.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          ) : (
            <input name="value" defaultValue={asInputValue(row)}
              className="w-48 rounded border border-slate-300 p-1 font-mono text-xs" />
          )}

          <button className="rounded bg-slate-900 px-2 py-1 text-xs text-white">Save</button>
        </form>
      </td>
      <td className="px-4 py-2 font-mono text-xs text-slate-500">
        {row.kind === "lang_set" ? (row.default as string[]).join(",") : String(row.default)}
      </td>
      <td className="px-4 py-2">
        {row.hot ? <Badge tone="ok">live</Badge> : <Badge tone="warn">restart</Badge>}
        {row.overridden && <Badge tone="muted">changed</Badge>}
      </td>
      <td className="px-4 py-2 text-xs text-slate-500">
        {row.min !== null && row.max !== null ? `${row.min}–${row.max}` : ""}
      </td>
    </tr>
  );
}
```

- [ ] **Step 4: Build**

Run: `cd console && npm run build`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add console/src/app/settings
git commit -m "feat: add read-only diagnostics and whitelisted settings editor"
```

---

## Task 11: Logs page

**Files:**
- Create: `console/src/app/logs/page.tsx`

- [ ] **Step 1: Write the page**

```tsx
import { api } from "@/lib/server";
import { getAdminToken } from "@/lib/session";
import type { AuditEntry } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function LogsPage() {
  const token = await getAdminToken();
  if (!token) return null;
  const entries: AuditEntry[] = await api().readAudit(token, 100, 0);

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
      <p className="mt-1 text-sm text-slate-600">
        Every key and setting mutation is recorded with its before and after values.
      </p>

      <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">When</th>
              <th className="px-4 py-2">Actor</th>
              <th className="px-4 py-2">Action</th>
              <th className="px-4 py-2">Target</th>
              <th className="px-4 py-2">Before</th>
              <th className="px-4 py-2">After</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {entries.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">
                  No mutations recorded yet.
                </td>
              </tr>
            )}
            {entries.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-2 font-mono text-xs text-slate-500">{e.at}</td>
                <td className="px-4 py-2 text-xs">{e.actor}</td>
                <td className="px-4 py-2 font-mono text-xs">{e.action}</td>
                <td className="px-4 py-2 font-mono text-xs">{e.target}</td>
                <td className="px-4 py-2 font-mono text-xs text-slate-500">{e.before_json ?? "—"}</td>
                <td className="px-4 py-2 font-mono text-xs">{e.after_json ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Build and run the full test suite**

Run: `cd console && npx vitest run && npm run build`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add console/src/app/logs
git commit -m "feat: add audit log page"
```

---

## Task 12: Docker images and compose

**Files:**
- Create: `deploy/api.Dockerfile`
- Create: `deploy/console.Dockerfile`
- Create: `deploy/docker-compose.yml`
- Modify: `console/next.config.ts`

- [ ] **Step 1: Configure Next.js standalone output**

```typescript
// console/next.config.ts
import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  // The console never imports the API's Python packages; keep the image small.
  experimental: { serverActions: { bodySizeLimit: "1mb" } },
};

export default config;
```

- [ ] **Step 2: Write `deploy/api.Dockerfile`**

```dockerfile
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

# Pinned so a rebuild months later produces the same wheels.
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install \
      "fastapi==0.162.0" "uvicorn[standard]==0.54.0" "pydantic==2.14.1" \
      "sqlalchemy==2.1.6" "cryptography==50.0.2" "argon2-cffi==25.1.0" \
      "simplemma==2.0.0" "lemminflect==0.2.3" \
      "pymorphy3==2.0.6" "pymorphy3-dicts-ru==2.4.417150.4580142" \
      "sudachipy==0.7.0" "sudachidict_core==20261015" \
      "kiwipiepy==0.24.1" "kiwipiepy_model==0.24.0"

COPY api ./api

# Refuse to run insecurely: auth must be on in any image built from this file.
ENV LEMMA_AUTH_ENABLED=1 LEMMA_REQUIRE_AUTH=1

RUN useradd --create-home --uid 10001 lemma && mkdir -p /data && chown lemma /data
USER lemma
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/v1/health').status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

- [ ] **Step 3: Write `deploy/console.Dockerfile`**

```dockerfile
FROM node:24-alpine AS deps
WORKDIR /app
COPY console/package.json console/package-lock.json ./
RUN npm ci

FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY console/ ./
RUN npm run build

FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3000
RUN addgroup -g 10001 nodejs && adduser -u 10001 -G nodejs -S nextjs
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

- [ ] **Step 4: Write `deploy/docker-compose.yml`**

```yaml
services:
  api:
    build:
      context: ..
      dockerfile: deploy/api.Dockerfile
    environment:
      LEMMA_MASTER_KEY: ${LEMMA_MASTER_KEY:?must be 32 random hex bytes, see deploy/README.md}
      LEMMA_SERVICE_TOKEN: ${LEMMA_SERVICE_TOKEN:?must be a long random value}
      LEMMA_ADMIN_PASSPHRASE_HASH: ${LEMMA_ADMIN_PASSPHRASE_HASH:?run python -m api.cli hash-passphrase}
      LEMMA_DB_PATH: /data/lemming.db
      LEMMA_AUTH_ENABLED: "1"
      LEMMA_REQUIRE_AUTH: "1"
    volumes:
      - lemmadata:/data
    # Deliberately NOT published: only the console reaches the API.
    expose:
      - "8000"
    restart: unless-stopped

  console:
    build:
      context: ..
      dockerfile: deploy/console.Dockerfile
    environment:
      LEMMA_API_URL: http://api:8000
      LEMMA_SERVICE_TOKEN: ${LEMMA_SERVICE_TOKEN:?must match the api service}
      LEMMA_DEMO_KEY: ${LEMMA_DEMO_KEY:-}
      LEMMA_PUBLIC_API_URL: ${LEMMA_PUBLIC_API_URL:-http://localhost:3000}
    ports:
      - "3000:3000"
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

volumes:
  lemmadata:
```

- [ ] **Step 5: Verify the compose file is valid**

Run: `cd deploy && LEMMA_MASTER_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))') LEMMA_SERVICE_TOKEN=x LEMMA_ADMIN_PASSPHRASE_HASH=x docker compose config >/dev/null && echo "compose OK"`
Expected: `compose OK`. If docker is unavailable, run `python3 -c "import yaml,sys; yaml.safe_load(open('docker-compose.yml'))"` instead and note that the images were not built.

- [ ] **Step 6: Commit**

```bash
git add deploy console/next.config.ts
git commit -m "feat: add api and console Docker images with compose stack"
```

---

## Task 13: Ops runbook

**Files:**
- Create: `deploy/README.md`

- [ ] **Step 1: Write `deploy/README.md`**

```markdown
# Lemma API — operations

## First run

```bash
export LEMMA_MASTER_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')
export LEMMA_ADMIN_PASSPHRASE_HASH=$(python -m api.cli hash-passphrase 'your passphrase')

docker compose up -d --build
docker compose exec api python -m api.cli create-key --name console-demo --allow-hmac
```

Put the printed `key_id.secret` into `LEMMA_DEMO_KEY` in `.env` and restart `console`.

Open http://localhost:3000, sign in with the passphrase.

## Secrets you must not lose

| Variable | If lost |
|---|---|
| `LEMMA_MASTER_KEY` | Every stored API secret becomes unverifiable. All keys must be reissued. |
| `LEMMA_SERVICE_TOKEN` | Console cannot reach the API. Rotate it in both services together. |
| `LEMMA_ADMIN_PASSPHRASE_HASH` | No admin access. Regenerate and restart `api`. |

**Back up `LEMMA_MASTER_KEY` outside this host.** It is not in the database, and without it the encrypted secrets in `lemming.db` are unrecoverable by design.

## Backups

The whole state is one SQLite file:

```bash
docker compose exec api sqlite3 /data/lemming.db ".backup /data/backup.db"
docker compose cp api:/data/backup.db ./lemming-$(date +%F).db
```

Run this before every upgrade. Restore by replacing the file while the stack is stopped.

## Rotating an API key

Console → Keys → `rotate`. The old secret keeps working for 24 hours so callers can switch without downtime; responses carry `X-Secret-Rotated: true` during that window.

If `LEMMA_MASTER_KEY` is compromised, rotation alone is insufficient: every key must be reissued, because the attacker can decrypt `secret_enc`.

## Rate limiting and single-instance assumptions

The nonce cache and rate-limit buckets are **in-process**. Running more than one `api` replica breaks HMAC replay protection (a nonce consumed on replica A is unknown to B). Scale `--workers` only; do not scale replicas without moving both caches to a shared store.

## Health

`GET /v1/health` needs no credentials and reports per-backend readiness. A backend can be `unavailable` while the service is otherwise healthy — check Settings → Diagnostics for the reason.

## Logs

```bash
docker compose logs -f api console
```

Audit entries (key and settings changes) live in the database, not stdout. View them at `/logs`.
```

- [ ] **Step 2: Commit**

```bash
git add deploy/README.md
git commit -m "docs: add operations runbook"
```

---

## Task 14: End-to-end verification

**Files:**
- Create: `console/e2e/smoke.spec.ts`
- Create: `console/playwright.config.ts`

- [ ] **Step 1: Write the Playwright config and spec**

```typescript
// console/playwright.config.ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000" },
});
```

```typescript
// console/e2e/smoke.spec.ts
import { expect, test } from "@playwright/test";

const PASSPHRASE = process.env.E2E_ADMIN_PASSPHRASE ?? "test-passphrase";

test("playground lemmatizes without exposing a credential", async ({ page }) => {
  await page.goto("/");
  await page.selectOption('select[name="lang"]', "de");
  await page.fill('input[name="text"]', "Häuser");
  await page.click('button[type="submit"]');

  await expect(page.getByRole("cell", { name: "Haus" })).toBeVisible();
  // The demo key must never reach the browser: not in the DOM, not in cookies.
  const html = await page.content();
  expect(html).not.toMatch(/ls_[A-Za-z0-9]{10,}/);
  const cookies = await page.context().cookies();
  expect(cookies.some((c) => c.value.includes("ls_"))).toBe(false);
});

test("admin cookie is httpOnly", async ({ page, context }) => {
  await page.goto("/login");
  await page.fill('input[name="passphrase"]', PASSPHRASE);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/keys/);

  const cookies = await context.cookies();
  const admin = cookies.find((c) => c.name === "lemma_admin");
  expect(admin?.httpOnly).toBe(true);

  // The browser must not be able to read it.
  await page.goto("/keys");
  const readable = await page.evaluate(() => document.cookie);
  expect(readable).not.toContain(admin!.value);
});

test("a created key is shown once and then gone", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[name="passphrase"]', PASSPHRASE);
  await page.click('button[type="submit"]');
  await page.waitForURL(/\/keys/);

  await page.fill('input[name="name"]', `e2e-${Date.now()}`);
  await page.click("text=Create key");
  await expect(page.getByText(/will not be shown again/)).toBeVisible();
  const secretText = await page.locator("dd.break-all").first().innerText();
  expect(secretText).toMatch(/^ls_/);

  await page.reload();
  const html = await page.content();
  expect(html).not.toContain(secretText);
});

test("protected routes redirect to login", async ({ page }) => {
  await page.context().clearCookies();
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/login\?next=%2Fsettings/);
});
```

- [ ] **Step 2: Run the stack and the E2E suite**

Run:
```bash
cd deploy && docker compose up -d --build
cd ../console && npx playwright install --with-deps chromium && npm run e2e
```
Expected: 4 passed. If Docker is unavailable here, record that the E2E suite was written but not executed, and say so explicitly rather than claiming it passes.

- [ ] **Step 3: Tear down**

```bash
cd deploy && docker compose down -v
```

- [ ] **Step 4: Commit**

```bash
git add console/e2e console/playwright.config.ts
git commit -m "test: add E2E smoke tests for playground, cookie secrecy and one-time secret"
```

---

## Self-review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §8.1 five pages | Tasks 6, 7, 8, 9, 10, 11 |
| §8.2 Playground via BFF, browser holds no key | Task 6, asserted in Task 14 |
| §8.3 App Router + Server Actions, no client state lib | everywhere; only `useState`/`useActionState` |
| §9 docker-compose, api not published | Task 12 |
| §9 image size accepted | Task 12 |
| §5.5 admin token in httpOnly cookie | Task 3, 8, asserted in Task 14 |
| §5.5 CSRF double-submit | Tasks 3, 9, 10 |
| §11 Kiwi/single-instance risks | Task 13 runbook |

**Security invariants, each pinned by a test or a config:**

| Invariant | Enforced by |
|---|---|
| No secret in the browser | Task 14 `html` / cookie assertions |
| Service token never `NEXT_PUBLIC_` | Task 2 test rejects the prefix |
| Admin token httpOnly | Task 3 unit test + Task 14 browser test |
| CSRF on mutations | Task 3 `assertCsrf`, called by Tasks 9, 10 |
| Diagnostics read-only | Plan 2 returns 405 on PATCH; Task 10 renders no editor |

**Deliberately not covered:** `request_log` traffic view (needs a Plan 2 writer task first), key detail/edit pages, i18n, dark mode, billing.

**Known gap to raise, not hide:** Task 12's `deploy/api.Dockerfile` pins versions that were resolved on this machine. If a pin is unavailable for `linux/amd64` the build fails loudly at `pip install`, which is the safe direction — do not relax the pins to unpinned names to make it build.

**Type consistency:** `LanguageEntry`/`KeyRecord`/`SettingRow`/`AuditEntry` defined once in `src/lib/types.ts` (Task 4) and imported everywhere. `ApiClient` methods used by Tasks 6, 9, 10, 11 match Task 4's signatures. `assertCsrf` (Task 3) is called with the `csrf` form field that Tasks 9 and 10 both set from `readCsrfToken()` (Task 9).
