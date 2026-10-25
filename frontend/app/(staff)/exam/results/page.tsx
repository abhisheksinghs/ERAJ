"use client";

import { PrinterOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Result, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

interface ExamRow { id: number; name: string; program: number; weightage: string }
interface Line { subject: number; name: string; display: string; grade: string | null; passed: boolean | null }
interface ResultRow {
  student: number; name: string; admission_no: string; roll_no: string; section_name: string; subjects: Line[];
  total: string; max_total: string; percentage: string; grade: string | null; passed: boolean; pending: boolean;
  rank_section: number; rank_class: number; sgpa?: string;
}
interface ExamResult { exam_name: string; scale_kind: string; subjects: { subject: number; name: string; max: string }[]; rows: ResultRow[] }
interface Analysis {
  students: number; passed: number; pass_percent: string | null;
  subjects: { subject: number; name: string; appeared: number; highest: string | null; lowest: string | null; average: string | null; pass_percent: string | null }[];
  toppers: { student: number; name: string; section: string; percentage: string; rank: number }[];
  failing: { student: number; name: string; section: string; subjects: string[] }[];
}
interface AnnualRow { student: number; name: string; section_name: string; percentage: string; grade: string | null; passed: boolean; rank_class: number;
  subjects: { subject: number; name: string; weighted_percent: string | null; grade: string | null }[] }
interface Annual { exams: { exam: number; name: string; weightage: string }[]; rows: AnnualRow[] }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Results & report cards", "परिणाम एवं रिपोर्ट कार्ड"),
  exam: t("Exam", "परीक्षा"),
  section: t("Section (all if blank)", "अनुभाग (रिक्त = सभी)"),
  results: t("Results", "परिणाम"),
  analysis: t("Analysis", "विश्लेषण"),
  annual: t("Annual result", "वार्षिक परिणाम"),
  cards: t("Print report cards", "रिपोर्ट कार्ड प्रिंट करें"),
  annualCards: t("Print annual cards", "वार्षिक कार्ड प्रिंट करें"),
  pickExams: t("Exams to combine (with weightage)", "मिलाने हेतु परीक्षाएँ (भारांक सहित)"),
  pass: t("Pass", "उत्तीर्ण"),
  fail: t("Fail", "अनुत्तीर्ण"),
  pending: t("Pending", "लंबित"),
};

const resultTag = (r: { passed: boolean; pending?: boolean }, lang: "en" | "hi") =>
  r.pending ? <Tag>{tr(L.pending, lang)}</Tag> : r.passed ? <Tag color="green">{tr(L.pass, lang)}</Tag> : <Tag color="red">{tr(L.fail, lang)}</Tag>;

export default function Results() {
  const { lang, can } = useSession();
  const [exam, setExam] = useState<ExamRow | null>(null);
  const [section, setSection] = useState<number | null>(null);
  const [result, setResult] = useState<ExamResult | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [classExams, setClassExams] = useState<ExamRow[]>([]);
  const [annualIds, setAnnualIds] = useState<number[]>([]);
  const [annual, setAnnual] = useState<Annual | null>(null);
  const [error, setError] = useState<string | null>(null);

  const sq = section ? `&section=${section}` : "";
  const load = useCallback(async () => {
    if (!exam) return;
    setError(null);
    try {
      const [r, a, list] = await Promise.all([
        api.get<ExamResult>(`exam/results/exam?exam=${exam.id}${sq}`),
        api.get<Analysis>(`exam/results/analysis?exam=${exam.id}${sq}`),
        api.get<{ results: ExamRow[] }>(`exam/exams?program=${exam.program}&page_size=50`),
      ]);
      setResult(r);
      setAnalysis(a);
      setClassExams(list.results);
      setAnnualIds((ids) => (ids.length ? ids : list.results.filter((e) => Number(e.weightage) > 0).map((e) => e.id)));
    } catch (e) {
      setError((e as { message?: string }).message ?? "Error");
    }
  }, [exam, sq]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!annualIds.length) {
      setAnnual(null);
      return;
    }
    api.get<Annual>(`exam/results/annual?exams=${annualIds.join(",")}${sq}`).then(setAnnual).catch((e) => {
      setAnnual(null);
      setError((e as { message?: string }).message ?? "Error");
    });
  }, [annualIds, sq]);

  if (!can("exam.result.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Space wrap>
        <div style={{ minWidth: 220 }}>
          <RelationSelect resource="exam/exams" label="label" search value={exam?.id ?? null} placeholder={tr(L.exam, lang)}
            onChange={async (v) => {
              setAnnualIds([]);
              setSection(null);
              setExam(v ? await api.get<ExamRow>(`exam/exams/${v}`) : null);
            }} />
        </div>
        <div style={{ minWidth: 220 }}>
          <RelationSelect resource="people/sections" label="label" value={section} placeholder={tr(L.section, lang)}
            filters={[{ field: "program", value: exam?.program }]} enabled={!!exam} onChange={(v) => setSection(v as number | null)} />
        </div>
        {exam && section && (
          <Button icon={<PrinterOutlined />} href={`${API}/exam/results/report-cards?exam=${exam.id}&section=${section}`} target="_blank">
            {tr(L.cards, lang)}
          </Button>
        )}
      </Space>
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}

      {result && (
        <Tabs
          items={[
            {
              key: "results",
              label: tr(L.results, lang),
              children: (
                <Table<ResultRow>
                  rowKey="student" size="small" dataSource={result.rows} pagination={{ pageSize: 50 }} scroll={{ x: true }}
                  columns={[
                    { title: tr(t("Rank (sec/class)", "स्थान (अनु./कक्षा)"), lang), render: (_, r) => `${r.rank_section} / ${r.rank_class}`, width: 90 },
                    { title: tr(t("Student", "छात्र"), lang), dataIndex: "name", fixed: "left" },
                    { title: tr(t("Section", "अनुभाग"), lang), dataIndex: "section_name" },
                    ...result.subjects.map((s) => ({
                      title: `${s.name} /${Number(s.max)}`, key: String(s.subject), align: "center" as const,
                      render: (_: unknown, r: ResultRow) => {
                        const ln = r.subjects.find((x) => x.subject === s.subject);
                        if (!ln) return "";
                        return <span style={{ color: ln.passed === false ? "#b42318" : undefined, fontWeight: ln.display === "AB" ? 700 : 400 }}>
                          {ln.display}{ln.grade ? ` · ${ln.grade}` : ""}</span>;
                      },
                    })),
                    { title: tr(t("Total", "योग"), lang), render: (_, r) => `${Number(r.total)} / ${Number(r.max_total)}` },
                    { title: "%", dataIndex: "percentage", align: "right" as const },
                    ...(result.scale_kind === "credit" ? [{ title: "SGPA", dataIndex: "sgpa" }] : []),
                    { title: tr(t("Grade", "ग्रेड"), lang), dataIndex: "grade" },
                    { title: tr(t("Result", "परिणाम"), lang), render: (_, r) => resultTag(r, lang) },
                  ]}
                />
              ),
            },
            {
              key: "analysis",
              label: tr(L.analysis, lang),
              children: analysis && (
                <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                  <Row gutter={16}>
                    <Col xs={8}><Statistic title={tr(t("Students", "छात्र"), lang)} value={analysis.students} /></Col>
                    <Col xs={8}><Statistic title={tr(L.pass, lang)} value={analysis.passed} /></Col>
                    <Col xs={8}><Statistic title={tr(t("Pass %", "उत्तीर्ण %"), lang)} value={analysis.pass_percent ?? "—"} /></Col>
                  </Row>
                  <Table rowKey="subject" size="small" pagination={false} dataSource={analysis.subjects}
                    columns={[
                      { title: tr(t("Subject", "विषय"), lang), dataIndex: "name" },
                      { title: tr(t("Appeared", "सम्मिलित"), lang), dataIndex: "appeared", align: "right" },
                      { title: tr(t("Highest", "अधिकतम"), lang), dataIndex: "highest", align: "right" },
                      { title: tr(t("Lowest", "न्यूनतम"), lang), dataIndex: "lowest", align: "right" },
                      { title: tr(t("Average", "औसत"), lang), dataIndex: "average", align: "right" },
                      { title: tr(t("Pass %", "उत्तीर्ण %"), lang), dataIndex: "pass_percent", align: "right" },
                    ]} />
                  <Row gutter={16}>
                    <Col xs={24} md={12}>
                      <Card size="small" title={tr(t("Toppers", "शीर्ष छात्र"), lang)}>
                        <Table rowKey="student" size="small" pagination={false} dataSource={analysis.toppers}
                          columns={[{ title: "#", dataIndex: "rank" }, { title: tr(t("Student", "छात्र"), lang), dataIndex: "name" },
                            { title: tr(t("Section", "अनुभाग"), lang), dataIndex: "section" }, { title: "%", dataIndex: "percentage" }]} />
                      </Card>
                    </Col>
                    <Col xs={24} md={12}>
                      <Card size="small" title={tr(t("Failing in one or more subjects", "एक या अधिक विषयों में अनुत्तीर्ण"), lang)}>
                        <Table rowKey="student" size="small" pagination={false} dataSource={analysis.failing}
                          columns={[{ title: tr(t("Student", "छात्र"), lang), dataIndex: "name" },
                            { title: tr(t("Section", "अनुभाग"), lang), dataIndex: "section" },
                            { title: tr(t("Subjects", "विषय"), lang), dataIndex: "subjects", render: (v: string[]) => v.join(", ") }]} />
                      </Card>
                    </Col>
                  </Row>
                </Space>
              ),
            },
            {
              key: "annual",
              label: tr(L.annual, lang),
              children: (
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Space wrap>
                    <Select mode="multiple" style={{ minWidth: 320 }} placeholder={tr(L.pickExams, lang)} value={annualIds}
                      onChange={setAnnualIds}
                      options={classExams.map((e) => ({ value: e.id, label: `${e.name} (${Number(e.weightage)}%)`, disabled: Number(e.weightage) <= 0 }))} />
                    {annualIds.length > 0 && (
                      <Button icon={<PrinterOutlined />} href={`${API}/exam/results/annual-cards?exams=${annualIds.join(",")}${sq}`} target="_blank">
                        {tr(L.annualCards, lang)}
                      </Button>
                    )}
                  </Space>
                  {annual && (
                    <Table<AnnualRow>
                      rowKey="student" size="small" dataSource={annual.rows} pagination={{ pageSize: 50 }} scroll={{ x: true }}
                      columns={[
                        { title: "#", dataIndex: "rank_class", width: 50 },
                        { title: tr(t("Student", "छात्र"), lang), dataIndex: "name" },
                        { title: tr(t("Section", "अनुभाग"), lang), dataIndex: "section_name" },
                        ...(annual.rows[0]?.subjects ?? []).map((s, i) => ({
                          title: s.name, key: String(s.subject), align: "center" as const,
                          render: (_: unknown, r: AnnualRow) => {
                            const x = r.subjects[i];
                            return x?.weighted_percent ? `${x.weighted_percent}%${x.grade ? ` · ${x.grade}` : ""}` : "—";
                          },
                        })),
                        { title: tr(t("Final %", "अंतिम %"), lang), dataIndex: "percentage", align: "right" as const },
                        { title: tr(t("Grade", "ग्रेड"), lang), dataIndex: "grade" },
                        { title: tr(t("Result", "परिणाम"), lang), render: (_, r) => resultTag(r, lang) },
                      ]}
                    />
                  )}
                </Space>
              ),
            },
          ]}
        />
      )}
    </Space>
  );
}
