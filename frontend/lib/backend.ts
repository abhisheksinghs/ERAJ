/**
 * Server-side HTTP client for the Django backend (raw bytes in, raw bytes out),
 * used by the /api/proxy route. Tenant = subdomain, exactly as in production.
 */
const BACKEND_ROOT = process.env.ERAJ_BACKEND_ROOT ?? "localhost:8000";
const BACKEND_PROTOCOL = process.env.ERAJ_BACKEND_PROTOCOL ?? "http";
const IS_LOCAL_BACKEND = BACKEND_ROOT.startsWith("localhost") || BACKEND_ROOT.startsWith("127.0.0.1");

export interface BackendRequest {
  method: string;
  path: string; // must start with /api/
  headers?: Record<string, string>;
  body?: Buffer;
}

export interface BackendResponse {
  status: number;
  headers: Record<string, string>;
  body: Buffer;
}

/**
 * Local dev only: Node's `fetch` (undici) forbids overriding `Host`, which is
 * how one localhost:8000 Django serves every tenant schema in dev. Node's core
 * `http` has no such restriction.
 */
function viaHttp(tenantSlug: string, req: BackendRequest): Promise<BackendResponse> {
  return new Promise((resolve, reject) => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const http = require("node:http") as typeof import("node:http");
    const u = new URL(`${BACKEND_PROTOCOL}://${BACKEND_ROOT}${req.path}`);
    const out = http.request(
      {
        hostname: u.hostname,
        port: u.port,
        path: u.pathname + u.search,
        method: req.method,
        headers: {
          ...req.headers,
          Host: `${tenantSlug}.localhost`,
          ...(req.body ? { "Content-Length": String(req.body.length) } : {}),
        },
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c: Buffer) => chunks.push(c));
        res.on("end", () => {
          const headers: Record<string, string> = {};
          for (const [k, v] of Object.entries(res.headers)) if (typeof v === "string") headers[k] = v;
          resolve({ status: res.statusCode ?? 502, headers, body: Buffer.concat(chunks) });
        });
      },
    );
    out.on("error", reject);
    if (req.body) out.write(req.body);
    out.end();
  });
}

export async function backend(tenantSlug: string, req: BackendRequest): Promise<BackendResponse> {
  if (IS_LOCAL_BACKEND) return viaHttp(tenantSlug, req);
  const res = await fetch(`${BACKEND_PROTOCOL}://${tenantSlug}.${BACKEND_ROOT}${req.path}`, {
    method: req.method,
    headers: req.headers,
    body: req.body ? new Uint8Array(req.body) : undefined,
    cache: "no-store",
    redirect: "manual",
  });
  const headers: Record<string, string> = {};
  res.headers.forEach((v, k) => (headers[k] = v));
  return { status: res.status, headers, body: Buffer.from(await res.arrayBuffer()) };
}

export async function backendJson<T>(
  tenantSlug: string,
  method: string,
  path: string,
  json?: unknown,
  token?: string | null,
): Promise<{ status: number; data: T | null }> {
  const res = await backend(tenantSlug, {
    method,
    path,
    headers: {
      Accept: "application/json",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: json !== undefined ? Buffer.from(JSON.stringify(json)) : undefined,
  });
  let data: T | null = null;
  try {
    data = res.body.length ? (JSON.parse(res.body.toString("utf8")) as T) : null;
  } catch {
    data = null;
  }
  return { status: res.status, data };
}
