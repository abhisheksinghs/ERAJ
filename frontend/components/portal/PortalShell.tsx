"use client";

import { App as AntdApp, ConfigProvider } from "antd";
import enUS from "antd/locale/en_US";
import hiIN from "antd/locale/hi_IN";
import dayjs from "dayjs";
import "dayjs/locale/hi";
import { createContext, useContext, useEffect, useState } from "react";

import type { Lang } from "@/lib/portal";

interface Ctx { lang: Lang; setLang: (l: Lang) => void }
const LangContext = createContext<Ctx>({ lang: "en", setLang: () => undefined });
export const usePortalLang = () => useContext(LangContext);

function readLang(): Lang {
  const m = typeof document !== "undefined" ? document.cookie.match(/(?:^|; )eraj_lang=([^;]*)/) : null;
  return m?.[1] === "hi" ? "hi" : "en";
}

/** Theme + language for the portal; phone-first width. */
export function PortalShell({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => setLangState(readLang()), []);
  useEffect(() => { dayjs.locale(lang === "hi" ? "hi" : "en"); }, [lang]);
  const setLang = (l: Lang) => {
    document.cookie = `eraj_lang=${l}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
    setLangState(l);
  };
  return (
    <LangContext.Provider value={{ lang, setLang }}>
      <ConfigProvider locale={lang === "hi" ? hiIN : enUS} theme={{ token: { colorPrimary: "#1e2761", borderRadius: 10, fontSize: 15 } }}>
        <AntdApp>
          <div className="portal">{children}</div>
        </AntdApp>
      </ConfigProvider>
    </LangContext.Provider>
  );
}
