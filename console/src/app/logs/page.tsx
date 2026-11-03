import { Suspense } from "react";
import { LogsBody } from "@/components/LogsBody";
import { Skeleton } from "@/components/Skeleton";

export default function LogsPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <Suspense fallback={<Skeleton lines={10} />}>
        <LogsBody />
      </Suspense>
    </main>
  );
}
