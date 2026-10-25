"use client";

import { DownloadOutlined, PrinterOutlined, ReloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, DatePicker, Result, Row, Space, Statistic, Table, Tabs, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useCallback, useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

type Money = string | number;
interface Collection {
  from: string; to: string; total: Money; count: number;
  by_mode: { mode: string; amount: Money; count: number }[];
  by_head: { head: string; amount: Money }[];
  cancelled: { number: string; amount: Money; cancel_reason: string; cancelled_by: string }[];
}
interface OutstandingRow { program: string | null; section: string | null; outstanding: Money; overdue: Money; students_with_dues: number }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Fee reports", "शुल्क रिपोर्ट"),
  daily: t("Collection (day book)", "संग्रह (दैनिक बही)"),
  outstanding: t("Outstanding by class", "कक्षावार बकाया"),
  tally: t("Tally export", "टैली निर्यात"),
  period: t("Period", "अवधि"),
  total: t("Total collected", "कुल संग्रह"),
  receipts: t("Receipts", "रसीदें"),
  byMode: t("By mode", "माध्यम अनुसार"),
  byHead: t("By fee head", "मद अनुसार"),
  cancelled: t("Cancelled receipts (not counted)", "रद्द रसीदें (गिनी नहीं गईं)"),
  mode: t("Mode", "माध्यम"),
  head: t("Head", "मद"),
  amount: t("Amount", "राशि"),
  count: t("Count", "संख्या"),
  reason: t("Reason", "कारण"),
  by: t("By", "द्वारा"),
  class: t("Class / course", "कक्षा / पाठ्यक्रम"),
  section: t("Section", "अनुभाग"),
  overdue: t("Overdue", "अतिदेय"),
  students: t("Students with dues", "बकाया वाले छात्र"),
  download: t("Download Tally XML", "टैली XML डाउनलोड करें"),
  tallyHelp: t(
    "Imports into Tally as receipt vouchers: one per receipt, credited to each fee head's income ledger. Set the ledgers in Fee heads and Fee settings first.",
    "टैली में रसीद वाउचर के रूप में आयात होता है: हर रसीद का एक वाउचर, हर मद के आय खाते में। पहले शुल्क मद और शुल्क सेटिंग्स में खाते भरें।",
  ),
  print: t("Print", "प्रिंट"),
};

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
const money = (v: Money | null | undefined) => inr.format(Number(v ?? 0));

export default function FeeReports() {
  const { lang, can, allBranches } = useSession();
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs(), dayjs()]);
  const [collection, setCollection] = useState<Collection | null>(null);
  const [outstanding, setOutstanding] = useState<OutstandingRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const q = `from=${range[0].format("YYYY-MM-DD")}&to=${range[1].format("YYYY-MM-DD")}`;

  const loadCollection = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setCollection(await api.get<Collection>(`fees/reports/collection?${q}`));
    } catch (e) {
      setError((e as { message?: string }).message ?? "Error");
    } finally {
      setLoading(false);
    }
  }, [q]);

  const loadOutstanding = useCallback(async () => {
    try {
      setOutstanding(await api.get<OutstandingRow[]>("fees/reports/outstanding"));
    } catch (e) {
      setError((e as { message?: string }).message ?? "Error");
    }
  }, []);

  useEffect(() => {
    if (can("fees.report.view")) void loadCollection();
  }, [loadCollection, can]);

  if (!can("fees.report.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;

  const rangePicker = (
    <DatePicker.RangePicker
      value={range}
      format="DD-MM-YYYY"
      allowClear={false}
      onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])}
    />
  );

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}
      <Tabs
        onChange={(k) => k === "outstanding" && outstanding === null && void loadOutstanding()}
        items={[
          {
            key: "daily",
            label: tr(L.daily, lang),
            children: (
              <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                <Space wrap className="no-print">
                  {rangePicker}
                  <Button icon={<ReloadOutlined />} onClick={() => void loadCollection()} loading={loading} />
                  <Button icon={<PrinterOutlined />} onClick={() => window.print()}>{tr(L.print, lang)}</Button>
                </Space>
                {collection && (
                  <>
                    <Row gutter={16}>
                      <Col xs={12} md={6}><Statistic title={tr(L.total, lang)} value={money(collection.total)} /></Col>
                      <Col xs={12} md={6}><Statistic title={tr(L.receipts, lang)} value={collection.count} /></Col>
                    </Row>
                    <Row gutter={[16, 16]}>
                      <Col xs={24} lg={12}>
                        <Card size="small" title={tr(L.byMode, lang)}>
                          <Table rowKey="mode" size="small" pagination={false} dataSource={collection.by_mode}
                            columns={[
                              { title: tr(L.mode, lang), dataIndex: "mode" },
                              { title: tr(L.count, lang), dataIndex: "count", align: "right" },
                              { title: tr(L.amount, lang), dataIndex: "amount", align: "right", render: (v: Money) => money(v) },
                            ]} />
                        </Card>
                      </Col>
                      <Col xs={24} lg={12}>
                        <Card size="small" title={tr(L.byHead, lang)}>
                          <Table rowKey="head" size="small" pagination={false} dataSource={collection.by_head}
                            columns={[
                              { title: tr(L.head, lang), dataIndex: "head" },
                              { title: tr(L.amount, lang), dataIndex: "amount", align: "right", render: (v: Money) => money(v) },
                            ]} />
                        </Card>
                      </Col>
                    </Row>
                    {collection.cancelled.length > 0 && (
                      <Card size="small" title={tr(L.cancelled, lang)}>
                        <Table rowKey="number" size="small" pagination={false} dataSource={collection.cancelled}
                          columns={[
                            { title: "#", dataIndex: "number" },
                            { title: tr(L.amount, lang), dataIndex: "amount", align: "right", render: (v: Money) => money(v) },
                            { title: tr(L.reason, lang), dataIndex: "cancel_reason" },
                            { title: tr(L.by, lang), dataIndex: "cancelled_by" },
                          ]} />
                      </Card>
                    )}
                  </>
                )}
              </Space>
            ),
          },
          {
            key: "outstanding",
            label: tr(L.outstanding, lang),
            children: (
              <Table<OutstandingRow>
                rowKey={(r) => `${r.program}-${r.section}`}
                size="small"
                loading={outstanding === null}
                dataSource={outstanding ?? []}
                pagination={false}
                summary={(rows) => (
                  <Table.Summary.Row>
                    <Table.Summary.Cell index={0} colSpan={2}><b>{tr(L.total, lang)}</b></Table.Summary.Cell>
                    <Table.Summary.Cell index={2} align="right"><b>{money(rows.reduce((s, r) => s + Number(r.outstanding), 0))}</b></Table.Summary.Cell>
                    <Table.Summary.Cell index={3} align="right"><b>{money(rows.reduce((s, r) => s + Number(r.overdue), 0))}</b></Table.Summary.Cell>
                    <Table.Summary.Cell index={4} align="right"><b>{rows.reduce((s, r) => s + r.students_with_dues, 0)}</b></Table.Summary.Cell>
                  </Table.Summary.Row>
                )}
                columns={[
                  { title: tr(L.class, lang), dataIndex: "program", render: (v) => v ?? "—" },
                  { title: tr(L.section, lang), dataIndex: "section", render: (v) => v ?? "—" },
                  { title: tr(L.outstanding, lang), dataIndex: "outstanding", align: "right", render: (v: Money) => money(v) },
                  { title: tr(L.overdue, lang), dataIndex: "overdue", align: "right", render: (v: Money) => money(v) },
                  { title: tr(L.students, lang), dataIndex: "students_with_dues", align: "right" },
                ]}
              />
            ),
          },
          {
            key: "tally",
            label: tr(L.tally, lang),
            children: allBranches ? (
              <Alert type="info" showIcon message={tr(UI.readOnlyAll, lang)} />
            ) : (
              <Space direction="vertical">
                <Typography.Paragraph style={{ maxWidth: 640 }}>{tr(L.tallyHelp, lang)}</Typography.Paragraph>
                <Space wrap>
                  {rangePicker}
                  <Button type="primary" icon={<DownloadOutlined />} href={`/api/proxy/fees/reports/tally?${q}`}>
                    {tr(L.download, lang)}
                  </Button>
                </Space>
              </Space>
            ),
          },
        ]}
      />
    </Space>
  );
}
