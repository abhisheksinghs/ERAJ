import { AntdRegistry } from "@ant-design/nextjs-registry";
import type { Metadata } from "next";
import { cookies } from "next/headers";

import "./globals.css";

export const metadata: Metadata = {
  title: "Eraj",
  description: "School, college and coaching management.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const lang = (await cookies()).get("eraj_lang")?.value === "hi" ? "hi" : "en";
  return (
    <html lang={lang}>
      <body>
        <AntdRegistry>{children}</AntdRegistry>
      </body>
    </html>
  );
}
