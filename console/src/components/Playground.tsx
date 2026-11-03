"use client";

import { useActionState } from "react";
import { runLemmatize, type PlaygroundState } from "@/app/actions/lemmatize";
import type { LanguageEntry } from "@/lib/types";
import { ResultTable } from "@/components/ResultTable";
import { Highlighted } from "@/components/Highlighted";
import { CopyButton } from "@/components/CopyButton";

const initial: PlaygroundState = { kind: "idle" };

export function Playground({ languages }: { languages: LanguageEntry[] }) {
  const [state, action, pending] = useActionState(runLemmatize, initial);

  return (
    <div className="mt-6 space-y-6">
      <form action={action} className="space-y-4 rounded-xl border border-slate-200 p-5">
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="text-sm">
            <span className="block font-medium text-slate-700">Language</span>
            <select
              name="lang"
              defaultValue="de"
              className="mt-1 w-full rounded-md border border-slate-300 p-2"
            >
              {languages.map((l) => (
                <option key={l.lang} value={l.lang} disabled={l.status !== "ok"}>
                  {l.lang} — {l.backend?.name ?? "unavailable"}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm sm:col-span-2">
            <span className="block font-medium text-slate-700">
              Text <span className="font-normal text-slate-500">(one word or a sentence)</span>
            </span>
            <input
              name="text"
              defaultValue="Häuser"
              className="mt-1 w-full rounded-md border border-slate-300 p-2"
            />
          </label>
        </div>
        <label className="block text-sm">
          <span className="block font-medium text-slate-700">
            POS <span className="font-normal text-slate-500">(optional, single word only)</span>
          </span>
          <input
            name="pos"
            placeholder="VERB"
            className="mt-1 w-full rounded-md border border-slate-300 p-2 sm:w-48"
          />
        </label>
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {pending ? "Lemmatizing…" : "Lemmatize"}
        </button>
      </form>

      {state.kind === "error" && (
        <div className="rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm">
          <div className="font-mono text-xs text-rose-700">{state.code}</div>
          <div className="mt-1 text-rose-900">{state.message}</div>
        </div>
      )}

      {state.kind === "ok" && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600">
            <span className="rounded bg-slate-100 px-2 py-1 font-mono">
              {state.response.backend.name} {state.response.backend.version}
            </span>
            <span className="rounded bg-slate-100 px-2 py-1 font-mono">
              segmented_by: {state.response.segmented_by}
            </span>
            <span>{state.response.elapsed_ms} ms</span>
            <span className="font-mono">{state.response.request_id}</span>
          </div>
          {state.submitted && (
            <Highlighted
              text={state.submitted}
              items={state.response.items}
              offsetUnit={state.response.offset_unit}
            />
          )}
          <ResultTable response={state.response} />
          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-slate-700">Equivalent request</h2>
              <CopyButton text={state.curl} />
            </div>
            <pre className="mt-2 overflow-x-auto text-xs leading-relaxed text-slate-800">
              {state.curl}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
