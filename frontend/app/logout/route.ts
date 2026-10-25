import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ACCESS, BRANCH, REFRESH } from "@/lib/auth";
import { backendJson } from "@/lib/backend";
import { getTenantSlug } from "@/lib/tenant";

/** Blacklists the refresh token on the backend, then clears the session cookies. */
export async function POST(request: Request) {
  const jar = await cookies();
  const tenant = await getTenantSlug();
  const access = jar.get(ACCESS)?.value;
  const refresh = jar.get(REFRESH)?.value;
  if (tenant && refresh) {
    await backendJson(tenant, "POST", "/api/auth/logout/", { refresh }, access).catch(() => undefined);
  }
  const res = NextResponse.redirect(new URL("/login", request.url), { status: 303 });
  for (const name of [ACCESS, REFRESH, BRANCH]) res.cookies.delete(name);
  return res;
}
