import { redirect } from "next/navigation";

import { getAccessToken, getRefreshToken } from "@/lib/auth";
import { getTenantSlug } from "@/lib/tenant";

export default async function Home() {
  if (!(await getTenantSlug())) {
    return (
      <div className="auth-wrap">
        <div className="auth-card">
          <span className="auth-brand">ERAJ</span>
          <p>
            Open your institution&apos;s address (for example <code>abc.eraj.com</code>; locally{" "}
            <code>abc.localhost:3000</code>) to sign in.
          </p>
        </div>
      </div>
    );
  }
  const signedIn = (await getAccessToken()) !== null || (await getRefreshToken()) !== null;
  redirect(signedIn ? "/dashboard" : "/login");
}
