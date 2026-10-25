import { redirect } from "next/navigation";

import { StaffShell } from "@/components/staff/StaffShell";
import { getAccessToken, getRefreshToken } from "@/lib/auth";
import { getTenantSlug } from "@/lib/tenant";

/** Every staff page requires a session; the proxy refreshes an expired access token. */
export default async function StaffLayout({ children }: { children: React.ReactNode }) {
  if (!(await getTenantSlug())) redirect("/");
  if (!(await getAccessToken()) && !(await getRefreshToken())) redirect("/login");
  return <StaffShell>{children}</StaffShell>;
}
