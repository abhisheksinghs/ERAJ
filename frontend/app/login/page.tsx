import { redirect } from "next/navigation";

import { setSession } from "@/lib/auth";
import { backendJson } from "@/lib/backend";
import { getTenantSlug } from "@/lib/tenant";

async function login(formData: FormData) {
  "use server";
  const tenantSlug = await getTenantSlug();
  if (!tenantSlug) redirect("/login?e=notenant");

  const res = await backendJson<{ access: string; refresh: string }>(tenantSlug, "POST", "/api/auth/login/", {
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (res.status === 429) redirect("/login?e=throttled");
  if (res.status !== 200 || !res.data) redirect("/login?e=bad");

  await setSession(res.data.access, res.data.refresh);
  redirect("/dashboard");
}

const MESSAGES: Record<string, string> = {
  bad: "Wrong email or password. / ईमेल या पासवर्ड गलत है।",
  expired: "Your session ended. Please sign in again. / सत्र समाप्त हुआ, फिर से साइन इन करें।",
  throttled: "Too many attempts. Wait a minute and try again. / बहुत अधिक प्रयास, एक मिनट बाद प्रयास करें।",
  notenant: "Open your institution's address to sign in.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const sp = await searchParams;
  const tenantSlug = await getTenantSlug();
  const message = typeof sp.e === "string" ? MESSAGES[sp.e] : undefined;

  return (
    <div className="auth-wrap">
      <form action={login} className="auth-card">
        <span className="auth-brand">ERAJ</span>
        <h1>Sign in</h1>
        <p className="sub">साइन इन करें{tenantSlug ? ` · ${tenantSlug}` : ""}</p>
        {message && <p className="notice">{message}</p>}
        <label>
          Email / ईमेल
          <input name="email" type="email" required autoComplete="username" />
        </label>
        <label>
          Password / पासवर्ड
          <input name="password" type="password" required autoComplete="current-password" />
        </label>
        <button type="submit" disabled={!tenantSlug}>
          Sign in
        </button>
      </form>
    </div>
  );
}
