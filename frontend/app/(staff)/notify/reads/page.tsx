"use client";

import { Alert, Result, Space, Table, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

interface Row { student: number; name: string; admission_no: string; read_at: string | null }
interface Reads { recipients: number; read: number; rows: Row[] }
const t = (en: string, hi: string): T => ({ en, hi });
const L = { title: t("Who has read the notice", "सूचना किसने पढ़ी"), read: t("Read", "पढ़ा"), unread: t("Not yet", "अभी नहीं"),
  none: t("Open this from the Notices list.", "सूचना सूची से खोलें।") };

function Reads() {
  const { lang, can } = useSession();
  const id = useSearchParams().get("notice");
  const [data, setData] = useState<Reads | null>(null);
  useEffect(() => { if (id) void api.get<Reads>(`notify/notices/${id}/reads`).then(setData).catch(() => setData(null)); }, [id]);
  if (!can("notify.notice.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (!id) return <Alert type="info" showIcon message={tr(L.none, lang)} />;
  return (
    <Space direction="vertical" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Typography.Text>{tr(L.read, lang)}: <b>{data?.read ?? 0}</b> / {data?.rows.length ?? 0}</Typography.Text>
      <Table<Row> size="small" rowKey="student" dataSource={data?.rows ?? []} pagination={{ pageSize: 100 }}
        columns={[{ title: "Student", dataIndex: "name" }, { title: "Adm. no.", dataIndex: "admission_no" },
          { title: "", dataIndex: "read_at", render: (v: string | null) => v ? <Tag color="green">{dayjs(v).format("DD-MM HH:mm")}</Tag> : <Tag>{tr(L.unread, lang)}</Tag> }]} />
    </Space>
  );
}

export default function Page() {
  return <Suspense><Reads /></Suspense>;
}
