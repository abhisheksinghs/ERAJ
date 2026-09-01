import type { Metadata } from "next";
import { getTenantSlug } from "@/lib/tenant";
import "./globals.css";

export const metadata: Metadata = {
  title: "Eraj",
  description: "One platform, every institution.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const tenantSlug = getTenantSlug();

  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <span className="brand">ERAJ</span>
          {tenantSlug ? (
            <span className="tenant-badge">{tenantSlug}</span>
          ) : (
            <span className="tenant-badge tenant-badge--none">no tenant (root domain)</span>
          )}
        </header>
        <main className="content">{children}</main>
      </body>
    </html>
  );
}
