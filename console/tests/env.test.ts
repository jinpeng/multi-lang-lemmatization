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
