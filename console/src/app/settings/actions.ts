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
    kind === "bool"
      ? raw === "true"
      : kind === "int"
        ? Number.parseInt(raw, 10)
        : kind === "lang_set"
          ? raw
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean)
          : raw;

  try {
    await api().patchSetting(token, key, value);
  } catch (error) {
    if (error instanceof ApiError) throw new Error(`${error.code}: ${error.message}`);
    throw error;
  }
  revalidatePath("/settings");
}
