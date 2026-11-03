import { Suspense } from "react";
import { SettingsBody } from "@/components/SettingsBody";
import { Skeleton } from "@/components/Skeleton";

export default function SettingsPage() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <Suspense fallback={<Skeleton lines={10} />}>
        <SettingsBody />
      </Suspense>
    </main>
  );
}
