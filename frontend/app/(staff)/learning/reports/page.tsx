"use client";

import { DatePicker, Progress, Result, Space, Table, Tabs, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

interface SectionRate { section: string; homework: number; expected: number; submitted: number; late: number; rate: number }
interface StudentRate { student: number; name: string; homework: number; submitted: number; late: number; pending: number; rate: number }
interface Pending { homework: number; title: string; section: string; subject: string; due_date: string; missing: number; students: string }
interface Score { test: number; title: string; section: string; subject: string; opens_at: string; taken: number; of: number; average: string | null }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Learning reports", "शिक्षण रिपोर्ट"), bySection: t("Submission rate by section", "अनुभागवार जमा दर"), byStudent: t("By student", "छात्रवार"),
  pending: t("Pending submissions", "लंबित जमा"), scores: t("Test scores", "परीक्षा अंक"), section: t("Section", "अनुभाग"),
};

function useGet<R>(path: string | null) {
  const [data, setData] = useState<R | null>(null);
  useEffect(() => { if (path) void api.get<R>(path).then(setData).catch(() => setData(null)); else setData(null); }, [path]);
  return data;
}

export default function LearningReports() {
  const { lang, can, allBranches } = useSession();
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf("month"), dayjs()]);
  const [section, setSection] = useState<number | null>(null);
  const ok = can("learning.report.view") && !allBranches;
  const q = `from=${range[0].format("YYYY-MM-DD")}&to=${range[1].format("YYYY-MM-DD")}`;
  const rates = useGet<SectionRate[]>(ok ? `learning/reports/submissions?${q}` : null);
  const students = useGet<StudentRate[]>(ok && section ? `learning/reports/submissions?${q}&section=${section}&by=student` : null);
  const pending = useGet<Pending[]>(ok ? "learning/reports/pending" : null);
  const scores = useGet<Score[]>(ok ? `learning/reports/tests${section ? `?section=${section}` : ""}` : null);
  if (!can("learning.report.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;
  const bar = (v: number) => <Progress percent={v} size="small" style={{ width: 140 }} />;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Space wrap>
        <DatePicker.RangePicker value={range} format="DD-MM-YYYY" allowClear={false} onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])} />
        <RelationSelect resource="people/sections" label="label" search value={section} onChange={(v) => setSection((v as number) ?? null)}
          placeholder={tr(L.section, lang)} style={{ minWidth: 200 }} />
      </Space>
      <Tabs items={[
        { key: "s", label: tr(L.bySection, lang), children: <Table<SectionRate> size="small" rowKey="section" pagination={false} dataSource={rates ?? []}
          columns={[{ title: "Section", dataIndex: "section" }, { title: "Homework", dataIndex: "homework" },
            { title: "Submitted", key: "n", render: (_, r) => `${r.submitted} / ${r.expected}` }, { title: "Late", dataIndex: "late" },
            { title: "", dataIndex: "rate", render: bar }]} /> },
        { key: "st", label: tr(L.byStudent, lang), disabled: !section, children: <Table<StudentRate> size="small" rowKey="student" pagination={false} dataSource={students ?? []}
          columns={[{ title: "Student", dataIndex: "name" }, { title: "Submitted", key: "n", render: (_, r) => `${r.submitted} / ${r.homework}` },
            { title: "Late", dataIndex: "late" }, { title: "Pending", dataIndex: "pending" }, { title: "", dataIndex: "rate", render: bar }]} /> },
        { key: "p", label: tr(L.pending, lang), children: <Table<Pending> size="small" rowKey="homework" pagination={false} dataSource={pending ?? []}
          columns={[{ title: "Homework", dataIndex: "title" }, { title: "Section", dataIndex: "section" }, { title: "Subject", dataIndex: "subject" },
            { title: "Due", dataIndex: "due_date", render: (v) => dayjs(v).format("DD-MM-YYYY") }, { title: "Missing", dataIndex: "missing" },
            { title: "Students", dataIndex: "students" }]} /> },
        { key: "t", label: tr(L.scores, lang), children: <Table<Score> size="small" rowKey="test" pagination={false} dataSource={scores ?? []}
          columns={[{ title: "Test", dataIndex: "title" }, { title: "Section", dataIndex: "section" }, { title: "Subject", dataIndex: "subject" },
            { title: "Taken", key: "n", render: (_, r) => `${r.taken} / ${r.of}` }, { title: "Average", dataIndex: "average", render: (v) => v ?? "—" }]} /> },
      ]} />
    </Space>
  );
}
