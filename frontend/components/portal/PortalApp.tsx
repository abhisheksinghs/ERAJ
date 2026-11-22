"use client";

import {
  BookOutlined, CalendarOutlined, HomeOutlined, LogoutOutlined, MenuOutlined, WalletOutlined,
} from "@ant-design/icons";
import { Alert, Button, Drawer, Segmented, Select, Space, Spin, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { usePortalLang } from "@/components/portal/PortalShell";
import {
  AttendanceTab, BusTab, ClassesTab, DiaryTab, FeesTab, HomeTab, HomeworkTab, HostelTab, NoticesTab, RequestsTab, ResultsTab, TimetableTab,
} from "@/components/portal/sections";
import { type Child, type Me, portal, t, tr } from "@/lib/portal";

export type Tab = "home" | "attendance" | "fees" | "homework" | "results" | "classes" | "timetable" | "diary" | "hostel" | "bus" | "notices" | "requests";

const TABS: Record<Tab, ReturnType<typeof t>> = {
  home: t("Home", "मुख्य"), attendance: t("Attendance", "उपस्थिति"), fees: t("Fees", "शुल्क"), homework: t("Homework", "गृहकार्य"),
  results: t("Results", "परिणाम"), classes: t("Online classes & tests", "ऑनलाइन कक्षा एवं परीक्षा"), timetable: t("Timetable", "समय-सारणी"),
  diary: t("Class diary", "कक्षा डायरी"), hostel: t("Hostel", "छात्रावास"), bus: t("Bus", "बस"), notices: t("Notices", "सूचनाएँ"),
  requests: t("Leave & changes", "अवकाश एवं परिवर्तन"),
};
const BOTTOM: { key: Tab; icon: React.ReactNode }[] = [
  { key: "home", icon: <HomeOutlined /> }, { key: "attendance", icon: <CalendarOutlined /> },
  { key: "fees", icon: <WalletOutlined /> }, { key: "homework", icon: <BookOutlined /> },
];
const MORE: Tab[] = ["results", "classes", "timetable", "diary", "notices", "hostel", "bus", "requests"];

/** First names on the switcher, unless two children would look the same. */
function shortName(c: Child, all: Child[]) {
  const first = c.name.split(" ")[0];
  return all.filter((x) => x.name.split(" ")[0] === first).length > 1 ? c.name : first;
}

/** The whole portal: child switcher on top, sections below, phone-style bottom bar. */
export function PortalApp() {
  const { lang, setLang } = usePortalLang();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [childId, setChildId] = useState<number | null>(null);
  const [tab, setTabState] = useState<Tab>("home");
  const [more, setMore] = useState(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const tb = q.get("tab") as Tab | null;
    if (tb && tb in TABS) setTabState(tb);
    portal.me().then((m) => {
      setMe(m);
      const wanted = Number(q.get("child"));
      setChildId(m.children.find((c) => c.id === wanted)?.id ?? m.children[0]?.id ?? null);
      if (m.language && !document.cookie.includes("eraj_lang=")) setLang(m.language);
    }).catch((e) => setError((e as Error).message));
  }, [setLang]);

  const setTab = useCallback((tb: Tab) => {
    setTabState(tb);
    setMore(false);
    const q = new URLSearchParams(window.location.search);
    q.set("tab", tb);
    window.history.replaceState(null, "", `?${q.toString()}`);
    window.scrollTo({ top: 0 });
  }, []);
  const choose = (id: number) => {
    setChildId(id);
    const q = new URLSearchParams(window.location.search);
    q.set("child", String(id));
    window.history.replaceState(null, "", `?${q.toString()}`);
  };

  if (error) return <Alert style={{ margin: 16 }} type="error" showIcon message={error} />;
  if (!me) return <div style={{ padding: 48, textAlign: "center" }}><Spin /></div>;
  const child: Child | undefined = me.children.find((c) => c.id === childId);

  return (
    <>
      <header className="portal-top">
        <Space style={{ width: "100%", justifyContent: "space-between" }}>
          <span className="auth-brand" style={{ margin: 0 }}>ERAJ</span>
          <Space>
            <Segmented size="small" value={lang} onChange={(v) => setLang(v as "en" | "hi")} options={[{ label: "EN", value: "en" }, { label: "हि", value: "hi" }]} />
            <form action="/logout?to=portal" method="post"><Button size="small" htmlType="submit" icon={<LogoutOutlined />} aria-label="sign out" /></form>
          </Space>
        </Space>
        {me.children.length > 1 ? (
          <div style={{ marginTop: 10 }}>
            {me.children.length <= 3 ? (
              <Segmented block value={childId ?? undefined} onChange={(v) => choose(Number(v))} data-testid="child-switch"
                options={me.children.map((c) => ({ value: c.id, label: shortName(c, me.children) }))} />
            ) : (
              <Select style={{ width: "100%" }} value={childId} onChange={choose} options={me.children.map((c) => ({ value: c.id, label: c.name }))} />
            )}
          </div>
        ) : null}
        {child && <Typography.Text type="secondary" style={{ display: "block", marginTop: 6 }}>
          {child.name} · {child.section ?? "—"} · {child.branch_name}
        </Typography.Text>}
      </header>

      <main className="portal-main">
        {!child ? (
          <Alert type="info" showIcon message={tr(t("No student is linked to this mobile number. Please contact the school office.", "इस मोबाइल नंबर से कोई छात्र जुड़ा नहीं है। विद्यालय कार्यालय से संपर्क करें।"), lang)} />
        ) : (
          <div key={`${child.id}-${tab}`}>
            <Typography.Title level={4} style={{ marginTop: 0 }}>{tr(TABS[tab], lang)}</Typography.Title>
            {tab === "home" && <HomeTab child={child} go={setTab} />}
            {tab === "attendance" && <AttendanceTab child={child} />}
            {tab === "fees" && <FeesTab child={child} />}
            {tab === "homework" && <HomeworkTab child={child} />}
            {tab === "results" && <ResultsTab child={child} />}
            {tab === "classes" && <ClassesTab child={child} />}
            {tab === "timetable" && <TimetableTab child={child} />}
            {tab === "diary" && <DiaryTab child={child} />}
            {tab === "hostel" && <HostelTab child={child} />}
            {tab === "bus" && <BusTab child={child} />}
            {tab === "notices" && <NoticesTab child={child} />}
            {tab === "requests" && <RequestsTab child={child} />}
          </div>
        )}
      </main>

      <nav className="portal-bottom" aria-label="sections">
        {BOTTOM.map((b) => (
          <button key={b.key} type="button" className={tab === b.key ? "on" : ""} onClick={() => setTab(b.key)}>
            {b.icon}<span>{tr(TABS[b.key], lang)}</span>
          </button>
        ))}
        <button type="button" className={MORE.includes(tab) ? "on" : ""} onClick={() => setMore(true)}>
          <MenuOutlined /><span>{tr(t("More", "और"), lang)}</span>
        </button>
      </nav>
      <Drawer placement="bottom" open={more} onClose={() => setMore(false)} height="auto" title={tr(t("More", "और"), lang)}>
        <div className="portal-more">
          {MORE.map((k) => <Button key={k} block size="large" type={tab === k ? "primary" : "default"} onClick={() => setTab(k)}>{tr(TABS[k], lang)}</Button>)}
        </div>
      </Drawer>
    </>
  );
}
