"use server";

import { api, demoKey } from "@/lib/server";
import { ApiError } from "@/lib/api";
import { buildCurl } from "@/lib/curl";
import type { LemmatizeResponse } from "@/lib/types";

export type PlaygroundState =
  | { kind: "idle" }
  | { kind: "ok"; response: LemmatizeResponse; curl: string; submitted: string }
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

  // Only use the `tokens` path when a POS tag must be attached to one token.
  // Everything else goes through `text`, because the `tokens` path carries no
  // source string and therefore no offsets — which would silently disable
  // highlighting. Never infer "one word" from the absence of whitespace:
  // Japanese and Korean sentences contain none but are many morphemes.
  const useTokens = posRaw.length > 0;
  const payload = useTokens
    ? { lang, tokens: [text], pos: [posRaw] }
    : { lang, text };

  try {
    const response = await api().lemmatize(key, payload);
    const publicBase = process.env.LEMMA_PUBLIC_API_URL ?? "https://your-host";
    return {
      kind: "ok",
      response,
      curl: buildCurl(publicBase, payload),
      submitted: useTokens ? "" : text,
    };
  } catch (error) {
    if (error instanceof ApiError) {
      return { kind: "error", code: error.code, message: error.message };
    }
    return { kind: "error", code: "INTERNAL", message: "Unexpected error contacting the API." };
  }
}
