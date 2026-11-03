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
