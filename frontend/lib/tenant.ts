import { headers } from "next/headers";

/**
 * Reads the tenant slug the middleware resolved for this request.
 * Returns null on the root domain (no tenant context) — callers must
 * handle that case explicitly rather than assuming a tenant always exists.
 */
export function getTenantSlug(): string | null {
  return headers().get("x-tenant-slug");
}

/**
 * Root domain the Django backend is served under. In production this is
 * "eraj.com" (so tenant "abc" backend lives at abc.eraj.com); in local dev
 * it's "localhost:8000" and the tenant is passed via the Host header
 * instead of being part of the URL, since Django's dev server doesn't
 * resolve *.localhost subdomains to itself without /etc/hosts entries.
 */
const BACKEND_ROOT = process.env.ERAJ_BACKEND_ROOT ?? "localhost:8000";
const BACKEND_PROTOCOL = process.env.ERAJ_BACKEND_PROTOCOL ?? "http";
const IS_LOCAL_BACKEND = BACKEND_ROOT.startsWith("localhost");

/**
 * Builds the backend API URL for the given tenant + path, and the extra
 * fetch options needed to reach it (a Host header override for local dev,
 * where every tenant's Django schema is served from the same
 * localhost:8000 and disambiguated by Host header rather than by a real
 * DNS subdomain).
 */
export function backendRequest(tenantSlug: string, path: string): { url: string; init: RequestInit } {
  if (IS_LOCAL_BACKEND) {
    return {
      url: `${BACKEND_PROTOCOL}://${BACKEND_ROOT}${path}`,
      init: { headers: { Host: `${tenantSlug}.localhost` } },
    };
  }
  return {
    url: `${BACKEND_PROTOCOL}://${tenantSlug}.${BACKEND_ROOT}${path}`,
    init: {},
  };
}

export type BackendFetchResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string };

/**
 * Local-dev only: Node's built-in `fetch` (undici) refuses to let you set
 * a custom `Host` header (it's on the forbidden-header list per the Fetch
 * spec), which is exactly what local dev needs since `*.localhost`
 * subdomains often don't resolve via DNS in every environment (sandboxes,
 * some CI runners). Node's core `http` module has no such restriction, so
 * we drop down to it for this one case. Production never takes this path —
 * it uses real subdomains via plain `fetch`, see fetchFromBackend below.
 */
function fetchViaHostHeaderOverride(url: string, hostHeader: string): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const http = require("node:http") as typeof import("node:http");
    const parsed = new URL(url);
    const req = http.request(
      {
        hostname: parsed.hostname,
        port: parsed.port,
        path: parsed.pathname + parsed.search,
        method: "GET",
        headers: { Host: hostHeader },
      },
      (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
      }
    );
    req.on("error", reject);
    req.end();
  });
}

/**
 * Fetches from the tenant's Django backend and surfaces the two states
 * every module page needs to handle explicitly: subscription inactive
 * (402, see apps/core/middleware.py) and module not licensed (403) —
 * these are not generic errors, they're the whole point of the platform's
 * access model, so pages should show a specific message for each rather
 * than a blanket "something went wrong".
 */
export async function fetchFromBackend<T>(tenantSlug: string, path: string): Promise<BackendFetchResult<T>> {
  let status: number;
  let bodyText: string;

  try {
    if (IS_LOCAL_BACKEND) {
      const { url } = backendRequest(tenantSlug, path);
      const result = await fetchViaHostHeaderOverride(url, `${tenantSlug}.localhost`);
      status = result.status;
      bodyText = result.body;
    } else {
      const { url, init } = backendRequest(tenantSlug, path);
      const response = await fetch(url, { ...init, cache: "no-store" });
      status = response.status;
      bodyText = await response.text();
    }
  } catch (err) {
    return { ok: false, status: 0, error: "Could not reach the Eraj backend." };
  }

  if (status === 402) {
    return { ok: false, status: 402, error: "This institution's subscription is not active." };
  }
  if (status === 403) {
    return { ok: false, status: 403, error: "This module is not included in the current plan." };
  }
  if (status < 200 || status >= 300) {
    return { ok: false, status, error: `Backend returned ${status}.` };
  }

  const data = JSON.parse(bodyText) as T;
  return { ok: true, data };
}
