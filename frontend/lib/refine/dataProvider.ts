"use client";

import type { CrudFilter, DataProvider, HttpError } from "@refinedev/core";

/**
 * Refine ⇄ DRF. Resource names are "<module>/<resource>" and map to
 * /api/proxy/<module>/<resource>/ (the proxy adds auth + branch).
 *
 * DRF conventions handled here:
 *   pagination  ?page=&page_size=        → {count, results}
 *   ordering    ?ordering=field|-field
 *   search      filter {field:"q"}       → ?search=
 *   filters     eq / in                  → ?field=value (in → comma list)
 *   errors      400 {field:[msgs]} → form field errors; {detail} → message;
 *               402 → subscription lapsed (global renewal notice)
 */
export const API = "/api/proxy";

export const SUBSCRIPTION_EVENT = "eraj:subscription-inactive";

const url = (resource: string, id?: string | number, suffix?: string) =>
  `${API}/${resource.replace(/^\/|\/$/g, "")}/${id !== undefined ? `${id}/` : ""}${suffix ? `${suffix.replace(/^\/|\/$/g, "")}/` : ""}`;

function toQuery(filters: CrudFilter[] | undefined, q: URLSearchParams) {
  for (const f of filters ?? []) {
    if (!("field" in f)) continue;
    if (f.value === undefined || f.value === null || f.value === "") continue;
    if (f.field === "q") q.set("search", String(f.value));
    else if (f.operator === "in" && Array.isArray(f.value)) q.set(f.field, f.value.join(","));
    else if (f.operator === "eq" || f.operator === "contains") q.set(f.field, String(f.value));
  }
}

async function request<T>(input: string, init: RequestInit = {}): Promise<T> {
  // Next.js 308-redirects trailing slashes; the proxy adds the slash DRF needs.
  input = input.replace(/\/+(\?|$)/, "$1");
  const res = await fetch(input, {
    ...init,
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(init.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
  });
  if (res.status === 204) return undefined as T;
  let body: unknown = null;
  const text = await res.text();
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (res.ok) return body as T;

  if (res.status === 401 && typeof window !== "undefined") {
    window.location.href = "/login?e=expired";
  }
  if (res.status === 402 && typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(SUBSCRIPTION_EVENT));
  }
  throw toHttpError(res.status, body);
}

export function toHttpError(status: number, body: unknown): HttpError {
  const err: HttpError = { message: `Request failed (${status}).`, statusCode: status };
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.detail === "string") err.message = b.detail;
    else if (typeof b.error === "string") err.message = b.error === "subscription_inactive"
      ? "This institution's subscription is not active."
      : b.error;
    const fieldErrors: Record<string, string[]> = {};
    for (const [k, v] of Object.entries(b)) {
      if (k === "detail") continue;
      if (Array.isArray(v)) fieldErrors[k] = v.map(String);
      else if (typeof v === "string" && k !== "error") fieldErrors[k] = [v];
    }
    if (Object.keys(fieldErrors).length) {
      err.errors = fieldErrors;
      const nonField = fieldErrors.non_field_errors ?? fieldErrors.branch;
      err.message = nonField?.[0] ?? (status === 400 ? "Please correct the highlighted fields." : err.message);
    }
  } else if (status === 403) {
    err.message = "Your role does not allow this action.";
  }
  if (status === 403 && err.message.startsWith("Request failed")) err.message = "Your role does not allow this action.";
  return err;
}

export const api = {
  get: <T,>(path: string) => request<T>(`${API}/${path.replace(/^\//, "")}`),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(`${API}/${path.replace(/^\//, "")}`, {
      method: "POST",
      body: body instanceof FormData ? body : JSON.stringify(body ?? {}),
    }),
  patch: <T,>(path: string, body: unknown) =>
    request<T>(`${API}/${path.replace(/^\//, "")}`, { method: "PATCH", body: JSON.stringify(body) }),
};

export const dataProvider: DataProvider = {
  getApiUrl: () => API,

  getList: async ({ resource, pagination, sorters, filters, meta }) => {
    const q = new URLSearchParams();
    const mode = pagination?.mode ?? "server";
    if (mode === "server") {
      q.set("page", String(pagination?.currentPage ?? 1));
      q.set("page_size", String(pagination?.pageSize ?? 25));
    } else {
      q.set("page_size", "200");
    }
    if (sorters?.length) q.set("ordering", sorters.map((s) => (s.order === "desc" ? `-${s.field}` : s.field)).join(","));
    toQuery(filters, q);
    for (const [k, v] of Object.entries((meta?.query as Record<string, string>) ?? {})) q.set(k, v);
    const body = await request<{ count: number; results: Record<string, unknown>[] } | Record<string, unknown>[]>(
      `${url(meta?.endpoint ?? resource)}?${q}`,
    );
    if (Array.isArray(body)) return { data: body as never[], total: body.length };
    return { data: body.results as never[], total: body.count };
  },

  getMany: async ({ resource, ids, meta }) => {
    const data = await Promise.all(ids.map((id) => request<Record<string, unknown>>(url(meta?.endpoint ?? resource, id))));
    return { data: data as never[] };
  },

  getOne: async ({ resource, id, meta }) => ({
    data: (await request<Record<string, unknown>>(url(meta?.endpoint ?? resource, id))) as never,
  }),

  create: async ({ resource, variables, meta }) => ({
    data: (await request<Record<string, unknown>>(url(meta?.createEndpoint ?? resource), {
      method: "POST",
      body: variables instanceof FormData ? variables : JSON.stringify(variables),
    })) as never,
  }),

  update: async ({ resource, id, variables, meta }) => ({
    data: (await request<Record<string, unknown>>(url(meta?.endpoint ?? resource, id), {
      method: "PATCH",
      body: JSON.stringify(variables),
    })) as never,
  }),

  deleteOne: async ({ resource, id, meta }) => {
    await request(url(meta?.endpoint ?? resource, id), { method: "DELETE" });
    return { data: { id } as never };
  },

  custom: async ({ url: target, method, payload, query }) => {
    const q = new URLSearchParams((query as Record<string, string>) ?? {});
    const full = `${target.startsWith("/api/") ? target : `${API}/${target.replace(/^\//, "")}`}${q.toString() ? `?${q}` : ""}`;
    return {
      data: (await request(full, {
        method: method.toUpperCase(),
        body: payload === undefined ? undefined : payload instanceof FormData ? payload : JSON.stringify(payload),
      })) as never,
    };
  },
};
