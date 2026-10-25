"use client";

import { DownloadOutlined, PrinterOutlined } from "@ant-design/icons";
import { Alert, Button, DatePicker, Empty, InputNumber, Result, Space, Table, Tabs, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

interface Register {
  section_name: string; working_days: number;
  days: { date: string; holiday: string | null }[];
  rows: { student: number; name: string; roll_no: string; marks: (string | null)[]; attended: number; marked: number; percentage: number }[];
}
interface Daily { section: number; section_name: string; enrolled: number; marked: number; present: number; absent: number; leave: number; late: number; half_day: number; percentage: number }
interface Pct { student: number; name: string; admission_no: string; section: string; attended: number; marked: number; percentage: number }
interface LongAbs { student: number; name: string; admission_no: string; absent_days: number; since: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Attendance reports", "उपस्थिति रिपोर्ट"),
  register: t("Monthly register", "मासिक रजिस्टर"),
  daily: t("Daily summary", "दैनिक सारांश"),
  below: t("Below minimum %", "न्यूनतम % से कम"),
  long: t("Long absentees", "लंबे अनुपस्थित"),
  section: t("Section", "अनुभाग"),
  print: t("Print", "प्रिंट"),
  excel: t("Excel", "एक्सेल"),
  threshold: t("Below %", "% से कम"),
  days: t("Absent for at least (days)", "कम से कम अनुपस्थित (दिन)"),
  working: t("Working days", "कार्य दिवस"),
  pickSection: t("Choose a section", "अनुभाग चुनें"),
};
const CODE_COLOR: Record<string, string> = { A: "#b42318", L: "#8a5a00", LT: "#1d4ed8", H: "#6d28d9" };

function useLoad<R>(fn: () => Promise<R>, deps: unknown[]) {
  const [data, setData] = useState<R | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fn());
    } catch (e) {
      setError((e as { message?: string }).message ?? "Error");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, deps);
  return { data, error, loading, run };
}

export default function AttendanceReports() {
  const { lang, can } = useSession();
  const [section, setSection] = useState<number | null>(null);
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [day, setDay] = useState<Dayjs>(dayjs());
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().subtract(30, "day"), dayjs()]);
  const [threshold, setThreshold] = useState<number | null>(null);
  const [minDays, setMinDays] = useState<number | null>(null);

  const reg = useLoad<Register | null>(
    async () => (section ? api.get<Register>(`attendance/reports/register?section=${section}&month=${month.format("YYYY-MM")}`) : null),
    [section, month],
  );
  const daily = useLoad<Daily[]>(() => api.get<Daily[]>(`attendance/reports/daily?date=${day.format("YYYY-MM-DD")}`), [day]);
  const belowQ = `from=${range[0].format("YYYY-MM-DD")}&to=${range[1].format("YYYY-MM-DD")}${threshold ? `&threshold=${threshold}` : ""}${section ? `&section=${section}` : ""}`;
  const below = useLoad<Pct[]>(() => api.get<Pct[]>(`attendance/reports/below?${belowQ}`), [belowQ]);
  const longQ = `${minDays ? `days=${minDays}` : ""}${section ? `&section=${section}` : ""}`;
  const longAbs = useLoad<LongAbs[]>(() => api.get<LongAbs[]>(`attendance/reports/long-absent?${longQ}`), [longQ]);

  useEffect(() => { void reg.run(); }, [reg.run]);
  useEffect(() => { void daily.run(); }, [daily.run]);
  useEffect(() => { void below.run(); }, [below.run]);
  useEffect(() => { void longAbs.run(); }, [longAbs.run]);

  if (!can("attendance.report.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;

  const sectionPicker = (
    <div style={{ minWidth: 220 }}>
      <RelationSelect resource="people/sections" label="label" value={section} placeholder={tr(L.section, lang)}
        onChange={(v) => setSection(v as number | null)} />
    </div>
  );
  const err = (e: string | null) => e && <Alert type="error" showIcon message={e} />;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Tabs
        items={[
          {
            key: "register",
            label: tr(L.register, lang),
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  {sectionPicker}
                  <DatePicker picker="month" value={month} onChange={(m) => m && setMonth(m)} allowClear={false} format="MMM YYYY" />
                  {section && (
                    <Button icon={<PrinterOutlined />} href={`${API}/attendance/reports/register?section=${section}&month=${month.format("YYYY-MM")}&pdf=1`} target="_blank">
                      {tr(L.print, lang)}
                    </Button>
                  )}
                </Space>
                {err(reg.error)}
                {!section && <Empty description={tr(L.pickSection, lang)} />}
                {reg.data && (
                  <>
                    <Typography.Text type="secondary">{reg.data.section_name} · {tr(L.working, lang)}: {reg.data.working_days}</Typography.Text>
                    <Table
                      rowKey="student" size="small" pagination={false} loading={reg.loading} scroll={{ x: true }} bordered
                      dataSource={reg.data.rows}
                      columns={[
                        { title: "#", dataIndex: "roll_no", fixed: "left", width: 44 },
                        { title: tr(t("Student", "छात्र"), lang), dataIndex: "name", fixed: "left", width: 170 },
                        ...reg.data.days.map((d, i) => ({
                          title: <span style={{ fontSize: 11 }}>{dayjs(d.date).format("D")}<br />{dayjs(d.date).format("dd")}</span>,
                          key: d.date,
                          width: 34,
                          align: "center" as const,
                          onCell: () => ({ style: d.holiday ? { background: "#eef0f5" } : {} }),
                          render: (_: unknown, r: Register["rows"][number]) => {
                            const m = r.marks[i];
                            return m ? <span style={{ color: CODE_COLOR[m] ?? undefined, fontWeight: m === "A" ? 700 : 400 }}>{m}</span> : "";
                          },
                        })),
                        { title: "%", dataIndex: "percentage", fixed: "right", width: 60, align: "right" as const,
                          render: (v: number) => <Tag color={v < 75 ? "red" : "green"}>{v}</Tag> },
                      ]}
                    />
                  </>
                )}
              </Space>
            ),
          },
          {
            key: "daily",
            label: tr(L.daily, lang),
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <DatePicker value={day} onChange={(d) => d && setDay(d)} format="DD-MM-YYYY" allowClear={false} />
                {err(daily.error)}
                <Table<Daily>
                  rowKey="section" size="small" pagination={false} loading={daily.loading} dataSource={daily.data ?? []}
                  columns={[
                    { title: tr(L.section, lang), dataIndex: "section_name" },
                    { title: tr(t("Enrolled", "नामांकित"), lang), dataIndex: "enrolled", align: "right" },
                    { title: tr(t("Marked", "चिह्नित"), lang), dataIndex: "marked", align: "right",
                      render: (v: number, r) => (v === 0 ? <Tag color="orange">{tr(t("Not marked", "नहीं लगी"), lang)}</Tag> : `${v}/${r.enrolled}`) },
                    { title: "P", dataIndex: "present", align: "right" },
                    { title: "A", dataIndex: "absent", align: "right" },
                    { title: "L", dataIndex: "leave", align: "right" },
                    { title: "LT", dataIndex: "late", align: "right" },
                    { title: "H", dataIndex: "half_day", align: "right" },
                    { title: "%", dataIndex: "percentage", align: "right" },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "below",
            label: tr(L.below, lang),
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  <DatePicker.RangePicker value={range} format="DD-MM-YYYY" allowClear={false}
                    onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])} />
                  <InputNumber min={1} max={100} placeholder={tr(L.threshold, lang)} value={threshold} onChange={setThreshold} addonAfter="%" />
                  {sectionPicker}
                  <Button icon={<DownloadOutlined />} href={`${API}/attendance/reports/below?${belowQ}&format=xlsx`}>{tr(L.excel, lang)}</Button>
                </Space>
                {err(below.error)}
                <Table<Pct>
                  rowKey="student" size="small" loading={below.loading} dataSource={below.data ?? []}
                  columns={[
                    { title: tr(t("Admission no.", "प्रवेश सं."), lang), dataIndex: "admission_no" },
                    { title: tr(t("Student", "छात्र"), lang), dataIndex: "name" },
                    { title: tr(L.section, lang), dataIndex: "section" },
                    { title: tr(t("Attended / marked", "उपस्थित / कुल"), lang), render: (_, r) => `${r.attended} / ${r.marked}` },
                    { title: "%", dataIndex: "percentage", align: "right", render: (v: number) => <Tag color="red">{v}</Tag> },
                  ]}
                />
              </Space>
            ),
          },
          {
            key: "long",
            label: tr(L.long, lang),
            children: (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space wrap>
                  <InputNumber min={2} max={60} placeholder={tr(L.days, lang)} value={minDays} onChange={setMinDays} style={{ width: 220 }} />
                  {sectionPicker}
                </Space>
                {err(longAbs.error)}
                <Table<LongAbs>
                  rowKey="student" size="small" loading={longAbs.loading} dataSource={longAbs.data ?? []}
                  columns={[
                    { title: tr(t("Admission no.", "प्रवेश सं."), lang), dataIndex: "admission_no" },
                    { title: tr(t("Student", "छात्र"), lang), dataIndex: "name" },
                    { title: tr(t("Absent days in a row", "लगातार अनुपस्थित दिन"), lang), dataIndex: "absent_days", align: "right" },
                    { title: tr(t("Since", "से"), lang), dataIndex: "since", render: (v: string) => dayjs(v).format("DD-MM-YYYY") },
                  ]}
                />
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );
}
