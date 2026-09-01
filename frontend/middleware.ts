import { NextRequest, NextResponse } from "next/server";

/**
 * Tenant resolution for the whole frontend.
 *
 * Mirrors the backend's model exactly (see /docs/ARCHITECTURE.md in the
 * repo root): a TENANT is identified by subdomain (abc.eraj.com,
 * xyz.eraj.com); a PRODUCT/module is identified by path (/library,
 * /hostel, ...) within that tenant. There is no product-level subdomain —
 * one Next.js app serves every module for a given tenant, exactly as one
 * Django app serves every module for a given tenant schema.
 *
 * This middleware's only job: figure out which tenant a request is for,
 * and make that available to every Server Component and API route via a
 * request header (`x-tenant-slug`). It does NOT do auth or module
 * permission checks — those stay server-side, enforced by the Django
 * backend's SubscriptionEnforcementMiddleware. Trusting a client-supplied
 * value for access control would defeat the point of doing it in Django.
 */

// Root domains this app is served under. Requests to these exact hosts
// (no subdomain) are treated as "no tenant" (e.g. the marketing/login page,
// or local dev without a subdomain).
const ROOT_HOSTS = new Set([
  "eraj.com",
  "www.eraj.com",
  "localhost:3000",
  "localhost",
]);

export function resolveTenantSlug(host: string | null): string | null {
  if (!host) return null;
  const hostname = host.split(":")[0]; // strip port for comparison
  const hostWithPort = host;

  if (ROOT_HOSTS.has(hostname) || ROOT_HOSTS.has(hostWithPort)) {
    return null;
  }

  // Local dev: abc.localhost:3000 -> "abc"
  if (hostname.endsWith(".localhost")) {
    return hostname.split(".")[0];
  }

  // Production: abc.eraj.com -> "abc"
  const parts = hostname.split(".");
  if (parts.length >= 3) {
    return parts[0];
  }

  return null;
}

export function middleware(request: NextRequest) {
  const host = request.headers.get("host");
  const tenantSlug = resolveTenantSlug(host);

  const requestHeaders = new Headers(request.headers);
  if (tenantSlug) {
    requestHeaders.set("x-tenant-slug", tenantSlug);
  } else {
    requestHeaders.delete("x-tenant-slug");
  }

  return NextResponse.next({
    request: { headers: requestHeaders },
  });
}

export const config = {
  // Run on every path except static assets and Next internals.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
