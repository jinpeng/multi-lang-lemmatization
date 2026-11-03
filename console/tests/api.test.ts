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
