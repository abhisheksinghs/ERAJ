"use client";

import { FilePdfOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Checkbox, DatePicker, Form, Input, Result, Select, Space, Statistic, Table, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Self-service for any staff login: balances, apply for leave, withdraw pending, own payslips. */
interface Balance { id: number; leave_type_code: string; entitled: string; used: string; available: string }
interface Application { id: number; leave_type_code: string; start: string; end: string; days: string; status: string; remarks: string }
interface Summary { name: string; employee_code: string; year: number; leave_types: { id: number; code: string; name: string }[]; balances: Balance[]; applications: Application[] }
interface Slip { id: number; month: string; gross: string; total_deductions: string; net_pay: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("My leave & payslips", "मेरा अवकाश एवं वेतन पर्ची"),
  apply: t("Apply for leave", "अवकाश हेतु आवेदन"), type: t("Leave type", "अवकाश प्रकार"), dates: t("Dates", "तिथियाँ"),
  half: t("Half-day", "आधा दिन"), reason: t("Reason", "कारण"), send: t("Apply", "आवेदन करें"),
  mine: t("My applications", "मेरे आवेदन"), withdraw: t("Withdraw", "वापस लें"), payslips: t("My payslips", "मेरी वेतन पर्चियाँ"),
  notLinked: t("Your login is not linked to a staff record. Ask the office.", "आपका लॉगिन किसी कर्मचारी अभिलेख से जुड़ा नहीं है। कार्यालय से संपर्क करें।"),
  available: t("available", "उपलब्ध"), net: t("Net pay", "शुद्ध वेतन"), days: t("Days", "दिन"),
};
const STATUS_COLOR: Record<string, string> = { pending: "orange", approved: "green", rejected: "red", cancelled: "default" };
const STATUS_LABEL: Record<string, T> = {
  pending: t("Pending", "लंबित"), approved: t("Approved", "स्वीकृत"), rejected: t("Rejected", "अस्वीकृत"), cancelled: t("Cancelled", "रद्द"),
};

export default function MyHR() {
  const { lang, can } = useSession();
  const { message } = App.useApp();
  const [data, setData] = useState<Summary | null>(null);
  const [slips, setSlips] = useState<Slip[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form] = Form.useForm<{ leave_type: number; dates: [Dayjs, Dayjs]; half_day: boolean; reason: string }>();

  const load = useCallback(async () => {
    try {
      setData(await api.get<Summary>("hr/me/summary"));
      if (can("payroll.self.view")) setSlips(await api.get<Slip[]>("payroll/me/payslips"));
    } catch (e) {
      setError((e as { statusCode?: number; message?: string }).statusCode === 404 ? tr(L.notLinked, lang) : (e as { message?: string }).message ?? "Error");
    }
  }, [can, lang]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!can("hr.self.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (error) return <Alert style={{ margin: 8 }} type="info" showIcon message={error} />;

  async function apply(v: { leave_type: number; dates: [Dayjs, Dayjs]; half_day: boolean; reason: string }) {
    setBusy(true);
    try {
      await api.post("hr/me/apply", { leave_type: v.leave_type, start: v.dates[0].format("YYYY-MM-DD"), end: v.dates[1].format("YYYY-MM-DD"),
        half_day: !!v.half_day, reason: v.reason ?? "" });
      message.success(tr(UI.done, lang));
      form.resetFields();
      await load();
    } catch (e) {
      message.error((e as { message?: string }).message ?? "Error");
    } finally {
      setBusy(false);
    }
  }

  async function withdraw(id: number) {
    try {
      await api.post(`hr/me/${id}/cancel`);
      await load();
    } catch (e) {
      message.error((e as { message?: string }).message ?? "Error");
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      {data && <Typography.Text type="secondary">{data.name} · {data.employee_code} · {data.year}</Typography.Text>}
      <Space wrap>
        {data?.balances.map((b) => (
          <Card size="small" key={b.id}><Statistic title={`${b.leave_type_code} ${tr(L.available, lang)}`} value={Number(b.available)} suffix={`/ ${Number(b.entitled)}`} /></Card>
        ))}
      </Space>
      <Card size="small" title={tr(L.apply, lang)}>
        <Form form={form} layout="vertical" onFinish={apply} style={{ maxWidth: 520 }}>
          <Form.Item name="leave_type" label={tr(L.type, lang)} rules={[{ required: true }]}>
            <Select options={(data?.leave_types ?? []).map((lt) => ({ value: lt.id, label: `${lt.code} — ${lt.name}` }))} />
          </Form.Item>
          <Form.Item name="dates" label={tr(L.dates, lang)} rules={[{ required: true }]}>
            <DatePicker.RangePicker format="DD-MM-YYYY" disabledDate={(d) => d.isBefore(dayjs().subtract(30, "day"), "day")} />
          </Form.Item>
          <Form.Item name="half_day" valuePropName="checked"><Checkbox>{tr(L.half, lang)}</Checkbox></Form.Item>
          <Form.Item name="reason" label={tr(L.reason, lang)}><Input.TextArea rows={2} /></Form.Item>
          <Button type="primary" htmlType="submit" loading={busy}>{tr(L.send, lang)}</Button>
        </Form>
      </Card>
      <Card size="small" title={tr(L.mine, lang)}>
        <Table<Application> rowKey="id" size="small" pagination={false} dataSource={data?.applications ?? []}
          columns={[
            { title: "", dataIndex: "leave_type_code" },
            { title: tr(L.dates, lang), key: "d", render: (_, a) => `${dayjs(a.start).format("DD-MM")} → ${dayjs(a.end).format("DD-MM-YYYY")}` },
            { title: tr(L.days, lang), dataIndex: "days", render: (v: string) => Number(v) },
            { title: "", dataIndex: "status", render: (v: string, a) => <Space><Tag color={STATUS_COLOR[v]}>{STATUS_LABEL[v] ? tr(STATUS_LABEL[v], lang) : v}</Tag>{a.remarks}</Space> },
            { title: "", key: "x", render: (_, a) => a.status === "pending" && <Button size="small" onClick={() => withdraw(a.id)}>{tr(L.withdraw, lang)}</Button> },
          ]} />
      </Card>
      {can("payroll.self.view") && (
        <Card size="small" title={tr(L.payslips, lang)}>
          <Table<Slip> rowKey="id" size="small" pagination={false} dataSource={slips}
            columns={[
              { title: "", dataIndex: "month", render: (v: string) => dayjs(v).format("MMMM YYYY") },
              { title: tr(L.net, lang), dataIndex: "net_pay", render: (v: string) => `₹${Number(v).toLocaleString("en-IN")}` },
              { title: "", key: "pdf", render: (_, s) => <Button size="small" icon={<FilePdfOutlined />} target="_blank"
                  href={`${API}/payroll/me/pdf?month=${dayjs(s.month).format("YYYY-MM")}`}>PDF</Button> },
            ]} />
        </Card>
      )}
    </Space>
  );
}
