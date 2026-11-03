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
