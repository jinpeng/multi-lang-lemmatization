import { Suspense } from "react";
import { PlaygroundLoader } from "@/components/PlaygroundLoader";
import { Skeleton } from "@/components/Skeleton";

// Next 16 with cacheComponents requires dynamic reads to stream inside a
// Suspense boundary rather than opting the whole route out of prerendering.
export default function HomePage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Lemmatization Playground</h1>
      <p className="mt-2 text-sm text-slate-600">
        Runs against the live API with a server-side demo key, so nothing is exposed to your
        browser. The equivalent <code>curl</code> is shown with each result.
      </p>
      <Suspense fallback={<div className="mt-6"><Skeleton lines={6} /></div>}>
        <PlaygroundLoader />
      </Suspense>
    </main>
  );
}
