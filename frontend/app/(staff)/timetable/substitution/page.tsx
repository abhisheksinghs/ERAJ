"use client";

import { CheckOutlined, PrinterOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, DatePicker, Empty, Form, Input, Result, Select, Space, Table, Tabs, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** The day's absent teachers → their periods → pick a suggested free teacher → confirm. */
interface Suggestion { staff: number; name: string; same_subject: boolean; periods_that_day: number }
interface Period {
  entry: number; section_name: string; subject: string; teacher: number; teacher_name: string; slot: string;
  start: string; end: string; substitute: number | null; substitute_name: string | null; suggestions: Suggestion[];
}
interface Absence { id: number; staff: number; staff_name: string; reason: string }
interface Register { per_teacher: { staff: number; name: string; periods: number }[]; rows: { date: string; section_name: string; slot: string; subject: string; absent: string; substitute: string }[] }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Substitutes", "प्रतिस्थापक"),
  absent: t("Teachers away", "अनुपस्थित शिक्षक"),
  markAway: t("Mark a teacher away", "शिक्षक को अनुपस्थित दर्ज करें"),
  reason: t("Reason", "कारण"),
  periods: t("Periods to cover", "प्रतिस्थापन हेतु कालांश"),
  noPeriods: t("No periods to cover for this date.", "इस तिथि के लिए कोई कालांश नहीं।"),
  choose: t("Choose a free teacher", "उपलब्ध शिक्षक चुनें"),
  confirm: t("Confirm", "पुष्टि करें"),
  covered: t("Covered by", "प्रतिस्थापक"),
  sameSubject: t("same subject", "वही विषय"),
  periodsThatDay: t("periods that day", "कालांश उस दिन"),
  register: t("Monthly register", "मासिक रजिस्टर"),
  print: t("Print", "प्रिंट"),
};

export default function Substitution() {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const [day, setDay] = useState<Dayjs>(dayjs());
  const [absences, setAbsences] = useState<Absence[]>([]);
  const [periods, setPeriods] = useState<Period[]>([]);
  const [picked, setPicked] = useState<Record<number, number>>({});
  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [register, setRegister] = useState<Register | null>(null);
  const [form] = Form.useForm();

  const d = day.format("YYYY-MM-DD");
  const load = useCallback(async () => {
    const [abs, cover] = await Promise.all([
      api.get<{ results: Absence[] }>(`timetable/absences?date=${d}&page_size=100`),
      api.get<{ periods: Period[] }>(`timetable/substitutions/to-cover?date=${d}`),
    ]);
    setAbsences(abs.results);
    setPeriods(cover.periods);
    setPicked(Object.fromEntries(cover.periods.filter((p) => !p.substitute && p.suggestions[0]).map((p) => [p.entry, p.suggestions[0].staff])));
  }, [d]);
  useEffect(() => {
    if (!allBranches) void load().catch(() => undefined);
  }, [load, allBranches]);
  useEffect(() => {
    api.get<Register>(`timetable/substitutions/register?month=${month.format("YYYY-MM")}`).then(setRegister).catch(() => setRegister(null));
  }, [month, periods]);

  if (!can("timetable.substitution.manage")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  const fail = (e: unknown) => {
    const err = e as { message?: string; errors?: Record<string, string[]> };
    message.error((err.errors ? Object.values(err.errors).flat()[0] : undefined) ?? err.message ?? "Error", 6);
  };

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Tabs items={[
        {
          key: "day",
          label: day.format("DD-MM-YYYY"),
          children: (
            <Space direction="vertical" size="middle" style={{ width: "100%" }}>
              <DatePicker value={day} onChange={(v) => v && setDay(v)} format="DD-MM-YYYY" allowClear={false} aria-label="date" />
              <Card size="small" title={tr(L.absent, lang)}>
                <Space wrap style={{ marginBottom: 8 }}>
                  {absences.map((a) => (
                    <Tag key={a.id} closable color="orange" onClose={async (e) => {
                      e.preventDefault();
                      await fetch(`/api/proxy/timetable/absences/${a.id}`, { method: "DELETE", credentials: "same-origin" });
                      await load();
                    }}>{a.staff_name}{a.reason ? ` — ${a.reason}` : ""}</Tag>
                  ))}
                </Space>
                <Form form={form} layout="inline" onFinish={async (v) => {
                  try {
                    await api.post("timetable/absences", { staff: v.staff, date: d, reason: v.reason ?? "" });
                    form.resetFields();
                    await load();
                  } catch (e) {
                    fail(e);
                  }
                }}>
                  <Form.Item name="staff" rules={[{ required: true }]} style={{ minWidth: 240 }}>
                    <RelationSelect resource="people/staff" label="full_name" search placeholder={tr(L.markAway, lang)} />
                  </Form.Item>
                  <Form.Item name="reason"><Input placeholder={tr(L.reason, lang)} /></Form.Item>
                  <Button htmlType="submit">{tr(L.markAway, lang)}</Button>
                </Form>
              </Card>
              <Card size="small" title={tr(L.periods, lang)}>
                {periods.length === 0 ? <Empty description={tr(L.noPeriods, lang)} /> : (
                  <Table<Period> rowKey="entry" size="small" pagination={false} dataSource={periods} scroll={{ x: true }}
                    columns={[
                      { title: tr(t("Period", "कालांश"), lang), render: (_, p) => `${p.slot} (${p.start.slice(0, 5)}–${p.end.slice(0, 5)})` },
                      { title: tr(t("Class", "कक्षा"), lang), dataIndex: "section_name" },
                      { title: tr(t("Subject", "विषय"), lang), dataIndex: "subject" },
                      { title: tr(t("Away", "अनुपस्थित"), lang), dataIndex: "teacher_name" },
                      {
                        title: tr(L.covered, lang),
                        render: (_, p) => p.substitute_name ? <Tag color="green" icon={<CheckOutlined />}>{p.substitute_name}</Tag> : (
                          p.suggestions.length === 0 ? <Alert type="warning" message={tr(t("No free teacher", "कोई शिक्षक उपलब्ध नहीं"), lang)} /> : (
                            <Space>
                              <Select style={{ minWidth: 240 }} value={picked[p.entry]} placeholder={tr(L.choose, lang)} aria-label={`substitute-${p.entry}`}
                                onChange={(v) => setPicked((m) => ({ ...m, [p.entry]: v }))}
                                options={p.suggestions.map((s) => ({
                                  value: s.staff,
                                  label: `${s.name}${s.same_subject ? ` · ${tr(L.sameSubject, lang)}` : ""} · ${s.periods_that_day} ${tr(L.periodsThatDay, lang)}`,
                                }))} />
                              <Button type="primary" disabled={!picked[p.entry]} onClick={async () => {
                                try {
                                  await api.post("timetable/substitutions/confirm", { entry: p.entry, date: d, substitute: picked[p.entry] });
                                  await load();
                                } catch (e) {
                                  fail(e);
                                }
                              }}>{tr(L.confirm, lang)}</Button>
                            </Space>
                          )
                        ),
                      },
                    ]} />
                )}
              </Card>
            </Space>
          ),
        },
        {
          key: "register",
          label: tr(L.register, lang),
          children: (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space>
                <DatePicker picker="month" value={month} onChange={(m) => m && setMonth(m)} allowClear={false} format="MMM YYYY" />
                <Button icon={<PrinterOutlined />} href={`${API}/timetable/substitutions/register?month=${month.format("YYYY-MM")}&pdf=1`} target="_blank">
                  {tr(L.print, lang)}
                </Button>
              </Space>
              <Table rowKey="staff" size="small" pagination={false} dataSource={register?.per_teacher ?? []}
                columns={[{ title: tr(t("Teacher", "शिक्षक"), lang), dataIndex: "name" },
                  { title: tr(t("Periods covered", "प्रतिस्थापित कालांश"), lang), dataIndex: "periods", align: "right" }]} />
            </Space>
          ),
        },
      ]} />
    </Space>
  );
}
