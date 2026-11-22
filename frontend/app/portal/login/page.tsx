import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { setSession } from "@/lib/auth";
import { backendJson } from "@/lib/backend";
import { getTenantSlug } from "@/lib/tenant";

/**
 * Parent login with the registered mobile number and a one-time code (ADR-011). The number waits
 * in a short-lived httpOnly cookie between the two steps, never in the address bar.
 */
const PHONE = "eraj_otp_phone";
const DEMO = "eraj_otp_demo"; // staging only: the backend returns the code when no real channel exists
const STEP_OPTS = { httpOnly: true, sameSite: "lax" as const, path: "/portal", maxAge: 60 * 10, secure: process.env.NODE_ENV === "production" };

async function askCode(formData: FormData) {
  "use server";
  const tenant = await getTenantSlug();
  if (!tenant) redirect("/portal/login?e=notenant");
  const phone = String(formData.get("phone") ?? "").replace(/\D/g, "").slice(-10);
  if (phone.length !== 10) redirect("/portal/login?e=phone");
  const res = await backendJson<{ detail: string; demo_code?: string }>(tenant, "POST", "/api/portal/otp/request/", { phone });
  if (res.status === 429) redirect("/portal/login?e=throttled");
  const jar = await cookies();
  jar.set(PHONE, phone, STEP_OPTS);
  if (res.data?.demo_code) jar.set(DEMO, res.data.demo_code, { ...STEP_OPTS, maxAge: 60 * 5 });
  else jar.delete(DEMO);
  redirect("/portal/login?step=code");
}

async function checkCode(formData: FormData) {
  "use server";
  const tenant = await getTenantSlug();
  if (!tenant) redirect("/portal/login?e=notenant");
  const jar = await cookies();
  const phone = jar.get(PHONE)?.value;
  if (!phone) redirect("/portal/login?e=again");
  const res = await backendJson<{ access: string; refresh: string }>(tenant, "POST", "/api/portal/otp/verify/", {
    phone, code: String(formData.get("code") ?? "").trim(),
  });
  if (res.status === 429) redirect("/portal/login?step=code&e=throttled");
  if (res.status !== 200 || !res.data) redirect("/portal/login?step=code&e=bad");
  jar.delete(PHONE);
  jar.delete(DEMO);
  await setSession(res.data.access, res.data.refresh);
  redirect("/portal");
}

const MESSAGES: Record<string, string> = {
  bad: "The code is wrong or has expired. / कोड गलत है या समाप्त हो गया।",
  phone: "Enter your 10-digit mobile number. / 10 अंकों का मोबाइल नंबर लिखें।",
  again: "Start again with your mobile number. / मोबाइल नंबर से फिर शुरू करें।",
  expired: "Your session ended. Please sign in again. / सत्र समाप्त, फिर से साइन इन करें।",
  throttled: "Too many attempts. Wait a minute. / बहुत अधिक प्रयास, एक मिनट रुकें।",
  notenant: "Open your school's address to sign in.",
};

export default async function PortalLogin({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const tenant = await getTenantSlug();
  const jar = await cookies();
  const step = sp.step === "code" && jar.get(PHONE) ? "code" : "phone";
  const phone = jar.get(PHONE)?.value ?? "";
  const demo = jar.get(DEMO)?.value;
  const message = typeof sp.e === "string" ? MESSAGES[sp.e] : undefined;

  return (
    <div className="auth-wrap">
      {step === "phone" ? (
        <form action={askCode} className="auth-card">
          <span className="auth-brand">ERAJ</span>
          <h1>Parent sign in</h1>
          <p className="sub">अभिभावक साइन इन{tenant ? ` · ${tenant}` : ""}</p>
          {message && <p className="notice">{message}</p>}
          <label>
            Registered mobile number / पंजीकृत मोबाइल नंबर
            <input name="phone" type="tel" inputMode="numeric" autoComplete="tel" required pattern="[0-9 +]{10,15}" />
          </label>
          <button type="submit" disabled={!tenant}>Send code / कोड भेजें</button>
          <p className="sub" style={{ marginTop: 12 }}><a href="/login">Students and staff: sign in with email / छात्र एवं कर्मचारी: ईमेल से</a></p>
        </form>
      ) : (
        <form action={checkCode} className="auth-card">
          <span className="auth-brand">ERAJ</span>
          <h1>Enter the code</h1>
          <p className="sub">If ******{phone.slice(-4)} is registered with the school, a 6-digit code was sent by SMS or WhatsApp. / कोड लिखें</p>
          {message && <p className="notice">{message}</p>}
          {demo && <p className="notice" data-testid="demo-code">Test system — no SMS is sent. Code: <b>{demo}</b></p>}
          <label>
            6-digit code / 6 अंकों का कोड
            <input name="code" inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6}" maxLength={6} />
          </label>
          <button type="submit">Sign in / साइन इन</button>
          <p className="sub" style={{ marginTop: 12 }}><a href="/portal/login">Change number / नंबर बदलें</a></p>
        </form>
      )}
    </div>
  );
}
