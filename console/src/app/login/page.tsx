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
        {state.kind === "error" && <p className="text-sm text-rose-700">{state.message}</p>}
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
