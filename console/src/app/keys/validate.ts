export const KNOWN_LANGS = ["en", "de", "fr", "es", "ru", "ja", "ko"] as const;

export function validateKeyName(raw: string): string {
  const name = raw.trim();
  if (!name) throw new Error("Key name is required");
  if (name.length > 100) throw new Error("Key name must be 100 characters or fewer");
  return name;
}

export function parseLangs(raw: string): string[] {
  const langs = raw.split(",").map((x) => x.trim()).filter(Boolean);
  const unknown = langs.filter((l) => !(KNOWN_LANGS as readonly string[]).includes(l));
  if (unknown.length > 0) {
    throw new Error(`Unknown language code(s): ${unknown.join(", ")}`);
  }
  return langs;
}
