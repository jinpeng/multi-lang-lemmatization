"use client";

import { CopyButton } from "@/components/CopyButton";

export function NewKeySecret({
  keyId,
  secret,
  fingerprint,
}: {
  keyId: string;
  secret: string;
  fingerprint: string;
}) {
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-5">
      <h2 className="text-sm font-semibold text-amber-900">
        Copy this secret now — it will not be shown again
      </h2>
      <p className="mt-1 text-xs text-amber-800">
        Only an encrypted copy is stored. If you lose it you must rotate the key.
      </p>
      <dl className="mt-4 space-y-2 text-sm">
        <div className="flex items-baseline gap-3">
          <dt className="w-24 shrink-0 text-xs uppercase tracking-wide text-amber-700">key_id</dt>
          <dd className="font-mono">{keyId}</dd>
        </div>
        <div className="flex items-baseline gap-3">
          <dt className="w-24 shrink-0 text-xs uppercase tracking-wide text-amber-700">secret</dt>
          <dd className="break-all font-mono">{secret}</dd>
        </div>
        <div className="flex items-baseline gap-3">
          <dt className="w-24 shrink-0 text-xs uppercase tracking-wide text-amber-700">
            fingerprint
          </dt>
          <dd className="font-mono text-slate-600">{fingerprint}</dd>
        </div>
      </dl>
      <div className="mt-4 flex gap-2">
        <CopyButton text={`${keyId}.${secret}`} />
        <CopyButton text={secret} />
      </div>
    </div>
  );
}
