"use client";

import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Input, InputNumber, Radio, Result, Space, Switch, Table, Tabs, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Build an MCQ test (questions, right answers, marks), open it to students, see scores. */
interface Q { id?: number; sequence: number; text: string; options: string[]; correct: number; marks: string | number }
interface Test { id: number; title: string; section_name: string; subject_name: string; opens_at: string; closes_at: string; time_limit_minutes: number; published: boolean; questions: Q[] }
interface Row { student: number; name: string; admission_no: string; status: string; score: string | null; max_score: string | null; auto_submitted: boolean }
interface Results { rows: Row[]; taken: number; average: string | null }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  questions: t("Questions", "प्रश्न"), results: t("Scores", "अंक"), add: t("Add question", "प्रश्न जोड़ें"), addChoice: t("Add choice", "विकल्प जोड़ें"),
  save: t("Save questions", "प्रश्न सहेजें"), open: t("Open to students", "छात्रों के लिए खोलें"), right: t("Right answer", "सही उत्तर"),
  marks: t("Marks", "अंक"), saved: t("Saved", "सहेजा"), locked: t("Students have started; questions can't change now.", "छात्र आरंभ कर चुके हैं; अब प्रश्न नहीं बदल सकते।"),
  taken: t("Taken", "दी"), avg: t("Average", "औसत"), auto: t("Time ran out", "समय समाप्त"),
  none: t("Open this from the Online tests list.", "ऑनलाइन परीक्षा सूची से खोलें।"),
};

function Builder({ id }: { id: string }) {
  const { lang } = useSession();
  const { message } = App.useApp();
  const [test, setTest] = useState<Test | null>(null);
  const [qs, setQs] = useState<Q[]>([]);
  const [res, setRes] = useState<Results | null>(null);
  const load = useCallback(async () => {
    const tt = await api.get<Test>(`learning/tests/${id}`);
    setTest(tt);
    setQs(tt.questions.length ? tt.questions : [{ sequence: 1, text: "", options: ["", ""], correct: 0, marks: 1 }]);
    setRes(await api.get<Results>(`learning/tests/${id}/results`));
  }, [id]);
  useEffect(() => { void load().catch(() => setTest(null)); }, [load]);
  if (!test) return null;
  const started = (res?.rows ?? []).some((r) => r.status !== "not taken");

  const set = (i: number, patch: Partial<Q>) => setQs((all) => all.map((q, j) => (j === i ? { ...q, ...patch } : q)));
  async function save(extra: Record<string, unknown> = {}) {
    try {
      const body = started ? extra : { ...extra, questions: qs.map((q, i) => ({ ...q, sequence: i + 1, options: q.options.filter((o) => o.trim()) })) };
      await api.patch(`learning/tests/${id}/`, body);
      message.success(tr(L.saved, lang));
      await load();
    } catch (e) { message.error((e as { message?: string }).message ?? "Error"); }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%" }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{test.title}</Typography.Title>
      <Space wrap>
        <Typography.Text type="secondary">{test.section_name} · {test.subject_name} · {dayjs(test.opens_at).format("DD-MM HH:mm")} → {dayjs(test.closes_at).format("DD-MM HH:mm")} · {test.time_limit_minutes} min</Typography.Text>
        <span>{tr(L.open, lang)} <Switch aria-label="published" checked={test.published} onChange={(v) => void save({ published: v })} /></span>
      </Space>
      <Tabs items={[
        { key: "q", label: `${tr(L.questions, lang)} (${qs.length})`, children: (
          <Space direction="vertical" style={{ width: "100%" }}>
            {started && <Alert type="warning" showIcon message={tr(L.locked, lang)} />}
            {qs.map((q, i) => (
              <Card key={i} size="small" title={`Q${i + 1}`} extra={!started && <Button size="small" icon={<DeleteOutlined />} onClick={() => setQs(qs.filter((_, j) => j !== i))} />}>
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Input.TextArea aria-label={`q${i + 1}-text`} disabled={started} value={q.text} autoSize onChange={(e) => set(i, { text: e.target.value })} />
                  <Radio.Group value={q.correct} disabled={started} onChange={(e) => set(i, { correct: e.target.value })} style={{ width: "100%" }}>
                    <Space direction="vertical" style={{ width: "100%" }}>
                      {q.options.map((o, k) => (
                        <Space key={k} style={{ width: "100%" }}>
                          <Radio value={k} aria-label={`q${i + 1}-right-${k}`} />
                          <Input aria-label={`q${i + 1}-opt-${k}`} disabled={started} value={o} style={{ width: 360 }}
                            onChange={(e) => set(i, { options: q.options.map((x, m) => (m === k ? e.target.value : x)) })} />
                        </Space>
                      ))}
                    </Space>
                  </Radio.Group>
                  <Space>
                    {!started && q.options.length < 6 && <Button size="small" onClick={() => set(i, { options: [...q.options, ""] })}>{tr(L.addChoice, lang)}</Button>}
                    <span>{tr(L.marks, lang)} <InputNumber size="small" min={0} disabled={started} value={Number(q.marks)} onChange={(v) => set(i, { marks: v ?? 1 })} /></span>
                  </Space>
                </Space>
              </Card>
            ))}
            {!started && <Space>
              <Button icon={<PlusOutlined />} onClick={() => setQs([...qs, { sequence: qs.length + 1, text: "", options: ["", ""], correct: 0, marks: 1 }])}>{tr(L.add, lang)}</Button>
              <Button type="primary" onClick={() => void save()}>{tr(L.save, lang)}</Button>
            </Space>}
          </Space>
        ) },
        { key: "r", label: tr(L.results, lang), children: (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Typography.Text>{tr(L.taken, lang)}: <b>{res?.taken ?? 0}</b> / {res?.rows.length ?? 0} · {tr(L.avg, lang)}: <b>{res?.average ?? "—"}</b></Typography.Text>
            <Table<Row> size="small" rowKey="student" dataSource={res?.rows ?? []} pagination={false}
              columns={[{ title: "Student", dataIndex: "name" }, { title: "Adm. no.", dataIndex: "admission_no" }, { title: "", dataIndex: "status", render: (v) => <Tag>{v}</Tag> },
                { title: "Score", key: "s", render: (_, r) => r.score !== null ? <span>{r.score} / {r.max_score} {r.auto_submitted && <Tag color="orange">{tr(L.auto, lang)}</Tag>}</span> : "—" }]} />
          </Space>
        ) },
      ]} />
    </Space>
  );
}

function TestPage() {
  const { lang, can } = useSession();
  const id = useSearchParams().get("id");
  if (!can("learning.test.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  return <div style={{ padding: 8 }}>{id ? <Builder id={id} /> : <Alert type="info" showIcon message={tr(L.none, lang)} />}</div>;
}

export default function Page() {
  return <Suspense><TestPage /></Suspense>;
}
