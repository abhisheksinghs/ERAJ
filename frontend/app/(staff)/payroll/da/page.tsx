"use client";

import { Alert, App, Button, Card, DatePicker, Form, Input, InputNumber, Result, Space, Table, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Revise DA for one rule set, from any past month; arrears are paid in the next payroll run (ADR-009). */
interface Rate { id: number; effective_from: string; percent: string; declared_on: string; note: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Revise DA", "महँगाई भत्ता संशोधित करें"), rules: t("Pay rules", "वेतन नियम"), pct: t("New DA %", "नया महँगाई भत्ता %"),
  from: t("Effective from (month)", "प्रभावी (माह)"), note: t("Government order / note", "सरकारी आदेश / टिप्पणी"),
  save: t("Save revision", "संशोधन सहेजें"), history: t("DA history", "महँगाई भत्ता इतिहास"),
  hint: t("Only staff on these pay rules are affected. Arrears for locked past months are added to the next payroll run.",
    "केवल इन वेतन नियमों वाले कर्मचारी प्रभावित होंगे। लॉक हुए पिछले माह का बकाया अगले वेतन में जुड़ेगा।"),
};

function DAForm() {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const params = useSearchParams();
  const [ruleSet, setRuleSet] = useState<number | null>(params.get("rule_set") ? Number(params.get("rule_set")) : null);
  const [rates, setRates] = useState<Rate[]>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!ruleSet) return setRates([]);
    setRates((await api.get<{ results: Rate[] }>(`payroll/da-rates?rule_set=${ruleSet}&page_size=100`)).results);
  }, [ruleSet]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!can("payroll.da.manage")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  async function save(v: { percent: number; month: Dayjs; note: string }) {
    if (!ruleSet) return;
    setBusy(true);
    try {
      await api.post(`payroll/rule-sets/${ruleSet}/revise-da`, { percent: v.percent, effective_from: v.month.startOf("month").format("YYYY-MM-DD"), note: v.note ?? "" });
      message.success(tr(UI.done, lang));
      await load();
    } catch (e) {
      message.error((e as { message?: string }).message ?? "Error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <RelationSelect resource="payroll/rule-sets" label="name" value={ruleSet} onChange={(v) => setRuleSet((v as number) ?? null)}
        placeholder={tr(L.rules, lang)} style={{ minWidth: 260 }} />
      <Alert type="info" showIcon message={tr(L.hint, lang)} />
      {ruleSet && (
        <Card size="small">
          <Form layout="inline" onFinish={save}>
            <Form.Item name="percent" label={tr(L.pct, lang)} rules={[{ required: true }]}><InputNumber min={0} max={500} step={1} /></Form.Item>
            <Form.Item name="month" label={tr(L.from, lang)} rules={[{ required: true }]}>
              <DatePicker picker="month" disabledDate={(d) => d.isAfter(dayjs().add(1, "month"), "month")} />
            </Form.Item>
            <Form.Item name="note" label={tr(L.note, lang)}><Input style={{ width: 220 }} /></Form.Item>
            <Button type="primary" htmlType="submit" loading={busy}>{tr(L.save, lang)}</Button>
          </Form>
        </Card>
      )}
      {ruleSet && (
        <Table<Rate> rowKey="id" size="small" pagination={false} dataSource={rates} title={() => tr(L.history, lang)}
          columns={[
            { title: tr(L.from, lang), dataIndex: "effective_from", render: (v: string) => dayjs(v).format("MMM YYYY") },
            { title: "DA %", dataIndex: "percent", render: (v: string) => Number(v) },
            { title: tr(L.note, lang), dataIndex: "note" },
            { title: "", dataIndex: "declared_on", render: (v: string) => v && dayjs(v).format("DD-MM-YYYY") },
          ]} />
      )}
    </Space>
  );
}

export default function DAPage() {
  return <Suspense><DAForm /></Suspense>;
}
