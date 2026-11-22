"use client";

/**
 * Portal calls go through the same-origin proxy like staff screens, naming the child's branch per
 * request (a parent's children can be in two branches). The backend re-checks everything:
 * a child that isn't the caller's is a 404 whatever is sent.
 */
export type Lang = "en" | "hi";
export type T = { en: string; hi: string };
export const t = (en: string, hi: string): T => ({ en, hi });
export const tr = (x: T, lang: Lang) => x[lang] || x.en;

export interface Child { id: number; name: string; admission_no: string; section: string | null; branch: number; branch_name: string; is_self: boolean }
export interface Me { name: string; phone: string; language: Lang; kind: "parent" | "student"; children: Child[] }

export class PortalError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call<R>(path: string, init: RequestInit & { branch?: number } = {}): Promise<R> {
  const { branch, ...rest } = init;
  const res = await fetch(`/api/proxy/portal/${path.replace(/^\//, "")}`, {
    ...rest,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(rest.body && !(rest.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(branch ? { "X-Branch": String(branch) } : {}),
      ...(rest.headers ?? {}),
    },
  });
  if (res.status === 401) {
    window.location.href = "/portal/login?e=expired";
    throw new PortalError(401, "Signed out");
  }
  const text = await res.text();
  let body: unknown = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!res.ok) {
    const b = body as Record<string, unknown> | null;
    const msg = typeof b?.detail === "string" ? b.detail : b ? Object.values(b).flat().join(" ") : `Error ${res.status}`;
    throw new PortalError(res.status, msg);
  }
  return body as R;
}

export const portal = {
  me: () => call<Me>("me"),
  get: <R,>(child: Child, path: string) => call<R>(path ? `children/${child.id}/${path}` : `children/${child.id}`, { branch: child.branch }),
  post: <R,>(child: Child, path: string, body: unknown) =>
    call<R>(`children/${child.id}/${path}`, { method: "POST", branch: child.branch, body: body instanceof FormData ? body : JSON.stringify(body) }),
  /** Same-origin link for PDFs and files; the branch goes as a query parameter the proxy can't add to a plain link. */
  href: (child: Child, path: string) =>
    `/api/proxy/portal/children/${child.id}/${path}${path.includes("?") ? "&" : "?"}_branch=${child.branch}`,
};

export function money(v: string | number | null | undefined) {
  const n = Number(v ?? 0);
  return `₹${n.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
}
