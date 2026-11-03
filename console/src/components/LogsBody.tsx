import { connection } from "next/server";
import { api } from "@/lib/server";
import { getAdminToken } from "@/lib/session";
import type { AuditEntry, RequestRow } from "@/lib/types";

export async function LogsBody() {
  await connection();
  const token = await getAdminToken();
  if (!token) return null;

  const [entries, requests] = await Promise.all([
    api().readAudit(token, 100, 0),
    api().readRequests(token, 100, 0),
  ]);

  return (
    <div className="space-y-12">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight">Recent requests</h1>
        <p className="mt-1 text-sm text-slate-600">
          Request <em>shape</em> only — language, token count, latency, status. Request text is
          deliberately never stored, so this is not a transcript of what anyone sent.
        </p>
        <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">When</th>
                <th className="px-4 py-2">Request</th>
                <th className="px-4 py-2">Key</th>
                <th className="px-4 py-2">Lang</th>
                <th className="px-4 py-2">Tokens</th>
                <th className="px-4 py-2">ms</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {requests.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-slate-500">
                    No requests recorded yet.
                  </td>
                </tr>
              )}
              {(requests as RequestRow[]).map((r) => (
                <tr key={r.id} className={r.status >= 400 ? "bg-rose-50/40" : ""}>
                  <td className="px-4 py-2 font-mono text-xs text-slate-500">{r.at}</td>
                  <td className="px-4 py-2 font-mono text-xs">{r.request_id}</td>
                  <td className="px-4 py-2 font-mono text-xs">{r.key_id ?? "—"}</td>
                  <td className="px-4 py-2 font-mono text-xs">{r.lang ?? "—"}</td>
                  <td className="px-4 py-2 text-xs">{r.n_tokens ?? "—"}</td>
                  <td className="px-4 py-2 text-xs">{r.latency_ms}</td>
                  <td className="px-4 py-2 text-xs">
                    {r.status}
                    {r.error_code ? ` ${r.error_code}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">Audit log</h2>
        <p className="mt-1 text-sm text-slate-600">
          Every key and setting mutation is recorded with its before and after values.
        </p>
        <div className="mt-6 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">When</th>
                <th className="px-4 py-2">Actor</th>
                <th className="px-4 py-2">Action</th>
                <th className="px-4 py-2">Target</th>
                <th className="px-4 py-2">Before</th>
                <th className="px-4 py-2">After</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {entries.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">
                    No mutations recorded yet.
                  </td>
                </tr>
              )}
              {(entries as AuditEntry[]).map((e) => (
                <tr key={e.id}>
                  <td className="px-4 py-2 font-mono text-xs text-slate-500">{e.at}</td>
                  <td className="px-4 py-2 text-xs">{e.actor}</td>
                  <td className="px-4 py-2 font-mono text-xs">{e.action}</td>
                  <td className="px-4 py-2 font-mono text-xs">{e.target}</td>
                  <td className="px-4 py-2 font-mono text-xs text-slate-500">
                    {e.before_json ?? "—"}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{e.after_json ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
