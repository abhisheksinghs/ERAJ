import { headers } from "next/headers";

/** Tenant slug the middleware resolved for this request (null on the root domain). */
export function getTenantSlug(): string | null {
  return headers().get("x-tenant-slug");
}

const BACKEND_ROOT = process.env.ERAJ_BACKEND_ROOT ?? "localhost:8000";
const BACKEND_PROTOCOL = process.env.ERAJ_BACKEND_PROTOCOL ?? "http";
const IS_LOCAL_BACKEND = BACKEND_ROOT.startsWith("localhost");

type Raw = { status: number; body: string };

interface CallOptions {
  method: "GET" | "POST";
  token?: string | null;
  json?: unknown;
}

/**
 * Local dev only: Node's `fetch` (undici) forbids overriding the `Host`
 * header, which is how a single localhost:8000 Django serves every tenant
 * schema in dev. Node's core `http` has no such restriction. Production uses
 * real subdomains via plain `fetch` (see `call` below).
 */
function callViaHttp(url: string, hostHeader: string, opts: CallOptions): Promise<Raw> {
  return new Promise((resolve, reject) => {
    const http = require("node:http") as typeof import("node:http");
    const u = new URL(url);
    const payload = opts.json === undefined ? undefined : JSON.stringify(opts.json);
    const req = http.request(
      {
        hostname: u.hostname,
        port: u.port,
        path: u.pathname + u.search,
        method: opts.method,
        headers: {
          Host: hostHeader,
          ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
          ...(payload
            ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) }
            : {}),
        },
      },
      (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => resolve({ status: res.statusCode ?? 0, body }));
      },
    );
    req.on("error", reject);
    if (payload) req.write(payload);
    req.end();
  });
}

async function call(tenantSlug: string, path: string, opts: CallOptions): Promise<Raw> {
  if (IS_LOCAL_BACKEND) {
    return callViaHttp(`${BACKEND_PROTOCOL}://${BACKEND_ROOT}${path}`, `${tenantSlug}.localhost`, opts);
  }
  const res = await fetch(`${BACKEND_PROTOCOL}://${tenantSlug}.${BACKEND_ROOT}${path}`, {
    method: opts.method,
    cache: "no-store",
    headers: {
      ...(opts.token ? { Authorization: `Bearer ${opts.token}` } : {}),
      ...(opts.json !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.json !== undefined ? JSON.stringify(opts.json) : undefined,
  });
  return { status: res.status, body: await res.text() };
}

export type BackendResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string };

function interpret<T>(r: Raw): BackendResult<T> {
  if (r.status === 401) return { ok: false, status: 401, error: "You are not signed in." };
  if (r.status === 402)
    return { ok: false, status: 402, error: "This institution's subscription is not active." };
  if (r.status === 403)
    return { ok: false, status: 403, error: "This module is not included in the current plan." };
  if (r.status < 200 || r.status >= 300)
    return { ok: false, status: r.status, error: `Backend returned ${r.status}.` };

  let parsed: unknown;
  try {
    parsed = r.body ? JSON.parse(r.body) : null;
  } catch {
    return { ok: false, status: r.status, error: "Unexpected response from the backend." };
  }
  // Unwrap DRF pagination. ponytail: first page only; pass ?page= for the rest.
  if (parsed && typeof parsed === "object" && "results" in parsed && "count" in parsed) {
    return { ok: true, data: (parsed as { results: T }).results };
  }
  return { ok: true, data: parsed as T };
}

export async function fetchFromBackend<T>(
  tenantSlug: string,
  path: string,
  token?: string | null,
): Promise<BackendResult<T>> {
  try {
    return interpret<T>(await call(tenantSlug, path, { method: "GET", token }));
  } catch {
    return { ok: false, status: 0, error: "Could not reach the Eraj backend." };
  }
}

export async function postToBackend<T>(
  tenantSlug: string,
  path: string,
  json: unknown,
  token?: string | null,
): Promise<BackendResult<T>> {
  try {
    return interpret<T>(await call(tenantSlug, path, { method: "POST", token, json }));
  } catch {
    return { ok: false, status: 0, error: "Could not reach the Eraj backend." };
  }
}
