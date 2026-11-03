import { connection } from "next/server";
import { api } from "@/lib/server";
import { Badge } from "@/components/Badge";
import type { LanguageEntry } from "@/lib/types";

function Flag({ on }: { on: boolean }) {
  return on ? <span className="text-emerald-600">●</span> : <span className="text-slate-300">○</span>;
}

export async function LanguagesTable() {
  // Live API data: must be read per request, never prerendered.
  await connection();
  const languages: LanguageEntry[] = await api().languages();

  return (
    <>
      <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2">Lang</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Backend</th>
              <th className="px-4 py-2">POS scheme</th>
              <th className="px-4 py-2">pos</th>
              <th className="px-4 py-2">pos_accepted</th>
              <th className="px-4 py-2">reading</th>
              <th className="px-4 py-2">tokenizes</th>
              <th className="px-4 py-2">Options</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {languages.map((l) => (
              <tr key={l.lang} className={l.status !== "ok" ? "bg-rose-50/40" : ""}>
                <td className="px-4 py-2 font-mono font-medium">{l.lang}</td>
                <td className="px-4 py-2">
                  <Badge tone={l.status === "ok" ? "ok" : "warn"}>{l.status}</Badge>
                </td>
                <td className="px-4 py-2 text-slate-600">
                  {l.backend ? `${l.backend.name} ${l.backend.version}` : "—"}
                </td>
                <td className="px-4 py-2 font-mono text-xs text-slate-600">
                  {l.pos_scheme ?? "—"}
                </td>
                <td className="px-4 py-2"><Flag on={l.capabilities.pos} /></td>
                <td className="px-4 py-2"><Flag on={l.capabilities.pos_accepted} /></td>
                <td className="px-4 py-2"><Flag on={l.capabilities.reading} /></td>
                <td className="px-4 py-2"><Flag on={l.capabilities.tokenizes} /></td>
                <td className="px-4 py-2 text-xs text-slate-600">
                  {Object.keys(l.options).length === 0
                    ? "—"
                    : Object.entries(l.options)
                        .map(([k, v]) => `${k}=${String(v.default)}`)
                        .join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {languages.some((l) => l.status !== "ok") && (
        <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          Some backends failed to initialise. Requests for those languages return{" "}
          <code>503 LANGUAGE_UNAVAILABLE</code> with the reason recorded in{" "}
          <a className="underline" href="/settings">Settings → Diagnostics</a>.
        </div>
      )}
    </>
  );
}
