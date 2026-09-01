import Link from "next/link";
import { getTenantSlug } from "@/lib/tenant";

export default function HomePage() {
  const tenantSlug = getTenantSlug();

  if (!tenantSlug) {
    return (
      <div className="notice notice--no-tenant">
        You&apos;re on the root domain (eraj.com) — no tenant resolved. Visit{" "}
        <code>abc.localhost:3000</code> or <code>xyz.localhost:3000</code> in dev to see a
        tenant&apos;s dashboard.
      </div>
    );
  }

  return (
    <div>
      <h1>Welcome, {tenantSlug}</h1>
      <p>This is your institution&apos;s Eraj dashboard. Pick a module below.</p>
      <nav className="nav-links">
        <Link href="/library">Library</Link>
        <Link href="/hostel">Hostel</Link>
      </nav>
      <p style={{ fontSize: 13, color: "#888" }}>
        Module access shown here reflects your institution&apos;s current plan — enforced by the
        backend, not by this page.
      </p>
    </div>
  );
}
