import { Suspense } from "react";
import { LanguagesTable } from "@/components/LanguagesTable";
import { Skeleton } from "@/components/Skeleton";

export default function LanguagesPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Language capabilities</h1>
      <p className="mt-2 max-w-3xl text-sm text-slate-600">
        <strong>pos</strong> means the backend emits a tag. <strong>pos_accepted</strong> means it
        uses one you send. English accepts a tag but emits none; Russian emits one but ignores
        yours. Modelling these as one flag would hide that difference.
      </p>
      <Suspense fallback={<div className="mt-6"><Skeleton lines={8} /></div>}>
        <LanguagesTable />
      </Suspense>
    </main>
  );
}
