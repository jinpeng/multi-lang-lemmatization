import { connection } from "next/server";
import { api } from "@/lib/server";
import { getAdminToken } from "@/lib/session";
import { Badge } from "@/components/Badge";
import { SettingRow } from "@/app/settings/SettingRow";
import type { SettingRow as Row } from "@/lib/types";

type Diagnostics = {
  backends: Record<
    string,
    { status: string; backend: string | null; version: string | null; reason: string | null }
  >;
  master_key: string;
  service_token: string;
  db_url_kind: string;
};

export async function SettingsBody() {
  await connection();
  const token = await getAdminToken();
  if (!token) return null;

  const [settings, diagnostics] = await Promise.all([
    api().readSettings(token),
    api().diagnostics(token) as Promise<Diagnostics>,
  ]);

  return (
    <div className="space-y-12">
      <section>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">Diagnostics</h1>
          <Badge tone="muted">read-only</Badge>
        </div>
        <p className="mt-1 text-sm text-slate-600">
          Deployment facts. These cannot be changed here — doing so from a web UI is how a console
          makes its own service unreachable.
        </p>

        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          {(
            [
              ["Master key", diagnostics.master_key],
              ["Service token", diagnostics.service_token],
              ["Storage", diagnostics.db_url_kind],
            ] as const
          ).map(([label, value]) => (
            <div key={label} className="rounded-xl border border-slate-200 p-4">
              <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
              <div className="mt-1 font-mono text-sm">{value}</div>
            </div>
          ))}
        </div>

        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Lang</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Backend</th>
                <th className="px-4 py-2">Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {Object.entries(diagnostics.backends).map(([lang, info]) => (
                <tr key={lang}>
                  <td className="px-4 py-2 font-mono">{lang}</td>
                  <td className="px-4 py-2">
                    <Badge tone={info.status === "ok" ? "ok" : "warn"}>{info.status}</Badge>
                  </td>
                  <td className="px-4 py-2 text-slate-600">
                    {info.backend ? `${info.backend} ${info.version}` : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-rose-700">{info.reason ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-2xl font-semibold tracking-tight">Settings</h2>
        <p className="mt-1 text-sm text-slate-600">
          Only whitelisted keys are editable. Entries marked <Badge tone="warn">restart</Badge>{" "}
          take effect after the API restarts.
        </p>

        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2">Key</th>
                <th className="px-4 py-2">Value</th>
                <th className="px-4 py-2">Default</th>
                <th className="px-4 py-2">Applied</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(settings as Row[]).map((row) => (
                <SettingRow key={row.key} row={row} />
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
