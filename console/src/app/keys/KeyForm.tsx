"use client";

import { useActionState, useEffect, useState } from "react";
import { createKey, type KeyActionResult } from "@/app/keys/actions";
import { NewKeySecret } from "@/app/keys/NewKeySecret";
import { readCsrfToken } from "@/lib/csrf-client";

const initial: KeyActionResult = { kind: "idle" };

export function KeyForm() {
  const [state, action, pending] = useActionState(createKey, initial);
  const [csrf, setCsrf] = useState("");

  useEffect(() => setCsrf(readCsrfToken()), []);

  return (
    <section className="mt-6 space-y-4">
      <form action={action} className="grid gap-4 rounded-xl border border-slate-200 p-5 sm:grid-cols-4">
        <input type="hidden" name="csrf" value={csrf} />
        <label className="text-sm sm:col-span-2">
          <span className="block font-medium text-slate-700">Name</span>
          <input
            name="name"
            placeholder="production-crawler"
            className="mt-1 w-full rounded-md border border-slate-300 p-2"
          />
        </label>
        <label className="text-sm">
          <span className="block font-medium text-slate-700">Restrict langs</span>
          <input
            name="langs"
            placeholder="de,fr (blank = all)"
            className="mt-1 w-full rounded-md border border-slate-300 p-2"
          />
        </label>
        <label className="flex items-end gap-2 pb-2 text-sm">
          <input name="allow_hmac" type="checkbox" />
          <span className="text-slate-700">Allow HMAC</span>
        </label>
        <div className="sm:col-span-4">
          <button
            type="submit"
            disabled={pending}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "Creating…" : "Create key"}
          </button>
        </div>
      </form>

      {state.kind === "error" && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-900">
          {state.message}
        </div>
      )}
      {state.kind === "created" && (
        <NewKeySecret keyId={state.keyId} secret={state.secret} fingerprint={state.fingerprint} />
      )}
    </section>
  );
}
