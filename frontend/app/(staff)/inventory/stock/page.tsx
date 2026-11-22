"use client";

import { Alert, App, Button, Card, Col, DatePicker, Form, Input, InputNumber, Result, Row, Space, Statistic, Table, Tag, Typography } from "antd";
import type { Dayjs } from "dayjs";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** One item: stock, issue (consumable → department/staff; returnable → staff), Admin count adjustment, full ledger. */
interface Item { id: number; code: string; name: string; unit: string; kind: string; quantity: string; reorder_level: string; avg_cost: string; value: string; low: boolean; store_name: string; location: string }
interface Move { at: string; kind: string; kind_label: string; quantity: string; value: string; balance: string; staff: string; department: string; vendor: string; reference: string; note: string; by: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Issue & stock", "जारी एवं स्टॉक"), item: t("Item", "सामग्री"), pick: t("Choose an item.", "सामग्री चुनें।"),
  stock: t("In stock", "स्टॉक"), value: t("Value", "मूल्य"), reorder: t("Reorder at", "पुनःआदेश स्तर"), low: t("Low stock", "कम स्टॉक"),
  issue: t("Issue", "जारी करें"), qty: t("Quantity", "मात्रा"), dept: t("Department", "विभाग"), staff: t("Staff member", "कर्मचारी"),
  due: t("Due back", "वापसी तिथि"), note: t("Note", "टिप्पणी"), adjust: t("Adjust after physical count (Admin)", "भौतिक गणना के बाद समायोजन (प्रशासक)"),
  counted: t("Counted quantity", "गिनी गई मात्रा"), adjustBtn: t("Adjust stock", "स्टॉक समायोजित करें"), reason: t("Reason", "कारण"), ledger: t("Item ledger", "सामग्री खाता"),
  returnable: t("Returnable: issue to a staff member; it stays on their list until returned.", "वापसी योग्य: कर्मचारी को जारी करें; वापसी तक उनकी सूची में रहेगा।"),
};

function StockPage() {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const params = useSearchParams();
  const [itemId, setItemId] = useState<number | null>(params.get("item") ? Number(params.get("item")) : null);
  const [item, setItem] = useState<Item | null>(null);
  const [moves, setMoves] = useState<Move[]>([]);
  const [busy, setBusy] = useState(false);
  const [issueForm] = Form.useForm();
  const [adjForm] = Form.useForm();

  const load = useCallback(async () => {
    if (!itemId) return;
    setItem(await api.get<Item>(`inventory/items/${itemId}`));
    setMoves(await api.get<Move[]>(`inventory/items/${itemId}/ledger`));
  }, [itemId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!can("inventory.item.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  const readOnly = allBranches;

  async function run(fn: () => Promise<unknown>, form: ReturnType<typeof Form.useForm>[0]) {
    setBusy(true);
    try {
      await fn();
      message.success(tr(UI.done, lang));
      form.resetFields();
      await load();
    } catch (e) {
      const err = e as { message?: string; errors?: Record<string, string[]> };
      message.error(err.errors ? Object.values(err.errors).flat()[0] : err.message ?? "Error");
    } finally {
      setBusy(false);
    }
  }

  const returnable = item?.kind === "returnable";
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <RelationSelect resource="inventory/items" label="name" search value={itemId} onChange={(v) => setItemId((v as number) ?? null)}
        placeholder={tr(L.item, lang)} style={{ minWidth: 300 }} />
      {!itemId && <Alert type="info" showIcon message={tr(L.pick, lang)} />}
      {item && (
        <>
          <Space wrap>
            <Card size="small"><Statistic title={tr(L.stock, lang)} value={Number(item.quantity)} suffix={item.unit} /></Card>
            <Card size="small"><Statistic title={tr(L.value, lang)} value={Number(item.value)} prefix="₹" /></Card>
            <Card size="small"><Statistic title={tr(L.reorder, lang)} value={Number(item.reorder_level)} /></Card>
            {item.low && <Tag color="red">{tr(L.low, lang)}</Tag>}
            <Typography.Text type="secondary">{item.code} · {item.store_name} · {item.location}</Typography.Text>
          </Space>
          {!readOnly && (
            <Row gutter={16}>
              {can("inventory.issue.manage") && (
                <Col xs={24} lg={12}>
                  <Card size="small" title={tr(L.issue, lang)}>
                    {returnable && <Alert type="info" style={{ marginBottom: 8 }} message={tr(L.returnable, lang)} />}
                    <Form form={issueForm} layout="vertical" onFinish={(v: { quantity: number; department?: number; staff?: number; due_back?: Dayjs; note?: string }) =>
                      run(() => api.post("inventory/items/issue", { item: item.id, quantity: v.quantity, department: v.department ?? null,
                        staff: v.staff ?? null, due_back: v.due_back ? v.due_back.format("YYYY-MM-DD") : null, note: v.note ?? "" }), issueForm)}>
                      <Form.Item name="quantity" label={tr(L.qty, lang)} rules={[{ required: true }]}><InputNumber min={0.001} style={{ width: 160 }} /></Form.Item>
                      {!returnable && (
                        <Form.Item name="department" label={tr(L.dept, lang)}>
                          <RelationSelect resource="people/departments" label="name" placeholder={tr(L.dept, lang)} />
                        </Form.Item>
                      )}
                      <Form.Item name="staff" label={tr(L.staff, lang)} rules={returnable ? [{ required: true }] : []}>
                        <RelationSelect resource="people/staff" label="full_name" search placeholder={tr(L.staff, lang)} />
                      </Form.Item>
                      {returnable && <Form.Item name="due_back" label={tr(L.due, lang)}><DatePicker format="DD-MM-YYYY" /></Form.Item>}
                      <Form.Item name="note" label={tr(L.note, lang)}><Input /></Form.Item>
                      <Button type="primary" htmlType="submit" loading={busy}>{tr(L.issue, lang)}</Button>
                    </Form>
                  </Card>
                </Col>
              )}
              {can("inventory.stock.adjust") && (
                <Col xs={24} lg={12}>
                  <Card size="small" title={tr(L.adjust, lang)}>
                    <Form form={adjForm} layout="vertical" onFinish={(v: { counted: number; reason: string }) =>
                      run(() => api.post(`inventory/items/${item.id}/adjust`, v), adjForm)}>
                      <Form.Item name="counted" label={tr(L.counted, lang)} rules={[{ required: true }]}><InputNumber min={0} style={{ width: 160 }} /></Form.Item>
                      <Form.Item name="reason" label={tr(L.reason, lang)} rules={[{ required: true }]}><Input /></Form.Item>
                      <Button danger htmlType="submit" loading={busy}>{tr(L.adjustBtn, lang)}</Button>
                    </Form>
                  </Card>
                </Col>
              )}
            </Row>
          )}
          <Card size="small" title={tr(L.ledger, lang)}>
            <Table<Move> size="small" rowKey={(m, i) => `${m.at}-${i}`} dataSource={moves} pagination={{ pageSize: 25 }} scroll={{ x: true }}
              columns={[
                { title: "", dataIndex: "at", render: (v: string) => new Date(v).toLocaleString("en-IN", { dateStyle: "short", timeStyle: "short" }) },
                { title: "", dataIndex: "kind_label" },
                { title: tr(L.qty, lang), dataIndex: "quantity", render: (v: string) => <span style={{ color: Number(v) < 0 ? "#b42318" : undefined }}>{Number(v)}</span> },
                { title: "₹", dataIndex: "value", render: (v: string) => Number(v).toLocaleString("en-IN") },
                { title: "Balance", dataIndex: "balance", render: (v: string) => Number(v) },
                { title: "", key: "who", render: (_, m) => [m.staff, m.department, m.vendor].filter(Boolean).join(" · ") },
                { title: "", dataIndex: "reference" },
                { title: tr(L.note, lang), dataIndex: "note" },
              ]} />
          </Card>
        </>
      )}
    </Space>
  );
}

export default function Page() {
  return <Suspense><StockPage /></Suspense>;
}
