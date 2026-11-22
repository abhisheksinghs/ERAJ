"use client";

import { Alert, App, Button, Card, Descriptions, Input, InputNumber, Result, Space, Table, Tag, Typography } from "antd";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Goods received against a purchase order, in full or in part; stock rises at the order rate. */
interface Line { id: number; item_name: string; unit: string; quantity: string; rate: string; received: string; outstanding: string }
interface Order { id: number; number: string; vendor_name: string; order_date: string; status: string; total: string; received_percent: number; lines: Line[] }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Receive goods", "माल प्राप्त करें"), challan: t("Challan / bill no.", "चालान / बिल सं."), save: t("Record receipt", "प्राप्ति दर्ज करें"),
  all: t("Receive everything outstanding", "सारा शेष प्राप्त"), now: t("Received now", "अभी प्राप्त"), done: t("Fully received.", "पूरा प्राप्त।"),
};

function Receive() {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const router = useRouter();
  const id = useSearchParams().get("order");
  const [order, setOrder] = useState<Order | null>(null);
  const [qty, setQty] = useState<Record<number, number>>({});
  const [challan, setChallan] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (id) void api.get<Order>(`inventory/orders/${id}`).then(setOrder);
  }, [id]);

  if (!can("inventory.order.receive")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;
  if (!order) return null;

  async function save() {
    setBusy(true);
    try {
      const lines = Object.fromEntries(Object.entries(qty).filter(([, v]) => v > 0).map(([k, v]) => [k, String(v)]));
      await api.post(`inventory/orders/${order!.id}/receive`, { lines, challan_no: challan });
      message.success(tr(UI.done, lang));
      router.push("/inventory/orders");
    } catch (e) {
      message.error((e as { message?: string }).message ?? "Error");
    } finally {
      setBusy(false);
    }
  }

  const open = order.status === "open" || order.status === "partly";
  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8, maxWidth: 900 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Descriptions size="small" bordered column={{ xs: 1, md: 3 }}>
        <Descriptions.Item label="Order">{order.number}</Descriptions.Item>
        <Descriptions.Item label="Vendor">{order.vendor_name}</Descriptions.Item>
        <Descriptions.Item label="Received"><Tag>{order.received_percent}%</Tag></Descriptions.Item>
      </Descriptions>
      {!open && <Alert type="success" showIcon message={tr(L.done, lang)} />}
      <Card size="small">
        <Table<Line> rowKey="id" size="small" pagination={false} dataSource={order.lines}
          columns={[
            { title: "Item", dataIndex: "item_name" },
            { title: "Ordered", key: "o", render: (_, l) => `${Number(l.quantity)} ${l.unit}` },
            { title: "Rate ₹", dataIndex: "rate" },
            { title: "Received", dataIndex: "received", render: (v: string) => Number(v) },
            { title: "Outstanding", dataIndex: "outstanding", render: (v: string) => Number(v) },
            { title: tr(L.now, lang), key: "now", render: (_, l) => (
              <InputNumber min={0} max={Number(l.outstanding)} disabled={!open || Number(l.outstanding) === 0} value={qty[l.id]}
                onChange={(v) => setQty((q) => ({ ...q, [l.id]: Number(v ?? 0) }))} aria-label={`receive-${l.item_name}`} />
            ) },
          ]} />
        {open && (
          <Space style={{ marginTop: 12 }} wrap>
            <Button onClick={() => setQty(Object.fromEntries(order.lines.map((l) => [l.id, Number(l.outstanding)])))}>{tr(L.all, lang)}</Button>
            <Input placeholder={tr(L.challan, lang)} value={challan} onChange={(e) => setChallan(e.target.value)} style={{ width: 220 }} />
            <Button type="primary" loading={busy} onClick={save} disabled={!Object.values(qty).some((v) => v > 0)}>{tr(L.save, lang)}</Button>
          </Space>
        )}
      </Card>
    </Space>
  );
}

export default function Page() {
  return <Suspense><Receive /></Suspense>;
}
