import { redirect } from "next/navigation";

import { setAccessToken } from "@/lib/auth";
import { getTenantSlug, postToBackend } from "@/lib/tenant";

async function login(formData: FormData) {
  "use server";
  const tenantSlug = getTenantSlug();
  if (!tenantSlug) redirect("/login?e=notenant");

  const res = await postToBackend<{ access: string }>(tenantSlug, "/api/auth/login/", {
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!res.ok) redirect("/login?e=bad");

  setAccessToken(res.data.access);
  redirect("/");
}

export default function LoginPage({
  searchParams,
}: {
  searchParams: { [key: string]: string | string[] | undefined };
}) {
  const tenantSlug = getTenantSlug();
  if (!tenantSlug) {
    return (
      <div className="notice notice--no-tenant">
        Open a tenant subdomain (e.g. <code>abc.localhost:3000</code>) to sign in.
      </div>
    );
  }

  return (
    <form action={login} className="card">
      <h1>Sign in — {tenantSlug}</h1>
      {searchParams.e === "bad" && <p className="notice">Wrong email or password.</p>}
      <label>
        Email
        <input name="email" type="email" required autoComplete="username" />
      </label>
      <label>
        Password
        <input name="password" type="password" required autoComplete="current-password" />
      </label>
      <button type="submit">Sign in</button>
    </form>
  );
}
