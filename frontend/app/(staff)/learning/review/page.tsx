"use client";

import { PaperClipOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Input, Result, Space, Table, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Homework: attach files, see who submitted, grade with remarks. Online class: who opened the link. */
interface FileRow { id: number; name: string; size: number }
interface Homework { id: number; title: string; section_name: string; subject_name: string; due_date: string; description: string; files: FileRow[] }
interface Sub { id: number; student_name: string; admission_no: string; text: string; submitted_at: string; late: boolean; grade: string; remarks: string; reviewed_at: string | null; files: FileRow[] }
interface JoinRow { student: number; name: string; admission_no: string; opened_at: string | null; opens: number }
interface Joins { title: string; joined: number; of: number; rows: JoinRow[] }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Check homework", "गृहकार्य जाँचें"), files: t("Attachments", "संलग्न फ़ाइलें"), attach: t("Attach files (PDF, photo, Word, slides)", "फ़ाइलें जोड़ें"),
  subs: t("Submissions", "जमा कार्य"), late: t("Late", "विलंब"), grade: t("Grade", "ग्रेड"), remarks: t("Remarks", "टिप्पणी"), save: t("Save", "सहेजें"),
  checked: t("Checked", "जाँचा"), none: t("Open this from the Homework or Online classes list.", "गृहकार्य या ऑनलाइन कक्षा सूची से खोलें।"),
  joined: t("Opened the class link", "कक्षा लिंक खोला"), notJoined: t("Did not open", "नहीं खोला"), saved: t("Saved", "सहेजा"),
  due: t("Due", "अंतिम तिथि"),
};

function GradeCell({ sub, onSaved }: { sub: Sub; onSaved: () => void }) {
  const { lang } = useSession();
  const { message } = App.useApp();
  const [grade, setGrade] = useState(sub.grade);
  const [remarks, setRemarks] = useState(sub.remarks);
  return (
    <Space.Compact style={{ width: "100%" }}>
      <Input aria-label={`grade-${sub.id}`} style={{ width: 70 }} value={grade} maxLength={10} placeholder={tr(L.grade, lang)} onChange={(e) => setGrade(e.target.value)} />
      <Input aria-label={`remarks-${sub.id}`} value={remarks} maxLength={500} placeholder={tr(L.remarks, lang)} onChange={(e) => setRemarks(e.target.value)} />
      <Button type="primary" onClick={async () => {
        try {
          await api.post(`learning/submissions/${sub.id}/grade`, { grade, remarks });
          message.success(tr(L.saved, lang));
          onSaved();
        } catch (e) { message.error((e as { message?: string }).message ?? "Error"); }
      }}>{tr(L.save, lang)}</Button>
    </Space.Compact>
  );
}

function HomeworkReview({ id }: { id: string }) {
  const { lang } = useSession();
  const { message } = App.useApp();
  const [hw, setHw] = useState<Homework | null>(null);
  const [subs, setSubs] = useState<Sub[]>([]);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    setHw(await api.get<Homework>(`learning/homework/${id}`));
    setSubs((await api.get<{ results: Sub[] }>(`learning/submissions?homework=${id}&page_size=200`)).results);
  }, [id]);
  useEffect(() => { void load().catch(() => setHw(null)); }, [load]);
  if (!hw) return null;

  async function attach(files: FileList | null) {
    if (!files?.length) return;
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    setBusy(true);
    try { await api.post(`learning/homework/${id}/attach`, fd); await load(); message.success(tr(L.saved, lang)); }
    catch (e) { message.error((e as { message?: string }).message ?? "Error"); }
    finally { setBusy(false); }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{hw.title}</Typography.Title>
      <Typography.Text type="secondary">{hw.section_name} · {hw.subject_name} · {tr(L.due, lang)} {dayjs(hw.due_date).format("DD-MM-YYYY")}</Typography.Text>
      {hw.description && <Typography.Paragraph>{hw.description}</Typography.Paragraph>}
      <Card size="small" title={tr(L.files, lang)}>
        <Space direction="vertical">
          {hw.files.map((f) => <a key={f.id} href={`${API}/learning/homework/${hw.id}/file?file=${f.id}`}><PaperClipOutlined /> {f.name}</a>)}
          <label className="ant-btn" style={{ cursor: "pointer" }}>
            <UploadOutlined /> {tr(L.attach, lang)}
            <input data-testid="attach" type="file" multiple hidden disabled={busy} accept=".pdf,.jpg,.jpeg,.png,.docx,.pptx" onChange={(e) => void attach(e.target.files)} />
          </label>
        </Space>
      </Card>
      <Card size="small" title={`${tr(L.subs, lang)} (${subs.length})`}>
        <Table<Sub> size="small" rowKey="id" dataSource={subs} pagination={false}
          columns={[
            { title: "Student", dataIndex: "student_name", render: (v, r) => <span>{v} <Typography.Text type="secondary">{r.admission_no}</Typography.Text></span> },
            { title: "Submitted", dataIndex: "submitted_at", render: (v, r) => <span>{dayjs(v).format("DD-MM HH:mm")} {r.late && <Tag color="orange">{tr(L.late, lang)}</Tag>}</span> },
            { title: "Work", key: "w", render: (_, r) => <Space direction="vertical" size={0}>{r.text && <span>{r.text}</span>}
              {r.files.map((f) => <a key={f.id} href={`${API}/learning/submissions/${r.id}/file?file=${f.id}`}><PaperClipOutlined /> {f.name}</a>)}</Space> },
            { title: tr(L.grade, lang), key: "g", width: 380, render: (_, r) => <Space direction="vertical" size={2} style={{ width: "100%" }}>
              {r.reviewed_at && <Tag color="green">{tr(L.checked, lang)}</Tag>}<GradeCell sub={r} onSaved={() => void load()} /></Space> },
          ]} />
      </Card>
    </Space>
  );
}

function ClassJoins({ id }: { id: string }) {
  const { lang } = useSession();
  const [data, setData] = useState<Joins | null>(null);
  useEffect(() => { void api.get<Joins>(`learning/classes/${id}/joins`).then(setData).catch(() => setData(null)); }, [id]);
  if (!data) return null;
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{data.title}</Typography.Title>
      <Typography.Text>{tr(L.joined, lang)}: <b>{data.joined}</b> / {data.of}</Typography.Text>
      <Table<JoinRow> size="small" rowKey="student" dataSource={data.rows} pagination={false}
        columns={[{ title: "Student", dataIndex: "name" }, { title: "Adm. no.", dataIndex: "admission_no" },
          { title: "", dataIndex: "opened_at", render: (v: string | null, r) => v ? <Tag color="green">{dayjs(v).format("HH:mm")} ×{r.opens}</Tag> : <Tag>{tr(L.notJoined, lang)}</Tag> }]} />
    </Space>
  );
}

function Review() {
  const { lang, can } = useSession();
  const sp = useSearchParams();
  const homework = sp.get("homework");
  const cls = sp.get("class");
  if (!can("learning.submission.view") && !can("learning.class.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  return (
    <div style={{ padding: 8 }}>
      {homework ? <HomeworkReview id={homework} /> : cls ? <ClassJoins id={cls} /> : <Alert type="info" showIcon message={tr(L.none, lang)} />}
    </div>
  );
}

export default function Page() {
  return <Suspense><Review /></Suspense>;
}
