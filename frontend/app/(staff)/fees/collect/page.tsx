"use client";

import { PrinterOutlined } from "@ant-design/icons";
import {
  Alert, App, Button, Card, Col, DatePicker, Descriptions, Empty, Form, Input, InputNumber, Modal, Radio, Result, Row,
  Select, Space, Spin, Statistic, Table, Tabs, Tag, Typography,
} from "antd";
import dayjs from "dayjs";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/**
 * Fee counter: find a student, see what they owe, take a payment and print the
 * receipt. Also the place to refund money already received.
 */
type Money = string;
interface Charge {
  id: number; head_name: string; description: string; due_date: string | null; amount: Money; discount: Money;
  net: Money; paid: Money; outstanding: Money; source_type: string; cancelled_at: string | null;
}
interface Receipt {
  id: number; number: string; date: string; mode: string; reference: string; amount: Money; is_cancelled: boolean;
  cancel_reason: string; received_by: string; lines: { charge: number; head_name: string; description: string; amount: Money }[];
}
interface Refund { id: number; date: string; mode: string; amount: Money; reason: string; created_by: string }
interface Ledger {
  account: {
    id: number; admission_no: string; full_name: string; program: string | null; section: string | null;
    guardian_name: string | null; guardian_phone: string | null; total_charged: Money; total_paid: Money;
    outstanding: Money; overdue: Money;
  };
  charges: Charge[];
  receipts: Receipt[];
  refunds: Refund[];
}

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Collect fees", "शुल्क जमा"),
  pick: t("Search a student by name or admission number", "नाम या प्रवेश संख्या से छात्र खोजें"),
  class: t("Class", "कक्षा"),
  guardian: t("Guardian", "अभिभावक"),
  charged: t("Charged", "देय"),
  paid: t("Paid", "भुगतान"),
  outstanding: t("Outstanding", "बकाया"),
  overdue: t("Overdue", "अतिदेय"),
  dues: t("Dues", "बकाया मदें"),
  noDues: t("Nothing is due.", "कुछ भी बकाया नहीं है।"),
  head: t("Head", "मद"),
  desc: t("Description", "विवरण"),
  due: t("Due date", "नियत तिथि"),
  pay: t("Paying now", "अभी भुगतान"),
  how: t("How to apply the payment", "भुगतान कैसे लगाएँ"),
  pickLines: t("Choose dues", "मदें चुनें"),
  lumpSum: t("Lump sum (oldest dues first)", "एकमुश्त (पुराने बकाया पहले)"),
  amount: t("Amount (₹)", "राशि (₹)"),
  mode: t("Mode", "माध्यम"),
  reference: t("Cheque / UTR / DD number", "चेक / UTR / DD संख्या"),
  refRequired: t("Required for every mode except cash", "नकद के अलावा हर माध्यम में आवश्यक"),
  date: t("Receipt date", "रसीद तिथि"),
  note: t("Note", "टिप्पणी"),
  total: t("Total", "कुल"),
  collect: t("Collect and make receipt", "जमा करें और रसीद बनाएँ"),
  done: t("Receipt created", "रसीद बनी"),
  print: t("Print receipt", "रसीद प्रिंट करें"),
  next: t("Next student", "अगला छात्र"),
  receipts: t("Receipts", "रसीदें"),
  ledger: t("All charges", "सभी देय"),
  refunds: t("Refunds", "धनवापसी"),
  refund: t("Refund", "धनवापसी करें"),
  refundTitle: t("Refund money received", "प्राप्त राशि वापस करें"),
  reason: t("Reason", "कारण"),
  cancelled: t("Cancelled", "रद्द"),
  overdueTag: t("Overdue", "अतिदेय"),
  nothingSelected: t("Choose at least one due and an amount.", "कम से कम एक मद और राशि चुनें।"),
  refundable: t("Received", "प्राप्त"),
  allBranches: UI.readOnlyAll,
};

const MODES = [
  { value: "cash", label: t("Cash", "नकद") },
  { value: "upi", label: t("UPI", "UPI") },
  { value: "cheque", label: t("Cheque", "चेक") },
  { value: "dd", label: t("Demand draft", "डिमांड ड्राफ्ट") },
  { value: "bank_transfer", label: t("Bank transfer", "बैंक हस्तांतरण") },
];

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const money = (v: Money | number | null | undefined) => inr.format(Number(v ?? 0));
const fmtDate = (v: string | null) => (v ? dayjs(v).format("DD-MM-YYYY") : "—");
const round2 = (n: number) => Math.round(n * 100) / 100;

function openPdf(id: number) {
  window.open(`/api/proxy/fees/receipts/${id}/pdf`, "_blank", "noopener");
}

function Counter() {
  const { lang, can, allBranches, branch } = useSession();
  const { message } = App.useApp();
  const router = useRouter();
  const params = useSearchParams();
  const studentId = params.get("student");

  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payNow, setPayNow] = useState<Record<number, number | null>>({});
  const [applyMode, setApplyMode] = useState<"lines" | "amount">("lines");
  const [saving, setSaving] = useState(false);
  const [made, setMade] = useState<Receipt | null>(null);
  const [refundOpen, setRefundOpen] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!studentId) {
      setLedger(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<Ledger>(`fees/accounts/${studentId}`);
      setLedger(data);
      const open = data.charges.filter((c) => !c.cancelled_at && Number(c.outstanding) > 0);
      setPayNow(Object.fromEntries(open.map((c) => [c.id, null])));
    } catch (e) {
      setLedger(null);
      setError((e as { message?: string }).message ?? "Error");
    } finally {
      setLoading(false);
    }
  }, [studentId]);

  useEffect(() => {
    void load();
  }, [load, branch?.id]);

  const dues = useMemo(
    () =>
      (ledger?.charges ?? [])
        .filter((c) => !c.cancelled_at && Number(c.outstanding) > 0)
        .sort((a, b) => (a.due_date ?? "9999").localeCompare(b.due_date ?? "9999")),
    [ledger],
  );
  const today = dayjs().format("YYYY-MM-DD");
  const linesTotal = round2(Object.values(payNow).reduce<number>((s, v) => s + (v ?? 0), 0));

  if (!can("fees.receipt.manage")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(L.allBranches, lang)} />;

  async function submit(values: { mode: string; reference?: string; date?: dayjs.Dayjs; note?: string; amount?: number }) {
    if (!ledger) return;
    const body: Record<string, unknown> = {
      student: ledger.account.id,
      mode: values.mode,
      reference: values.reference ?? "",
      note: values.note ?? "",
      date: (values.date ?? dayjs()).format("YYYY-MM-DD"),
    };
    if (applyMode === "lines") {
      const lines = Object.entries(payNow)
        .filter(([, v]) => v && v > 0)
        .map(([charge, amount]) => ({ charge: Number(charge), amount: Number(amount).toFixed(2) }));
      if (!lines.length) {
        message.warning(tr(L.nothingSelected, lang));
        return;
      }
      body.lines = lines;
    } else {
      body.amount = Number(values.amount ?? 0).toFixed(2);
    }
    setSaving(true);
    try {
      const receipt = await api.post<Receipt>("fees/receipts", body);
      setMade(receipt);
      form.resetFields(["reference", "note", "amount"]);
      await load();
    } catch (e) {
      const err = e as { message?: string; errors?: Record<string, string[]> };
      const detail = err.errors ? Object.values(err.errors).flat()[0] : undefined;
      message.error(detail ?? err.message ?? "Error");
    } finally {
      setSaving(false);
    }
  }

  const acc = ledger?.account;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <div style={{ maxWidth: 520 }}>
        <RelationSelect
          resource="people/students"
          label="full_name"
          search
          value={studentId ? Number(studentId) : null}
          placeholder={tr(L.pick, lang)}
          onChange={(v) => router.replace(v ? `/fees/collect?student=${v}` : "/fees/collect")}
        />
      </div>

      {loading && <Spin />}
      {error && <Alert type="error" showIcon message={error} />}
      {!studentId && !loading && <Empty description={tr(L.pick, lang)} />}

      {acc && !loading && (
        <>
          <Card size="small">
            <Row gutter={[16, 16]} align="middle">
              <Col xs={24} lg={10}>
                <Descriptions size="small" column={1} title={`${acc.full_name} · ${acc.admission_no}`}>
                  <Descriptions.Item label={tr(L.class, lang)}>{[acc.program, acc.section].filter(Boolean).join(" – ") || "—"}</Descriptions.Item>
                  <Descriptions.Item label={tr(L.guardian, lang)}>
                    {[acc.guardian_name, acc.guardian_phone].filter(Boolean).join(" · ") || "—"}
                  </Descriptions.Item>
                </Descriptions>
              </Col>
              <Col xs={12} lg={3}><Statistic title={tr(L.charged, lang)} value={money(acc.total_charged)} /></Col>
              <Col xs={12} lg={3}><Statistic title={tr(L.paid, lang)} value={money(acc.total_paid)} /></Col>
              <Col xs={12} lg={4}><Statistic title={tr(L.outstanding, lang)} value={money(acc.outstanding)} /></Col>
              <Col xs={12} lg={4}>
                <Statistic title={tr(L.overdue, lang)} value={money(acc.overdue)}
                  valueStyle={Number(acc.overdue) > 0 ? { color: "#cf1322" } : undefined} />
              </Col>
            </Row>
          </Card>

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={15}>
              <Card size="small" title={tr(L.dues, lang)}>
                {dues.length === 0 ? (
                  <Empty description={tr(L.noDues, lang)} />
                ) : (
                  <Table<Charge> rowKey="id" size="small" pagination={false} dataSource={dues} scroll={{ x: true }}>
                    <Table.Column<Charge> title={tr(L.head, lang)} dataIndex="head_name" />
                    <Table.Column<Charge> title={tr(L.desc, lang)} dataIndex="description" />
                    <Table.Column<Charge>
                      title={tr(L.due, lang)}
                      render={(_, c) => (
                        <Space size={4} style={{ whiteSpace: "nowrap" }}>
                          {fmtDate(c.due_date)}
                          {c.due_date && c.due_date < today && <Tag color="red">{tr(L.overdueTag, lang)}</Tag>}
                        </Space>
                      )}
                    />
                    <Table.Column<Charge> title={tr(L.outstanding, lang)} align="right" render={(_, c) => money(c.outstanding)} />
                    {applyMode === "lines" && (
                      <Table.Column<Charge>
                        title={tr(L.pay, lang)}
                        render={(_, c) => (
                          <Space.Compact>
                            <InputNumber<number>
                              aria-label={`pay-${c.id}`}
                              min={0}
                              max={Number(c.outstanding)}
                              precision={2}
                              prefix="₹"
                              style={{ width: 130 }}
                              value={payNow[c.id] ?? null}
                              onChange={(v) => setPayNow((p) => ({ ...p, [c.id]: v }))}
                            />
                            <Button onClick={() => setPayNow((p) => ({ ...p, [c.id]: Number(c.outstanding) }))}>
                              {lang === "hi" ? "पूरा" : "Full"}
                            </Button>
                          </Space.Compact>
                        )}
                      />
                    )}
                  </Table>
                )}
              </Card>
            </Col>

            <Col xs={24} xl={9}>
              <Card size="small" title={tr(L.collect, lang)}>
                <Form form={form} layout="vertical" onFinish={submit} initialValues={{ mode: "cash", date: dayjs() }}
                  disabled={dues.length === 0}>
                  <Form.Item label={tr(L.how, lang)}>
                    <Radio.Group value={applyMode} onChange={(e) => setApplyMode(e.target.value)}>
                      <Radio.Button value="lines">{tr(L.pickLines, lang)}</Radio.Button>
                      <Radio.Button value="amount">{tr(L.lumpSum, lang)}</Radio.Button>
                    </Radio.Group>
                  </Form.Item>
                  {applyMode === "amount" ? (
                    <Form.Item name="amount" label={tr(L.amount, lang)} rules={[{ required: true }]}>
                      <InputNumber<number> min={0.01} max={Number(acc.outstanding)} precision={2} prefix="₹" style={{ width: "100%" }} />
                    </Form.Item>
                  ) : (
                    <Form.Item label={tr(L.total, lang)}>
                      <Typography.Text strong style={{ fontSize: 20 }}>{money(linesTotal)}</Typography.Text>
                      <Button type="link" onClick={() => setPayNow(Object.fromEntries(dues.map((c) => [c.id, Number(c.outstanding)])))}>
                        {lang === "hi" ? "सब पूरा भरें" : "Fill all in full"}
                      </Button>
                    </Form.Item>
                  )}
                  <Form.Item name="mode" label={tr(L.mode, lang)} rules={[{ required: true }]}>
                    <Select options={MODES.map((m) => ({ value: m.value, label: tr(m.label, lang) }))} />
                  </Form.Item>
                  <Form.Item noStyle shouldUpdate={(a, b) => a.mode !== b.mode}>
                    {({ getFieldValue }) => (
                      <Form.Item name="reference" label={tr(L.reference, lang)} extra={tr(L.refRequired, lang)}
                        rules={[{ required: getFieldValue("mode") !== "cash" }]}>
                        <Input maxLength={100} />
                      </Form.Item>
                    )}
                  </Form.Item>
                  <Form.Item name="date" label={tr(L.date, lang)}>
                    <DatePicker format="DD-MM-YYYY" style={{ width: "100%" }} disabledDate={(d) => d.isAfter(dayjs(), "day")} />
                  </Form.Item>
                  <Form.Item name="note" label={tr(L.note, lang)}>
                    <Input maxLength={200} />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" block size="large" loading={saving}>
                    {tr(L.collect, lang)}
                  </Button>
                </Form>
              </Card>
            </Col>
          </Row>

          <Card size="small">
            <Tabs
              tabBarExtraContent={can("fees.refund.manage") && (
                <Button onClick={() => setRefundOpen(true)}>{tr(L.refund, lang)}</Button>
              )}
              items={[
                {
                  key: "receipts",
                  label: `${tr(L.receipts, lang)} (${ledger.receipts.length})`,
                  children: (
                    <Table<Receipt> rowKey="id" size="small" dataSource={ledger.receipts} pagination={{ pageSize: 10 }} scroll={{ x: true }}>
                      <Table.Column<Receipt> title="#" dataIndex="number" />
                      <Table.Column<Receipt> title={tr(L.date, lang)} render={(_, r) => fmtDate(r.date)} />
                      <Table.Column<Receipt> title={tr(L.mode, lang)} render={(_, r) => <Tag>{tr(MODES.find((m) => m.value === r.mode)?.label ?? t(r.mode, r.mode), lang)}</Tag>} />
                      <Table.Column<Receipt> title={tr(L.amount, lang)} align="right" render={(_, r) => money(r.amount)} />
                      <Table.Column<Receipt>
                        render={(_, r) => (
                          <Space>
                            {r.is_cancelled && <Tag color="red" title={r.cancel_reason}>{tr(L.cancelled, lang)}</Tag>}
                            <Button size="small" icon={<PrinterOutlined />} onClick={() => openPdf(r.id)} />
                          </Space>
                        )}
                      />
                    </Table>
                  ),
                },
                {
                  key: "charges",
                  label: tr(L.ledger, lang),
                  children: (
                    <Table<Charge> rowKey="id" size="small" dataSource={ledger.charges} pagination={{ pageSize: 10 }} scroll={{ x: true }}>
                      <Table.Column<Charge> title={tr(L.head, lang)} dataIndex="head_name" />
                      <Table.Column<Charge> title={tr(L.desc, lang)} dataIndex="description" />
                      <Table.Column<Charge> title={tr(L.due, lang)} render={(_, c) => fmtDate(c.due_date)} />
                      <Table.Column<Charge> title={tr(L.charged, lang)} align="right" render={(_, c) => money(c.net)} />
                      <Table.Column<Charge> title={tr(L.paid, lang)} align="right" render={(_, c) => money(c.paid)} />
                      <Table.Column<Charge> title={tr(L.outstanding, lang)} align="right"
                        render={(_, c) => (c.cancelled_at ? <Tag>{tr(L.cancelled, lang)}</Tag> : money(c.outstanding))} />
                    </Table>
                  ),
                },
                {
                  key: "refunds",
                  label: `${tr(L.refunds, lang)} (${ledger.refunds.length})`,
                  children: (
                    <Table<Refund> rowKey="id" size="small" dataSource={ledger.refunds} pagination={false}>
                      <Table.Column<Refund> title={tr(L.date, lang)} render={(_, r) => fmtDate(r.date)} />
                      <Table.Column<Refund> title={tr(L.mode, lang)} dataIndex="mode" />
                      <Table.Column<Refund> title={tr(L.amount, lang)} align="right" render={(_, r) => money(r.amount)} />
                      <Table.Column<Refund> title={tr(L.reason, lang)} dataIndex="reason" />
                    </Table>
                  ),
                },
              ]}
            />
          </Card>

          <RefundModal open={refundOpen} ledger={ledger} lang={lang} onClose={() => setRefundOpen(false)} onDone={load} />
        </>
      )}

      <Modal
        open={made !== null}
        onCancel={() => setMade(null)}
        footer={[
          <Button key="next" onClick={() => { setMade(null); router.replace("/fees/collect"); }}>{tr(L.next, lang)}</Button>,
          <Button key="print" type="primary" icon={<PrinterOutlined />} onClick={() => made && openPdf(made.id)}>
            {tr(L.print, lang)}
          </Button>,
        ]}
      >
        {made && (
          <Result
            status="success"
            title={`${tr(L.done, lang)}: ${made.number}`}
            subTitle={`${money(made.amount)} · ${tr(MODES.find((m) => m.value === made.mode)?.label ?? t(made.mode, made.mode), lang)}`}
          />
        )}
      </Modal>
    </Space>
  );
}

function RefundModal({ open, ledger, lang, onClose, onDone }: {
  open: boolean; ledger: Ledger; lang: "en" | "hi"; onClose: () => void; onDone: () => Promise<void> | void;
}) {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [amounts, setAmounts] = useState<Record<number, number | null>>({});
  const [saving, setSaving] = useState(false);
  const paid = ledger.charges.filter((c) => Number(c.paid) > 0);

  async function submit(values: { mode: string; reference?: string; reason: string }) {
    const lines = Object.entries(amounts)
      .filter(([, v]) => v && v > 0)
      .map(([charge, amount]) => ({ charge: Number(charge), amount: Number(amount).toFixed(2) }));
    if (!lines.length) {
      message.warning(tr(L.nothingSelected, lang));
      return;
    }
    setSaving(true);
    try {
      await api.post("fees/refunds", { student: ledger.account.id, ...values, reference: values.reference ?? "", lines });
      message.success(tr(UI.done, lang));
      setAmounts({});
      form.resetFields();
      onClose();
      await onDone();
    } catch (e) {
      const err = e as { message?: string; errors?: Record<string, string[]> };
      message.error((err.errors ? Object.values(err.errors).flat()[0] : undefined) ?? err.message ?? "Error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} title={tr(L.refundTitle, lang)} onCancel={onClose} width={720}
      okText={tr(L.refund, lang)} okButtonProps={{ danger: true, loading: saving }} onOk={() => form.submit()} destroyOnHidden>
      <Table<Charge> rowKey="id" size="small" pagination={false} dataSource={paid} style={{ marginBottom: 16 }}>
        <Table.Column<Charge> title={tr(L.head, lang)} dataIndex="head_name" />
        <Table.Column<Charge> title={tr(L.desc, lang)} dataIndex="description" />
        <Table.Column<Charge> title={tr(L.refundable, lang)} align="right" render={(_, c) => money(c.paid)} />
        <Table.Column<Charge>
          title={tr(L.refund, lang)}
          render={(_, c) => (
            <InputNumber<number> min={0} max={Number(c.paid)} precision={2} prefix="₹" style={{ width: 130 }}
              value={amounts[c.id] ?? null} onChange={(v) => setAmounts((p) => ({ ...p, [c.id]: v }))} />
          )}
        />
      </Table>
      <Form form={form} layout="vertical" onFinish={submit} initialValues={{ mode: "cash" }}>
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="mode" label={tr(L.mode, lang)} rules={[{ required: true }]}>
              <Select options={MODES.map((m) => ({ value: m.value, label: tr(m.label, lang) }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="reference" label={tr(L.reference, lang)}>
              <Input maxLength={100} />
            </Form.Item>
          </Col>
        </Row>
        <Form.Item name="reason" label={tr(L.reason, lang)} rules={[{ required: true }]}>
          <Input maxLength={200} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default function CollectPage() {
  return (
    <Suspense fallback={<Spin />}>
      <Counter />
    </Suspense>
  );
}
