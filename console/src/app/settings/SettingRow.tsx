"use client";

import { updateSetting } from "@/app/settings/actions";
import { Badge } from "@/components/Badge";
import { CsrfField } from "@/components/CsrfField";
import type { SettingRow as Row } from "@/lib/types";

function asInputValue(row: Row): string {
  if (row.kind === "lang_set") return (row.value as string[]).join(",");
  return String(row.value);
}

export function SettingRow({ row }: { row: Row }) {
  return (
    <tr>
      <td className="px-4 py-2 font-mono text-xs">{row.key}</td>
      <td className="px-4 py-2">
        <form action={updateSetting} className="flex items-center gap-2">
          <CsrfField />
          <input type="hidden" name="key" value={row.key} />
          <input type="hidden" name="kind" value={row.kind} />

          {row.kind === "bool" ? (
            <select
              name="value"
              defaultValue={String(row.value)}
              className="rounded border border-slate-300 p-1 text-xs"
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : row.kind === "enum" ? (
            <select
              name="value"
              defaultValue={String(row.value)}
              className="rounded border border-slate-300 p-1 text-xs"
            >
              {row.values.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          ) : (
            <input
              name="value"
              defaultValue={asInputValue(row)}
              className="w-48 rounded border border-slate-300 p-1 font-mono text-xs"
            />
          )}

          <button className="rounded bg-slate-900 px-2 py-1 text-xs text-white">Save</button>
        </form>
      </td>
      <td className="px-4 py-2 font-mono text-xs text-slate-500">
        {row.kind === "lang_set" ? (row.default as string[]).join(",") : String(row.default)}
      </td>
      <td className="px-4 py-2">
        {row.hot ? <Badge tone="ok">live</Badge> : <Badge tone="warn">restart</Badge>}
        {row.overridden && <Badge tone="muted">changed</Badge>}
      </td>
      <td className="px-4 py-2 text-xs text-slate-500">
        {row.min !== null && row.max !== null ? `${row.min}–${row.max}` : ""}
      </td>
    </tr>
  );
}
