import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

import { ACCESS, ACCESS_OPTS, BRANCH, LANG, REFRESH, REFRESH_OPTS } from "@/lib/auth";
import { backend, backendJson } from "@/lib/backend";
import { getTenantSlug } from "@/lib/tenant";

/**
 * Same-origin proxy (ADR-004): browser → /api/proxy/<module>/<resource>/… →
 * tenant backend /api/<module>/<resource>/…
 *
 * - attaches the JWT from the httpOnly cookie (the browser never holds it)
 * - forwards the chosen branch as X-Branch (the backend re-checks it)
 * - on 401, refreshes once with the refresh cookie (rotated) and retries
 *
 * Only paths under /api/ on the backend are reachable; `..` segments are refused.
 */
const FORWARD_REQUEST_HEADERS = ["content-type", "accept"];
const FORWARD_RESPONSE_HEADERS = ["content-type", "content-disposition", "cache-control"];

async function handle(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const tenant = await getTenantSlug();
  if (!tenant) return NextResponse.json({ detail: "No institution for this address." }, { status: 400 });

  // CSRF defence in depth: cookies are SameSite=Lax already; additionally every
  // state-changing request must come from this same origin.
  if (!["GET", "HEAD"].includes(req.method)) {
    const origin = req.headers.get("origin");
    const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
    if (!origin || !host || new URL(origin).host !== host) {
      return NextResponse.json({ detail: "Cross-origin request refused." }, { status: 403 });
    }
  }

  const { path } = await ctx.params;
  if (path.some((p) => p === ".." || p === "." || p.includes("\\"))) {
    return NextResponse.json({ detail: "Bad path." }, { status: 400 });
  }
  const target = `/api/${path.map(encodeURIComponent).join("/")}/${req.nextUrl.search}`;

  const jar = await cookies();
  const branch = jar.get(BRANCH)?.value;
  const lang = jar.get(LANG)?.value ?? "en";
  const body = ["GET", "HEAD"].includes(req.method) ? undefined : Buffer.from(await req.arrayBuffer());

  const headersFor = (token: string | undefined) => {
    const h: Record<string, string> = { "Accept-Language": lang };
    for (const name of FORWARD_REQUEST_HEADERS) {
      const v = req.headers.get(name);
      if (v) h[name] = v;
    }
    if (token) h.Authorization = `Bearer ${token}`;
    if (branch && /^(\d+|all)$/.test(branch)) h["X-Branch"] = branch;
    return h;
  };

  let access = jar.get(ACCESS)?.value;
  let res = await backend(tenant, { method: req.method, path: target, headers: headersFor(access), body });

  let refreshed: { access: string; refresh?: string } | null = null;
  const refresh = jar.get(REFRESH)?.value;
  if (res.status === 401 && refresh) {
    const r = await backendJson<{ access: string; refresh?: string }>(tenant, "POST", "/api/auth/refresh/", { refresh });
    if (r.status === 200 && r.data?.access) {
      refreshed = r.data;
      access = r.data.access;
      res = await backend(tenant, { method: req.method, path: target, headers: headersFor(access), body });
    }
  }

  const out = new NextResponse(res.status === 204 ? null : new Uint8Array(res.body), { status: res.status });
  for (const name of FORWARD_RESPONSE_HEADERS) {
    if (res.headers[name]) out.headers.set(name, res.headers[name]);
  }
  if (refreshed) {
    out.cookies.set(ACCESS, refreshed.access, ACCESS_OPTS);
    if (refreshed.refresh) out.cookies.set(REFRESH, refreshed.refresh, REFRESH_OPTS);
  } else if (res.status === 401) {
    out.cookies.delete(ACCESS);
  }
  return out;
}

export const GET = handle;
export const POST = handle;
export const PUT = handle;
export const PATCH = handle;
export const DELETE = handle;
