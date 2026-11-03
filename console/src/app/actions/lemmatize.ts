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
    const publicBase = process.env.LEMMA_PUBLIC_API_URL ?? "https://your-host";
    return {
      kind: "ok",
      response,
      curl: buildCurl(publicBase, payload),
      submitted: isSingleWord ? "" : text,
    };
  } catch (error) {
    if (error instanceof ApiError) {
      return { kind: "error", code: error.code, message: error.message };
    }
    return { kind: "error", code: "INTERNAL", message: "Unexpected error contacting the API." };
  }
}
