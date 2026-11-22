"use client";

import { DownloadOutlined } from "@ant-design/icons";
import { Button, DatePicker, Result, Space, Table, Tabs, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

type Row = Record<string, string | number | boolean | null>;
const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Inventory reports", "भंडार रिपोर्ट"), stock: t("Current stock", "वर्तमान स्टॉक"), low: t("Low stock", "कम स्टॉक"),
  cons: t("Department consumption", "विभागवार खपत"), staff: t("Items with staff", "कर्मचारियों के पास सामग्री"),
  vendors: t("Purchases by vendor", "विक्रेतावार क्रय"), store: t("Store (all if empty)", "भंडार (खाली = सभी)"), total: t("Total value", "कुल मूल्य"),
};
const inr = (v: unknown) => `₹${Number(v ?? 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function useGet(path: string | null) {
  const [data, setData] = useState<Row[]>([]);
  useEffect(() => {
    if (path) void api.get<Row[]>(path).then(setData).catch(() => setData([]));
  }, [path]);
  return data;
}

export default function InventoryReports() {
  const { lang, can, allBranches } = useSession();
  const [store, setStore] = useState<number | null>(null);
  const [range, setRange] = useState<[Dayjs, Dayjs]>([dayjs().startOf("month"), dayjs()]);
  const ok = can("inventory.report.view") && !allBranches;
  const sq = store ? `store=${store}` : "";
  const rq = `from=${range[0].format("YYYY-MM-DD")}&to=${range[1].format("YYYY-MM-DD")}`;
  const stock = useGet(ok ? `inventory/reports/stock?${sq}` : null);
  const low = useGet(ok ? `inventory/reports/stock?low=1&${sq}` : null);
  const cons = useGet(ok ? `inventory/reports/consumption?${rq}&${sq}` : null);
  const withStaff = useGet(ok ? "inventory/reports/with-staff" : null);
  const vendors = useGet(ok ? `inventory/reports/vendors?${rq}` : null);
  if (!can("inventory.report.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  const xl = (path: string) => <Button icon={<DownloadOutlined />} href={`${API}/inventory/reports/${path}${path.includes("?") ? "&" : "?"}format=xlsx`}>Excel</Button>;
  const storeSel = <RelationSelect resource="inventory/stores" label="name" value={store} onChange={(v) => setStore((v as number) ?? null)} placeholder={tr(L.store, lang)} style={{ minWidth: 220 }} />;
  const rangeSel = <DatePicker.RangePicker value={range} format="DD-MM-YYYY" allowClear={false} onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])} />;
  const stockCols = [
    { title: "Code", dataIndex: "code" }, { title: "Item", dataIndex: "name" }, { title: "Store", dataIndex: "store" },
    { title: "Qty", dataIndex: "quantity", render: (v: unknown, r: Row) => `${Number(v)} ${r.unit}` },
    { title: "Reorder at", dataIndex: "reorder_level", render: (v: unknown) => Number(v) },
    { title: "Avg. cost", dataIndex: "avg_cost", render: inr }, { title: "Value", dataIndex: "value", render: inr },
    { title: "", dataIndex: "low", render: (v: unknown) => (v ? <Tag color="red">Low</Tag> : null) },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Tabs items={[
        { key: "stock", label: tr(L.stock, lang), children: (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space wrap>{storeSel}{xl(`stock?${sq}`)}<Tag>{tr(L.total, lang)}: {inr(stock.reduce((a, r) => a + Number(r.value), 0))}</Tag></Space>
            <Table size="small" rowKey="id" dataSource={stock} columns={stockCols} pagination={{ pageSize: 50 }} />
          </Space>) },
        { key: "low", label: `${tr(L.low, lang)} (${low.length})`, children: (
          <Space direction="vertical" style={{ width: "100%" }}>{xl(`stock?low=1&${sq}`)}
            <Table size="small" rowKey="id" dataSource={low} columns={stockCols} pagination={false} /></Space>) },
        { key: "cons", label: tr(L.cons, lang), children: (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space wrap>{rangeSel}{storeSel}{xl(`consumption?${rq}&${sq}`)}</Space>
            <Table size="small" rowKey={(r) => `${r.department}-${r.item}`} dataSource={cons} pagination={false}
              columns={[{ title: "Department", dataIndex: "department" }, { title: "Item", dataIndex: "item" },
                { title: "Qty", dataIndex: "quantity", render: (v: unknown, r: Row) => `${Number(v)} ${r.unit}` }, { title: "Value", dataIndex: "value", render: inr }]} />
          </Space>) },
        { key: "staff", label: tr(L.staff, lang), children: (
          <Space direction="vertical" style={{ width: "100%" }}>{xl("with-staff")}
            <Table size="small" rowKey="id" dataSource={withStaff} pagination={false}
              columns={[{ title: "Staff", dataIndex: "staff" }, { title: "Item", dataIndex: "item" }, { title: "Qty", dataIndex: "quantity", render: (v: unknown) => Number(v) },
                { title: "Issued", dataIndex: "issued_on" }, { title: "Due back", dataIndex: "due_back", render: (v: unknown, r: Row) => <span>{String(v ?? "")} {r.overdue ? <Tag color="red">overdue</Tag> : null}</span> }]} />
          </Space>) },
        { key: "vendors", label: tr(L.vendors, lang), children: (
          <Space direction="vertical" style={{ width: "100%" }}>
            <Space wrap>{rangeSel}{xl(`vendors?${rq}`)}</Space>
            <Table size="small" rowKey="vendor" dataSource={vendors} pagination={false}
              columns={[{ title: "Vendor", dataIndex: "vendor" }, { title: "GSTIN", dataIndex: "gstin" }, { title: "Lines", dataIndex: "lines" }, { title: "Value", dataIndex: "value", render: inr }]} />
          </Space>) },
      ]} />
    </Space>
  );
}
