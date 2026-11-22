import { redirect } from "next/navigation";

import { PortalShell } from "@/components/portal/PortalShell";
import { getAccessToken, getRefreshToken } from "@/lib/auth";
import { getTenantSlug } from "@/lib/tenant";

/** Parent / student portal: a phone-first layout, separate from the staff screens (ADR-011). */
export default async function PortalLayout({ children }: { children: React.ReactNode }) {
  if (!(await getTenantSlug())) redirect("/");
  if (!(await getAccessToken()) && !(await getRefreshToken())) redirect("/portal/login");
  return <PortalShell>{children}</PortalShell>;
}
