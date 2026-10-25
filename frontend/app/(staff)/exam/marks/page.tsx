"use client";

import { LockOutlined, SaveOutlined, UnlockOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Input, InputNumber, Modal, Result, Select, Space, Table, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Marks grid for one exam subject and section; lock / unlock the section. */
interface Exam { id: number; program: number; name: string }
interface Row { student: number; name: string; admission_no: string; roll_no: string; theory: string | null; practical: string | null; status: string | null }
interface Grid {
  exam: number; exam_name: string; subject: string; section: number; section_name: string; locked: boolean;
  max_theory: string; max_practical: string; pass_marks: string; rows: Row[];
}
type Edit = { theory: number | null; practical: number | null; status: string };

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Enter marks", "अंक दर्ज करें"),
  exam: t("Exam", "परीक्षा"),
  subject: t("Subject", "विषय"),
  section: t("Section", "अनुभाग"),
  theory: t("Theory", "सैद्धांतिक"),
  practical: t("Practical", "प्रायोगिक"),
  status: t("Attendance", "उपस्थिति"),
  save: t("Save marks", "अंक सहेजें"),
  lock: t("Lock section", "अनुभाग लॉक करें"),
  unlock: t("Unlock", "अनलॉक"),
  locked: t("Marks are locked. Only Admin can unlock them.", "अंक लॉक हैं। केवल प्रशासक अनलॉक कर सकते हैं।"),
  reason: t("Reason for unlocking", "अनलॉक करने का कारण"),
  pass: t("Pass marks", "उत्तीर्णांक"),
  pick: t("Choose the exam, subject and section", "परीक्षा, विषय और अनुभाग चुनें"),
  lockConfirm: t("Lock this section's marks for the whole exam? Teachers can no longer change them.",
    "पूरी परीक्षा के लिए इस अनुभाग के अंक लॉक करें? शिक्षक बदलाव नहीं कर सकेंगे।"),
};
const STATUS = [
  { value: "present", label: t("Present", "उपस्थित") },
  { value: "absent", label: t("Absent (AB)", "अनुपस्थित (AB)") },
  { value: "exempt", label: t("Exempt", "छूट") },
];

export default function MarksEntry() {
  const { lang, can, allBranches } = useSession();
  const { message, modal } = App.useApp();
  const [exam, setExam] = useState<Exam | null>(null);
  const [examSubject, setExamSubject] = useState<number | null>(null);
  const [section, setSection] = useState<number | null>(null);
  const [grid, setGrid] = useState<Grid | null>(null);
  const [edits, setEdits] = useState<Record<number, Edit>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [unlockOpen, setUnlockOpen] = useState(false);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    if (!examSubject || !section) {
      setGrid(null);
      return;
    }
    setError(null);
    try {
      const g = await api.get<Grid>(`exam/marks/grid?exam_subject=${examSubject}&section=${section}`);
      setGrid(g);
      setEdits(Object.fromEntries(g.rows.map((r) => [r.student, {
        theory: r.theory === null ? null : Number(r.theory), practical: r.practical === null ? null : Number(r.practical),
        status: r.status ?? "present",
      }])));
    } catch (e) {
      setGrid(null);
      setError((e as { message?: string }).message ?? "Error");
    }
  }, [examSubject, section]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!can("exam.marks.enter")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  const fail = (e: unknown) => {
    const err = e as { message?: string; errors?: Record<string, string[]> };
    message.error((err.errors ? Object.values(err.errors).flat()[0] : undefined) ?? err.message ?? "Error");
  };

  async function save() {
    if (!grid) return;
    setSaving(true);
    try {
      const rows = Object.entries(edits)
        .filter(([, e]) => e.status !== "present" || e.theory !== null || e.practical !== null)
        .map(([student, e]) => ({ student: Number(student), status: e.status, theory: e.status === "present" ? e.theory : null,
          practical: e.status === "present" && Number(grid.max_practical) > 0 ? e.practical : null }));
      const res = await api.post<{ saved: number }>("exam/marks/save", { exam_subject: examSubject, section, rows });
      message.success(`${tr(UI.done, lang)}: ${res.saved}`);
      await load();
    } catch (e) {
      fail(e);
    } finally {
      setSaving(false);
    }
  }

  const hasPractical = grid ? Number(grid.max_practical) > 0 : false;
  const set = (sid: number, patch: Partial<Edit>) => setEdits((m) => ({ ...m, [sid]: { ...m[sid], ...patch } }));

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Space wrap>
        <div style={{ minWidth: 220 }}>
          <RelationSelect resource="exam/exams" label="label" search value={exam?.id ?? null} placeholder={tr(L.exam, lang)}
            onChange={async (v) => {
              setExamSubject(null);
              setSection(null);
              setExam(v ? await api.get<Exam>(`exam/exams/${v}`) : null);
            }} />
        </div>
        <div style={{ minWidth: 200 }}>
          <RelationSelect resource="exam/exam-subjects" label="subject_name" value={examSubject} placeholder={tr(L.subject, lang)}
            filters={[{ field: "exam", value: exam?.id }]} enabled={!!exam} onChange={(v) => setExamSubject(v as number | null)} />
        </div>
        <div style={{ minWidth: 200 }}>
          <RelationSelect resource="people/sections" label="label" value={section} placeholder={tr(L.section, lang)}
            filters={[{ field: "program", value: exam?.program }]} enabled={!!exam} onChange={(v) => setSection(v as number | null)} />
        </div>
      </Space>
      {error && <Alert type="error" showIcon message={error} />}
      {!grid && !error && <Alert type="info" message={tr(L.pick, lang)} />}

      {grid && (
        <Card
          size="small"
          title={
            <Space wrap>
              <span>{grid.exam_name} · {grid.subject} · {grid.section_name}</span>
              <Tag>{tr(L.theory, lang)} /{Number(grid.max_theory)}</Tag>
              {hasPractical && <Tag>{tr(L.practical, lang)} /{Number(grid.max_practical)}</Tag>}
              <Tag>{tr(L.pass, lang)} {Number(grid.pass_marks)}</Tag>
              {grid.locked && <Tag icon={<LockOutlined />} color="red">Locked</Tag>}
            </Space>
          }
          extra={
            grid.locked ? (
              can("exam.marks.unlock") && <Button icon={<UnlockOutlined />} onClick={() => setUnlockOpen(true)}>{tr(L.unlock, lang)}</Button>
            ) : (
              can("exam.marks.lock") && (
                <Button icon={<LockOutlined />} onClick={() => modal.confirm({
                  title: tr(L.lockConfirm, lang),
                  onOk: async () => {
                    try {
                      await api.post("exam/marks/lock", { exam: grid.exam, section: grid.section });
                      await load();
                    } catch (e) {
                      fail(e);
                    }
                  },
                })}>{tr(L.lock, lang)}</Button>
              )
            )
          }
        >
          {grid.locked && <Alert type="warning" showIcon message={tr(L.locked, lang)} style={{ marginBottom: 8 }} />}
          <Table<Row> rowKey="student" size="small" pagination={false} dataSource={grid.rows} scroll={{ x: true }}>
            <Table.Column<Row> title="#" dataIndex="roll_no" width={50} />
            <Table.Column<Row> title={tr(t("Student", "छात्र"), lang)} render={(_, r) => <span>{r.name} <Typography.Text type="secondary">{r.admission_no}</Typography.Text></span>} />
            <Table.Column<Row>
              title={tr(L.status, lang)}
              render={(_, r) => (
                <Select size="small" style={{ width: 140 }} disabled={grid.locked} value={edits[r.student]?.status}
                  onChange={(v) => set(r.student, { status: v })} options={STATUS.map((s) => ({ value: s.value, label: tr(s.label, lang) }))}
                  aria-label={`status-${r.student}`} />
              )}
            />
            <Table.Column<Row>
              title={`${tr(L.theory, lang)} /${Number(grid.max_theory)}`}
              render={(_, r) => edits[r.student]?.status === "present" ? (
                <InputNumber size="small" min={0} max={Number(grid.max_theory)} step={0.5} disabled={grid.locked}
                  value={edits[r.student]?.theory} onChange={(v) => set(r.student, { theory: v })} aria-label={`theory-${r.student}`} />
              ) : <Tag>{edits[r.student]?.status === "absent" ? "AB" : "EX"}</Tag>}
            />
            {hasPractical && (
              <Table.Column<Row>
                title={`${tr(L.practical, lang)} /${Number(grid.max_practical)}`}
                render={(_, r) => edits[r.student]?.status === "present" ? (
                  <InputNumber size="small" min={0} max={Number(grid.max_practical)} step={0.5} disabled={grid.locked}
                    value={edits[r.student]?.practical} onChange={(v) => set(r.student, { practical: v })} />
                ) : null}
              />
            )}
          </Table>
          {!grid.locked && (
            <Button type="primary" size="large" block icon={<SaveOutlined />} loading={saving} onClick={save} style={{ marginTop: 12 }}>
              {tr(L.save, lang)}
            </Button>
          )}
        </Card>
      )}

      <Modal open={unlockOpen} title={tr(L.reason, lang)} okText={tr(L.unlock, lang)} okButtonProps={{ disabled: !reason.trim() }}
        onCancel={() => setUnlockOpen(false)}
        onOk={async () => {
          try {
            await api.post("exam/marks/unlock", { exam: grid?.exam, section: grid?.section, reason: reason.trim() });
            setUnlockOpen(false);
            setReason("");
            await load();
          } catch (e) {
            fail(e);
          }
        }}>
        <Input.TextArea rows={3} maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} />
      </Modal>
    </Space>
  );
}
