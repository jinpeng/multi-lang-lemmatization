import Link from "next/link";
import { Suspense } from "react";
import { logout } from "@/app/actions/session";
import { getAdminToken } from "@/lib/session";

/**
 * Session-aware half of the nav. `cookies()` is runtime data, so with
 * cacheComponents enabled it must sit inside a Suspense boundary or every
 * statically prerendered page that shares this layout (including /_not-found)
 * fails the build.
 */
async function NavSession() {
  if (!(await getAdminToken())) {
    return (
      <Link href="/login" className="text-slate-600 hover:text-slate-900">
        Sign in
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-6">
      <Link href="/keys" className="text-slate-600 hover:text-slate-900">
        Keys
      </Link>
      <Link href="/settings" className="text-slate-600 hover:text-slate-900">
        Settings
      </Link>
      <Link href="/logs" className="text-slate-600 hover:text-slate-900">
        Logs
      </Link>
      <form action={logout}>
        <button className="text-slate-600 hover:text-slate-900">Sign out</button>
      </form>
    </div>
  );
}

export function Nav() {
  return (
    <header className="border-b border-slate-200">
      <nav className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3 text-sm">
        <Link href="/" className="font-semibold tracking-tight">
          Lemma
        </Link>
        <Link href="/" className="text-slate-600 hover:text-slate-900">
          Playground
        </Link>
        <Link href="/languages" className="text-slate-600 hover:text-slate-900">
          Languages
        </Link>
        <span className="ml-auto">
          <Suspense fallback={<span className="text-slate-400">…</span>}>
            <NavSession />
          </Suspense>
        </span>
      </nav>
    </header>
  );
}
