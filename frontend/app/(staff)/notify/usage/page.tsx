"use client";

import { Result, Space, Table, Typography } from "antd";
import { useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Messages per month and channel — what the SMS / WhatsApp bill will be based on. */
interface Row { month: string; channel: string; total: number; [status: string]: number | string }
const t = (en: string, hi: string): T => ({ en, hi });
const L = { title: t("Messages per month", "मासिक संदेश"), help: t("Simulated = log-only testing, nothing was sent or billed.", "अनुकरण = केवल लॉग परीक्षण, कुछ भेजा या बिल नहीं हुआ।") };
const STATUSES = ["sent", "delivered", "failed", "held", "queued", "skipped", "simulated"];

export default function Usage() {
  const { lang, can, allBranches } = useSession();
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => { if (can("notify.message.view") && !allBranches) void api.get<Row[]>("notify/messages/monthly").then(setRows).catch(() => setRows([])); }, [can, allBranches]);
  if (!can("notify.message.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;
  return (
    <Space direction="vertical" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Typography.Text type="secondary">{tr(L.help, lang)}</Typography.Text>
      <Table<Row> size="small" rowKey={(r) => `${r.month}-${r.channel}`} dataSource={rows} pagination={false}
        columns={[{ title: "Month", dataIndex: "month" }, { title: "Channel", dataIndex: "channel" }, { title: "Total", dataIndex: "total" },
          ...STATUSES.map((s) => ({ title: s, key: s, render: (_: unknown, r: Row) => (r[s] as number) ?? 0 }))]} />
    </Space>
  );
}
