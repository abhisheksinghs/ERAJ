"use client";

import {
  BankOutlined, BookOutlined, CarOutlined, CheckSquareOutlined, DashboardOutlined, FileDoneOutlined,
  HomeOutlined, InboxOutlined, ScheduleOutlined, SettingOutlined, TeamOutlined, WalletOutlined,
} from "@ant-design/icons";
import { ThemedLayout, ThemedTitle, useNotificationProvider } from "@refinedev/antd";
import { type AccessControlProvider, type I18nProvider, Refine, type ResourceProps } from "@refinedev/core";
import routerProvider from "@refinedev/nextjs-router";
import { App as AntdApp, Button, ConfigProvider, Result, Spin } from "antd";
import enUS from "antd/locale/en_US";
import hiIN from "antd/locale/hi_IN";
import dayjs from "dayjs";
import "dayjs/locale/hi";
import { useEffect, useMemo, useState } from "react";

import { StaffHeader } from "@/components/staff/StaffHeader";
import { UI } from "@/lib/i18n";
import { dataProvider, SUBSCRIPTION_EVENT } from "@/lib/refine/dataProvider";
import { SessionProvider, useSession } from "@/lib/refine/session";
import { MODULES, PAGES, RESOURCES, tr } from "@/lib/resources";

const VERB: Record<string, string> = {
  list: "view", show: "view", create: "manage", edit: "manage", delete: "manage", clone: "manage",
};

// Refine's built-in toast texts ("Successfully created library/issue") name the
// internal resource; replace them with plain bilingual messages.
const NOTIFICATIONS: Record<string, { en: string; hi: string }> = {
  "notifications.success": { en: "Done", hi: "पूर्ण" },
  "notifications.error": { en: "Something went wrong", hi: "कुछ गलत हुआ" },
  "notifications.createSuccess": { en: "Saved", hi: "सहेजा गया" },
  "notifications.editSuccess": { en: "Saved", hi: "सहेजा गया" },
  "notifications.deleteSuccess": { en: "Deleted", hi: "हटाया गया" },
  "notifications.createError": { en: "Could not save", hi: "सहेजा नहीं जा सका" },
  "notifications.editError": { en: "Could not save", hi: "सहेजा नहीं जा सका" },
  "notifications.deleteError": { en: "Could not delete", hi: "हटाया नहीं जा सका" },
};

const ICONS: Record<string, React.ComponentType> = {
  BankOutlined, BookOutlined, CarOutlined, CheckSquareOutlined, DashboardOutlined, FileDoneOutlined,
  HomeOutlined, InboxOutlined, ScheduleOutlined, SettingOutlined, TeamOutlined, WalletOutlined,
};

function icon(name: string) {
  const Cmp = ICONS[name];
  return Cmp ? <Cmp /> : undefined;
}

function Shell({ children }: { children: React.ReactNode }) {
  const session = useSession();
  const { me, lang, can } = session;
  const [inactive, setInactive] = useState(false);

  useEffect(() => {
    const on = () => setInactive(true);
    window.addEventListener(SUBSCRIPTION_EVENT, on);
    return () => window.removeEventListener(SUBSCRIPTION_EVENT, on);
  }, []);
  useEffect(() => {
    dayjs.locale(lang === "hi" ? "hi" : "en");
  }, [lang]);

  const resources = useMemo<ResourceProps[]>(() => {
    const visible = RESOURCES.filter((r) => can(`${r.perm}.view`));
    const pages = PAGES.filter((p) => can(p.perm));
    const modules = MODULES.filter((m) => visible.some((r) => r.module === m.key) || pages.some((p) => p.module === m.key));
    return [
      { name: "dashboard", list: "/dashboard", meta: { label: tr(UI.dashboard, lang), icon: icon("DashboardOutlined") } },
      ...modules.map((m) => ({ name: m.key, meta: { label: tr(m.label, lang), icon: icon(m.icon) } })),
      ...pages.map((p) => ({ name: p.name, list: p.path, meta: { label: tr(p.label, lang), parent: p.module } })),
      ...visible.map((r) => ({
        name: r.name,
        list: `/${r.name}`,
        create: r.canCreate ? `/${r.name}/create` : undefined,
        edit: r.canEdit ? `/${r.name}/:id/edit` : undefined,
        meta: { label: tr(r.label, lang), parent: r.module, canDelete: r.canDelete },
      })),
    ];
  }, [can, lang]);

  const accessControlProvider = useMemo<AccessControlProvider>(
    () => ({
      can: async ({ resource, action }) => {
        if (!resource || resource === "dashboard") return { can: true };
        const page = PAGES.find((p) => p.name === resource);
        if (page) return { can: can(page.perm) };
        const def = RESOURCES.find((r) => r.name === resource);
        if (!def) return { can: MODULES.some((m) => m.key === resource) };
        return { can: can(`${def.perm}.${VERB[action] ?? action}`) };
      },
      options: { buttons: { enableAccessControl: true, hideIfUnauthorized: true } },
    }),
    [can],
  );

  const i18nProvider = useMemo<I18nProvider>(
    () => ({
      translate: (key: string, opts?: unknown, fallback?: string) => {
        // Refine passes the default text either as the 2nd or the 3rd argument.
        const dflt = typeof opts === "string" ? opts : fallback;
        const notice = NOTIFICATIONS[key];
        if (notice) return notice[lang];
        if (key.startsWith("notifications.")) return dflt ?? notice ?? key;
        const entry = (UI as Record<string, { en: string; hi: string }>)[key.split(".").pop() ?? key];
        return entry ? entry[lang] : dflt ?? key;
      },
      changeLocale: async () => undefined,
      getLocale: () => lang,
    }),
    [lang],
  );

  if (!me) {
    return (
      <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <ConfigProvider
      locale={lang === "hi" ? hiIN : enUS}
      theme={{ token: { colorPrimary: "#1e2761", borderRadius: 8, fontFamily: "inherit" } }}
    >
      <AntdApp>
        <Refine
          dataProvider={dataProvider}
          routerProvider={routerProvider}
          notificationProvider={useNotificationProvider}
          accessControlProvider={accessControlProvider}
          i18nProvider={i18nProvider}
          resources={resources}
          options={{ syncWithLocation: true, warnWhenUnsavedChanges: true, disableTelemetry: true }}
        >
          <ThemedLayout
            Header={StaffHeader}
            Title={({ collapsed }) => <ThemedTitle collapsed={collapsed} text="Eraj" />}
          >
            {inactive ? (
              <Result
                status="warning"
                title={tr(UI.subscriptionTitle, lang)}
                subTitle={tr(UI.subscriptionBody, lang)}
                extra={
                  <Button type="primary" href="mailto:billing@eraj.example?subject=Renew%20subscription">
                    {tr(UI.contactBilling, lang)}
                  </Button>
                }
              />
            ) : (
              children
            )}
          </ThemedLayout>
        </Refine>
      </AntdApp>
    </ConfigProvider>
  );
}

export function StaffShell({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <Shell>{children}</Shell>
    </SessionProvider>
  );
}
