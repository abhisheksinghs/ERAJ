"use client";

import { CheckOutlined, IdcardOutlined } from "@ant-design/icons";
import {
  Alert, App, Button, Card, DatePicker, Empty, InputNumber, Radio, Result, Select, Space, Spin, Table, Tag, Typography,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/**
 * Mark a section in one save: everyone starts present (or as already saved /
 * punched in at the gate), the teacher taps the absentees, then Save.
 */
interface SectionRow { id: number; label: string; program: number }
interface SheetRow {
  student: number; name: string; admission_no: string; roll_no: string;
  status: string | null; source: string | null; punched: boolean;
}
interface Sheet { section: number; section_name: string; date: string; holiday: string | null; mode: string; students: SheetRow[] }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Mark attendance", "उपस्थिति लगाएँ"),
  section: t("Section", "अनुभाग"),
  lecture: t("Lecture no.", "व्याख्यान सं."),
  subject: t("Subject", "विषय"),
  noSections: t("No sections are assigned to you. Ask the office to set you as class teacher or add your teaching allocation.",
    "आपको कोई अनुभाग आवंटित नहीं है। कार्यालय से कक्षा-शिक्षक या शिक्षण आवंटन जोड़ने को कहें।"),
  holiday: t("Holiday", "अवकाश"),
  tapHint: t("Everyone is present. Tap a student to mark absent; use the buttons for leave, late or half-day.",
    "सभी उपस्थित हैं। अनुपस्थित करने के लिए छात्र पर टैप करें; अवकाश, विलंब या आधा दिन के लिए बटन।"),
  save: t("Save attendance", "उपस्थिति सहेजें"),
  saved: t("Saved", "सहेजा गया"),
  punched: t("Punched in", "पंच किया"),
  notSaved: t("not saved yet", "अभी सहेजा नहीं"),
  allPresent: t("All present", "सभी उपस्थित"),
};
const STATUS = [
  { value: "present", short: "P", label: t("Present", "उपस्थित"), color: "green" },
  { value: "absent", short: "A", label: t("Absent", "अनुपस्थित"), color: "red" },
  { value: "leave", short: "L", label: t("Leave", "अवकाश"), color: "gold" },
  { value: "late", short: "LT", label: t("Late", "विलंब"), color: "blue" },
  { value: "half_day", short: "H", label: t("Half-day", "आधा दिन"), color: "purple" },
];

export default function MarkAttendance() {
  const { lang, can, allBranches, branch } = useSession();
  const { message } = App.useApp();
  const [sections, setSections] = useState<SectionRow[] | null>(null);
  const [sectionId, setSectionId] = useState<number | null>(null);
  const [day, setDay] = useState<Dayjs>(dayjs());
  const [period, setPeriod] = useState<number | null>(null);
  const [subject, setSubject] = useState<number | null>(null);
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [marks, setMarks] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (allBranches) return;
    api.get<SectionRow[]>("attendance/records/my-sections")
      .then((rows) => {
        setSections(rows);
        if (rows.length === 1) setSectionId(rows[0].id);
      })
      .catch(() => setSections([]));
  }, [branch?.id, allBranches]);

  const perLecture = sheet?.mode === "per_lecture";
  const load = useCallback(async () => {
    if (!sectionId) return;
    setLoading(true);
    setError(null);
    try {
      const q = new URLSearchParams({ section: String(sectionId), date: day.format("YYYY-MM-DD") });
      if (period) q.set("period", String(period));
      const data = await api.get<Sheet>(`attendance/records/sheet?${q}`);
      setSheet(data);
      setMarks(Object.fromEntries(data.students.map((s) => [s.student, s.status ?? "present"])));
    } catch (e) {
      setSheet(null);
      setError((e as { message?: string }).message ?? "Error");
    } finally {
      setLoading(false);
    }
  }, [sectionId, day, period]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    Object.values(marks).forEach((v) => (c[v] = (c[v] ?? 0) + 1));
    return c;
  }, [marks]);

  if (!can("attendance.record.mark")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  async function save() {
    if (!sheet) return;
    setSaving(true);
    try {
      const statuses: Record<string, string> = {};
      const absent: number[] = [];
      Object.entries(marks).forEach(([sid, st]) => {
        if (st === "absent") absent.push(Number(sid));
        else if (st !== "present") statuses[sid] = st;
      });
      const res = await api.post<{ created: number; updated: number }>("attendance/records/mark", {
        section: sheet.section, date: day.format("YYYY-MM-DD"), period: perLecture ? period : null,
        subject: perLecture ? subject : null, absent, statuses,
      });
      message.success(`${tr(L.saved, lang)} — ${counts.present ?? 0} P · ${counts.absent ?? 0} A (${res.created + res.updated})`);
      await load();
    } catch (e) {
      const err = e as { message?: string; errors?: Record<string, string[]> };
      message.error((err.errors ? Object.values(err.errors).flat()[0] : undefined) ?? err.message ?? "Error");
    } finally {
      setSaving(false);
    }
  }

  const toggle = (sid: number) => setMarks((m) => ({ ...m, [sid]: m[sid] === "absent" ? "present" : "absent" }));
  const unsaved = sheet?.students.some((s) => s.status === null) ?? false;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      {sections !== null && sections.length === 0 && <Alert type="info" showIcon message={tr(L.noSections, lang)} />}
      <Space wrap>
        <Select
          style={{ minWidth: 220 }}
          placeholder={tr(L.section, lang)}
          value={sectionId ?? undefined}
          onChange={setSectionId}
          loading={sections === null}
          options={(sections ?? []).map((s) => ({ value: s.id, label: s.label }))}
          aria-label="section"
        />
        <DatePicker value={day} onChange={(d) => d && setDay(d)} format="DD-MM-YYYY" allowClear={false}
          disabledDate={(d) => d.isAfter(dayjs(), "day")} aria-label="date" />
        {perLecture && (
          <>
            <InputNumber min={1} max={20} placeholder={tr(L.lecture, lang)} value={period} onChange={setPeriod} aria-label="lecture" />
            <div style={{ minWidth: 200 }}>
              <RelationSelect resource="people/subjects" label="name" search value={subject} placeholder={tr(L.subject, lang)}
                onChange={(v) => setSubject(v as number | null)} />
            </div>
          </>
        )}
      </Space>

      {error && <Alert type="error" showIcon message={error} />}
      {loading && <Spin />}
      {!sectionId && sections && sections.length > 0 && <Empty description={tr(L.section, lang)} />}

      {sheet && !loading && (
        sheet.holiday ? (
          <Result status="info" title={`${tr(L.holiday, lang)}: ${sheet.holiday}`} />
        ) : (
          <Card
            size="small"
            title={
              <Space wrap>
                <span>{sheet.section_name} · {day.format("DD-MM-YYYY")}</span>
                {STATUS.map((s) => <Tag key={s.value} color={s.color}>{s.short} {counts[s.value] ?? 0}</Tag>)}
                {unsaved && <Tag>{tr(L.notSaved, lang)}</Tag>}
              </Space>
            }
            extra={<Button size="small" onClick={() => setMarks(Object.fromEntries(sheet.students.map((s) => [s.student, "present"])))}>{tr(L.allPresent, lang)}</Button>}
          >
            <Typography.Paragraph type="secondary" style={{ marginBottom: 8 }}>{tr(L.tapHint, lang)}</Typography.Paragraph>
            <Table<SheetRow>
              rowKey="student"
              size="small"
              pagination={false}
              dataSource={sheet.students}
              onRow={(r) => ({ onClick: () => toggle(r.student), style: { cursor: "pointer", background: marks[r.student] === "absent" ? "#fff1f0" : undefined } })}
              scroll={{ x: true }}
            >
              <Table.Column<SheetRow> title="#" dataIndex="roll_no" width={50} />
              <Table.Column<SheetRow>
                title={tr(t("Student", "छात्र"), lang)}
                render={(_, r) => (
                  <Space size={4} wrap>
                    <span>{r.name}</span>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.admission_no}</Typography.Text>
                    {r.punched && <Tag icon={<IdcardOutlined />} color="cyan">{tr(L.punched, lang)}</Tag>}
                  </Space>
                )}
              />
              <Table.Column<SheetRow>
                title={tr(t("Status", "स्थिति"), lang)}
                render={(_, r) => (
                  <span onClick={(e) => e.stopPropagation()}>
                  <Radio.Group
                    size="small"
                    optionType="button"
                    buttonStyle="solid"
                    value={marks[r.student]}
                    onChange={(e) => setMarks((m) => ({ ...m, [r.student]: e.target.value }))}
                    options={STATUS.map((s) => ({ value: s.value, label: s.short, title: tr(s.label, lang) }))}
                    aria-label={`status-${r.student}`}
                  />
                  </span>
                )}
              />
            </Table>
            <Button type="primary" size="large" block icon={<CheckOutlined />} loading={saving} onClick={save}
              disabled={perLecture && !period} style={{ marginTop: 12 }}>
              {tr(L.save, lang)}
            </Button>
          </Card>
        )
      )}
    </Space>
  );
}
