import type { LemmatizeResponse } from "@/lib/types";

export function ResultTable({ response }: { response: LemmatizeResponse }) {
  const hasReading = response.capabilities.reading;
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full text-left text-sm">
        <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-4 py-2">Surface</th>
            <th className="px-4 py-2">Lemma</th>
            <th className="px-4 py-2">POS</th>
            {hasReading && <th className="px-4 py-2">Reading</th>}
            <th className="px-4 py-2">Prov</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {response.items.map((item, i) => (
            <tr
              key={`${item.surface}-${i}`}
              className={item.prov === "identity" ? "bg-amber-50/50" : ""}
            >
              <td className="px-4 py-2 font-mono">{item.surface}</td>
              <td className="px-4 py-2 font-mono font-medium">{item.lemma}</td>
              <td className="px-4 py-2 text-slate-600">
                {item.pos ?? <span className="text-slate-400">null</span>}
              </td>
              {hasReading && <td className="px-4 py-2 text-slate-600">{item.reading ?? "—"}</td>}
              <td className="px-4 py-2">
                <span
                  className={
                    item.prov === "identity"
                      ? "rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800"
                      : "rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800"
                  }
                >
                  {item.prov}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
