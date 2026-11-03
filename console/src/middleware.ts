import { NextResponse, type NextRequest } from "next/server";

const PROTECTED = ["/keys", "/settings", "/logs"];
export const ADMIN_COOKIE = "lemma_admin";

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function redirectTarget(pathname: string): string {
  return `/login?next=${encodeURIComponent(pathname)}`;
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!isProtectedPath(pathname)) return NextResponse.next();

  if (!request.cookies.get(ADMIN_COOKIE)?.value) {
    return NextResponse.redirect(new URL(redirectTarget(pathname), request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/keys/:path*", "/settings/:path*", "/logs/:path*"] };
