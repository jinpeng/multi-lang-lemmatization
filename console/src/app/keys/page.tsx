import { Suspense } from "react";
import { KeysTable } from "@/components/KeysTable";
import { KeyForm } from "@/app/keys/KeyForm";
import { Skeleton } from "@/components/Skeleton";

export default function KeysPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">API keys</h1>
      <p className="mt-1 text-sm text-slate-600">
        Key ids are identifiers; the secret is the credential. Both are needed — a key id alone
        authenticates nothing.
      </p>
      <KeyForm />
      <Suspense fallback={<div className="mt-8"><Skeleton lines={5} /></div>}>
        <KeysTable />
      </Suspense>
    </main>
  );
}
