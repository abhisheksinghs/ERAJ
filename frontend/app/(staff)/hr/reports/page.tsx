"use client";

import { DownloadOutlined, PrinterOutlined } from "@ant-design/icons";
import { Alert, Button, DatePicker, InputNumber, Result, Space, Table, Tabs, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

interface Register {
  working_days: number; days: { date: string; holiday: string | null }[];
  rows: { staff: number; name: string; employee_code: string; department: string; marks: (string | null)[];
          present: number; absent: number; leave: number; half_day: number; on_duty: number; lop_days: number }[];
}
interface Head { department: string; permanent: number; contract: number; part_time: number; total: number }
interface Bal { staff: number; name: string; employee_code: string; leave_type: string; entitled: number; used: number; pending: number; available: number }
interface Away { staff: number; name: string; employee_code: string; department: string; status?: string; leave_type?: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("HR reports", "मानव संसाधन रिपोर्ट"),
  register: t("Monthly attendance", "मासिक उपस्थिति"), headcount: t("Headcount", "कर्मचारी संख्या"),
  balances: t("Leave balances", "अवकाश शेष"), absentees: t("Absent today", "आज अनुपस्थित"),
  print: t("Print", "प्रिंट"), excel: t("Excel", "एक्सेल"), working: t("Working days", "कार्य दिवस"),
  notMarked: t("Attendance not marked yet", "उपस्थिति अभी नहीं लगी"), away: t("Away", "अनुपस्थित"),
  dept: t("Department", "विभाग"), name: t("Name", "नाम"), year: t("Year", "वर्ष"),
};
const COLOR: Record<string, string> = { A: "#b42318", H: "#6d28d9", OD: "#1d4ed8" };

function useData<R>(path: string | null) {
  const [data, setData] = useState<R | null>(null);
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async () => {
    if (!path) return;
    setError(null);
    try {
      setData(await api.get<R>(path));
    } catch (e) {
      setError((e as { message?: string }).message ?? "Error");
    }
  }, [path]);
  useEffect(() => {
    void run();
  }, [run]);
  return { data, error };
}

export default function HRReports() {
  const { lang, can, allBranches } = useSession();
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [year, setYear] = useState<number>(dayjs().year());
  const [day, setDay] = useState<Dayjs>(dayjs());
  const ok = can("hr.report.view") && !allBranches;
  const reg = useData<Register>(ok ? `hr/attendance/register?month=${month.format("YYYY-MM")}` : null);
  const head = useData<Head[]>(ok ? "hr/reports/headcount" : null);
  const bal = useData<Bal[]>(ok ? `hr/reports/balances?year=${year}` : null);
  const abs = useData<{ away: Away[]; not_marked: Away[]; holiday: string | null }>(ok ? `hr/reports/absentees?date=${day.format("YYYY-MM-DD")}` : null);

  if (!can("hr.report.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Tabs items={[
        {
          key: "register", label: tr(L.register, lang), children: (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space wrap>
                <DatePicker picker="month" value={month} onChange={(d) => d && setMonth(d)} allowClear={false} aria-label="month" />
                <Button icon={<PrinterOutlined />} href={`${API}/hr/attendance/register?month=${month.format("YYYY-MM")}&pdf=1`} target="_blank">{tr(L.print, lang)}</Button>
                {reg.data && <Tag>{tr(L.working, lang)}: {reg.data.working_days}</Tag>}
              </Space>
              {reg.error && <Alert type="error" message={reg.error} />}
              {reg.data && (
                <Table size="small" rowKey="staff" pagination={false} scroll={{ x: true }} dataSource={reg.data.rows}
                  columns={[
                    { title: tr(L.name, lang), dataIndex: "name", fixed: "left", width: 180 },
                    ...reg.data.days.map((d, i) => ({
                      title: dayjs(d.date).format("D"), key: d.date, width: 34, align: "center" as const,
                      onCell: () => ({ style: d.holiday ? { background: "#eef0f5" } : {} }),
                      render: (_: unknown, r: Register["rows"][number]) => <span style={{ color: COLOR[r.marks[i] ?? ""] }}>{r.marks[i] ?? ""}</span>,
                    })),
                    { title: "P", dataIndex: "present" }, { title: "A", dataIndex: "absent" }, { title: "L", dataIndex: "leave" },
                    { title: "LOP", dataIndex: "lop_days" },
                  ]} />
              )}
            </Space>
          ),
        },
        {
          key: "absent", label: tr(L.absentees, lang), children: (
            <Space direction="vertical" style={{ width: "100%" }}>
              <DatePicker value={day} onChange={(d) => d && setDay(d)} format="DD-MM-YYYY" allowClear={false} aria-label="date" />
              {abs.data?.holiday && <Alert type="info" message={abs.data.holiday} />}
              <Typography.Title level={5}>{tr(L.away, lang)} ({abs.data?.away.length ?? 0})</Typography.Title>
              <Table size="small" rowKey="staff" pagination={false} dataSource={abs.data?.away ?? []}
                columns={[{ title: tr(L.name, lang), dataIndex: "name" }, { title: tr(L.dept, lang), dataIndex: "department" },
                  { title: "", key: "s", render: (_, r) => <Tag>{r.leave_type || r.status}</Tag> }]} />
              <Typography.Title level={5}>{tr(L.notMarked, lang)} ({abs.data?.not_marked.length ?? 0})</Typography.Title>
              <Table size="small" rowKey="staff" pagination={false} dataSource={abs.data?.not_marked ?? []}
                columns={[{ title: tr(L.name, lang), dataIndex: "name" }, { title: tr(L.dept, lang), dataIndex: "department" }]} />
            </Space>
          ),
        },
        {
          key: "balances", label: tr(L.balances, lang), children: (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space>
                <InputNumber value={year} onChange={(v) => v && setYear(v)} min={2000} max={2100} aria-label={tr(L.year, lang)} />
                <Button icon={<DownloadOutlined />} href={`${API}/hr/reports/balances?year=${year}&format=xlsx`}>{tr(L.excel, lang)}</Button>
              </Space>
              <Table size="small" rowKey={(r) => `${r.staff}-${r.leave_type}`} dataSource={bal.data ?? []}
                columns={[{ title: tr(L.name, lang), dataIndex: "name" }, { title: "", dataIndex: "leave_type" },
                  { title: "Entitled", dataIndex: "entitled" }, { title: "Used", dataIndex: "used" },
                  { title: "Pending", dataIndex: "pending" }, { title: "Available", dataIndex: "available" }]} />
            </Space>
          ),
        },
        {
          key: "headcount", label: tr(L.headcount, lang), children: (
            <Table size="small" rowKey="department" pagination={false} dataSource={head.data ?? []}
              columns={[{ title: tr(L.dept, lang), dataIndex: "department" }, { title: "Permanent", dataIndex: "permanent" },
                { title: "Contract", dataIndex: "contract" }, { title: "Part-time", dataIndex: "part_time" }, { title: "Total", dataIndex: "total" }]} />
          ),
        },
      ]} />
    </Space>
  );
}
