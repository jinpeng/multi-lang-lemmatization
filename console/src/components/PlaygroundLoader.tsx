import { api } from "@/lib/server";
import { Playground } from "@/components/Playground";
import type { LanguageEntry } from "@/lib/types";

export async function PlaygroundLoader() {
  let languages: LanguageEntry[] = [];
  let loadError: string | undefined;
  try {
    languages = await api().languages();
  } catch {
    loadError = "The API is unreachable. Check that the api service is running.";
  }

  if (loadError) {
    return (
      <div className="mt-6 rounded-lg border border-rose-300 bg-rose-50 p-4 text-sm text-rose-800">
        {loadError}
      </div>
    );
  }
  return <Playground languages={languages} />;
}
