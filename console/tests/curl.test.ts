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
