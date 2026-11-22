"use client";

import { DownloadOutlined, PrinterOutlined } from "@ant-design/icons";
import { Button, InputNumber, Progress, Result, Space, Table, Tabs, Tag, Typography } from "antd";
import { useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

interface Rider { route: string; stop_no: number; stop: string; pickup: string | null; vehicle: string; rider: string; type: string; id_no: string; class: string; guardian_phone: string; monthly_fare: number }
interface Occ { vehicle: string; route: string; capacity: number; riders: number; free: number; percent: number }
interface Doc { id: number; vehicle: string; document: string; number: string; expires_on: string; days_left: number; expired: boolean }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Transport reports", "परिवहन रिपोर्ट"), riders: t("Rider list", "यात्री सूची"), occ: t("Occupancy", "भराव"),
  docs: t("Papers expiring", "समाप्त होते कागज़ात"), route: t("Route (all if empty)", "मार्ग (खाली = सभी)"), print: t("Print", "प्रिंट"),
  within: t("Expiring within (days)", "इतने दिनों में समाप्त"), expired: t("Expired", "समाप्त"),
};

function useGet<R>(path: string | null) {
  const [data, setData] = useState<R | null>(null);
  useEffect(() => {
    if (path) void api.get<R>(path).then(setData).catch(() => setData(null));
  }, [path]);
  return data;
}

export default function TransportReports() {
  const { lang, can, allBranches } = useSession();
  const [route, setRoute] = useState<number | null>(null);
  const [days, setDays] = useState(30);
  const ok = can("transport.report.view") && !allBranches;
  const q = route ? `?route=${route}` : "";
  const riders = useGet<Rider[]>(ok ? `transport/reports/riders${q}` : null);
  const occ = useGet<Occ[]>(ok ? "transport/reports/occupancy" : null);
  const docs = useGet<Doc[]>(ok ? `transport/reports/expiring?days=${days}` : null);
  if (!can("transport.report.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Tabs items={[
        {
          key: "riders", label: tr(L.riders, lang), children: (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space wrap>
                <RelationSelect resource="transport/routes" label="code" value={route} onChange={(v) => setRoute((v as number) ?? null)}
                  placeholder={tr(L.route, lang)} style={{ minWidth: 220 }} />
                <Button icon={<PrinterOutlined />} target="_blank" href={`${API}/transport/reports/riders${q ? q + "&" : "?"}pdf=1`}>{tr(L.print, lang)}</Button>
                <Button icon={<DownloadOutlined />} href={`${API}/transport/reports/riders${q ? q + "&" : "?"}format=xlsx`}>Excel</Button>
              </Space>
              <Table<Rider> size="small" rowKey={(r) => `${r.route}-${r.id_no}`} dataSource={riders ?? []} pagination={{ pageSize: 50 }}
                columns={[
                  { title: "Route", dataIndex: "route" }, { title: "#", dataIndex: "stop_no" }, { title: "Stop", dataIndex: "stop" },
                  { title: "Rider", dataIndex: "rider", render: (v, r) => <span>{v} {r.type === "staff" && <Tag>staff</Tag>}</span> },
                  { title: "Class", dataIndex: "class" }, { title: "Guardian phone", dataIndex: "guardian_phone" },
                  { title: "Vehicle", dataIndex: "vehicle" },
                ]} />
            </Space>
          ),
        },
        {
          key: "occ", label: tr(L.occ, lang), children: (
            <Table<Occ> size="small" rowKey="vehicle" pagination={false} dataSource={occ ?? []}
              columns={[{ title: "Vehicle", dataIndex: "vehicle" }, { title: "Route", dataIndex: "route" },
                { title: "Riders", key: "r", render: (_, r) => `${r.riders} / ${r.capacity}` },
                { title: "", dataIndex: "percent", render: (v: number) => <Progress percent={v} size="small" status={v >= 100 ? "exception" : "normal"} style={{ width: 160 }} /> }]} />
          ),
        },
        {
          key: "docs", label: tr(L.docs, lang), children: (
            <Space direction="vertical" style={{ width: "100%" }}>
              <Space><Typography.Text>{tr(L.within, lang)}</Typography.Text>
                <InputNumber min={0} max={365} value={days} onChange={(v) => setDays(v ?? 30)} aria-label="days" /></Space>
              <Table<Doc> size="small" rowKey="id" pagination={false} dataSource={docs ?? []}
                columns={[{ title: "Vehicle", dataIndex: "vehicle" }, { title: "Document", dataIndex: "document" }, { title: "No.", dataIndex: "number" },
                  { title: "Expires", dataIndex: "expires_on" },
                  { title: "", dataIndex: "days_left", render: (v: number, r) => r.expired ? <Tag color="red">{tr(L.expired, lang)}</Tag> : <Tag color={v <= 7 ? "orange" : "gold"}>{v} d</Tag> }]} />
            </Space>
          ),
        },
      ]} />
    </Space>
  );
}
