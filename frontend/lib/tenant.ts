import { headers } from "next/headers";

/** Tenant slug the proxy (proxy.ts) resolved for this request (null on the root domain). */
export async function getTenantSlug(): Promise<string | null> {
  return (await headers()).get("x-tenant-slug");
}
