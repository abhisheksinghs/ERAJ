"use client";

import { CheckOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, DatePicker, Radio, Result, Space, Spin, Table, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Staff attendance in one save: everyone present unless changed; approved leave is fixed (ADR-009). */
interface Row {
  staff: number; name: string; employee_code: string; designation: string; department: string;
  status: string | null; source: string | null; locked_by_leave: boolean;
}
interface Sheet { date: string; holiday: string | null; marked: boolean; rows: Row[] }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Mark staff attendance", "कर्मचारी उपस्थिति लगाएँ"),
  hint: t("Everyone is present. Change anyone absent, half-day or on duty, then save. Leave comes from approved applications.",
    "सभी उपस्थित हैं। अनुपस्थित, आधा दिन या ड्यूटी पर बदलें, फिर सहेजें। अवकाश स्वीकृत आवेदनों से आता है।"),
  holiday: t("Holiday", "अवकाश"),
  save: t("Save attendance", "उपस्थिति सहेजें"),
  saved: t("Saved", "सहेजा गया"),
  notSaved: t("Not saved yet for this date", "इस तिथि के लिए अभी सहेजा नहीं"),
  onLeave: t("On approved leave", "स्वीकृत अवकाश पर"),
  device: t("Punched in", "पंच किया"),
  code: t("Code", "कोड"), name: t("Name", "नाम"), dept: t("Department", "विभाग"), status: t("Status", "स्थिति"),
};
const STATUS = [
  { value: "present", label: t("Present", "उपस्थित") },
  { value: "absent", label: t("Absent", "अनुपस्थित") },
  { value: "half_day", label: t("Half-day", "आधा दिन") },
  { value: "on_duty", label: t("On duty", "ड्यूटी पर") },
];

export default function MarkStaffAttendance() {
  const { lang, can, allBranches, branch } = useSession();
  const { message } = App.useApp();
  const [day, setDay] = useState<Dayjs>(dayjs());
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [marks, setMarks] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (allBranches) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<Sheet>(`hr/attendance/day?date=${day.format("YYYY-MM-DD")}`);
      setSheet(data);
      setMarks(Object.fromEntries(data.rows.map((r) => [r.staff, r.status ?? "present"])));
    } catch (e) {
      setError((e as { message?: string }).message ?? "Error");
    } finally {
      setLoading(false);
    }
  }, [day, allBranches, branch?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    Object.values(marks).forEach((v) => (c[v] = (c[v] ?? 0) + 1));
    return c;
  }, [marks]);

  if (!can("hr.attendance.manage")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  async function save() {
    if (!sheet) return;
    setSaving(true);
    try {
      const statuses: Record<string, string> = {};
      const absent: number[] = [];
      sheet.rows.filter((r) => !r.locked_by_leave).forEach((r) => {
        const st = marks[r.staff];
        if (st === "absent") absent.push(r.staff);
        else if (st !== "present") statuses[String(r.staff)] = st;
      });
      const res = await api.post<{ created: number; updated: number }>("hr/attendance/mark", { date: day.format("YYYY-MM-DD"), absent, statuses });
      message.success(`${tr(L.saved, lang)} — ${counts.present ?? 0} P · ${counts.absent ?? 0} A (${res.created + res.updated})`);
      await load();
    } catch (e) {
      message.error((e as { message?: string }).message ?? "Error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Space wrap>
        <DatePicker value={day} onChange={(d) => d && setDay(d)} format="DD-MM-YYYY" allowClear={false}
          disabledDate={(d) => d.isAfter(dayjs(), "day")} aria-label="date" />
        {sheet && !sheet.marked && !sheet.holiday && <Tag color="orange">{tr(L.notSaved, lang)}</Tag>}
      </Space>
      {error && <Alert type="error" showIcon message={error} />}
      {sheet?.holiday && <Alert type="info" showIcon message={`${tr(L.holiday, lang)}: ${sheet.holiday}`} />}
      {loading && <Spin />}
      {sheet && !sheet.holiday && (
        <Card size="small">
          <Typography.Paragraph type="secondary">{tr(L.hint, lang)}</Typography.Paragraph>
          <Table<Row>
            rowKey="staff" size="small" pagination={false} dataSource={sheet.rows}
            columns={[
              { title: tr(L.code, lang), dataIndex: "employee_code", width: 100 },
              { title: tr(L.name, lang), dataIndex: "name", render: (v, r) => <span>{v} <Typography.Text type="secondary">{r.designation}</Typography.Text></span> },
              { title: tr(L.dept, lang), dataIndex: "department", responsive: ["md"] },
              {
                title: tr(L.status, lang), key: "status",
                render: (_, r) => r.locked_by_leave ? <Tag color="gold">{tr(L.onLeave, lang)}</Tag> : (
                  <Space size={4} wrap>
                    <Radio.Group size="small" optionType="button" value={marks[r.staff]} aria-label={`status-${r.employee_code}`}
                      onChange={(e) => setMarks((m) => ({ ...m, [r.staff]: e.target.value }))}
                      options={STATUS.map((s) => ({ value: s.value, label: tr(s.label, lang) }))} />
                    {r.source === "device" && <Tag color="blue">{tr(L.device, lang)}</Tag>}
                  </Space>
                ),
              },
            ]}
          />
          <Space style={{ marginTop: 12 }}>
            <Button type="primary" icon={<CheckOutlined />} loading={saving} onClick={save}>{tr(L.save, lang)}</Button>
            <Typography.Text type="secondary">
              {counts.present ?? 0} P · {counts.absent ?? 0} A · {counts.half_day ?? 0} H · {counts.on_duty ?? 0} OD
            </Typography.Text>
          </Space>
        </Card>
      )}
    </Space>
  );
}
