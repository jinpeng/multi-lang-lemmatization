import { connection } from "next/server";
import { api } from "@/lib/server";
import { getAdminToken } from "@/lib/session";
import { Badge } from "@/components/Badge";
import { rotateKey, revokeKey } from "@/app/keys/actions";
import { CsrfField } from "@/components/CsrfField";
import type { KeyRecord } from "@/lib/types";

export async function KeysTable() {
  await connection();
  const token = await getAdminToken();
  if (!token) return null; // middleware already redirects; this satisfies types
  const keys: KeyRecord[] = await api().listKeys(token);

  if (keys.length === 0) {
    return <p className="mt-8 text-sm text-slate-500">No keys yet.</p>;
  }

  return (
    <div className="mt-8 overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Name</th>
            <th className="px-4 py-2">key_id</th>
            <th className="px-4 py-2">Fingerprint</th>
            <th className="px-4 py-2">Langs</th>
            <th className="px-4 py-2">HMAC</th>
            <th className="px-4 py-2">rpm</th>
            <th className="px-4 py-2">Last used</th>
            <th className="px-4 py-2">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {keys.map((k) => (
            <tr key={k.key_id} className={k.revoked_at ? "bg-slate-50 text-slate-400" : ""}>
              <td className="px-4 py-2 font-medium">{k.name}</td>
              <td className="px-4 py-2 font-mono text-xs">{k.key_id}</td>
              <td className="px-4 py-2 font-mono text-xs">{k.secret_fingerprint}</td>
              <td className="px-4 py-2 text-xs">
                {k.langs.length === 0 ? <em>all</em> : k.langs.join(", ")}
              </td>
              <td className="px-4 py-2">
                <Badge tone={k.allow_hmac ? "ok" : "muted"}>{k.allow_hmac ? "yes" : "no"}</Badge>
              </td>
              <td className="px-4 py-2 text-xs">{k.rate_limit_rpm}</td>
              <td className="px-4 py-2 text-xs">{k.last_used_at ?? "never"}</td>
              <td className="px-4 py-2">
                {k.revoked_at ? (
                  <Badge tone="warn">revoked</Badge>
                ) : (
                  <div className="flex gap-3">
                    <form action={rotateKey}>
                      <CsrfField />
                      <input type="hidden" name="key_id" value={k.key_id} />
                      <button className="text-xs text-slate-600 underline">rotate</button>
                    </form>
                    <form action={revokeKey}>
                      <CsrfField />
                      <input type="hidden" name="key_id" value={k.key_id} />
                      <button className="text-xs text-rose-600 underline">revoke</button>
                    </form>
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
