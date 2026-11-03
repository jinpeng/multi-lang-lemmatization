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
      name,
      langs,
      allow_hmac: allowHmac,
    });
    revalidatePath("/keys");
    return {
      kind: "created",
      keyId: created.key_id,
      secret: created.secret,
      fingerprint: created.secret_fingerprint,
    };
  } catch (error) {
    if (error instanceof ApiError)
      return { kind: "error", message: `${error.code}: ${error.message}` };
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
