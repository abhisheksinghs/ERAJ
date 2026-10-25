"use client";

import { PrinterOutlined } from "@ant-design/icons";
import { Button, Empty, Result, Segmented, Space, Typography } from "antd";
import { useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { type Grid, TimetableGrid } from "@/components/staff/TimetableGrid";
import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Timetable", "समय-सारणी"),
  section: t("Section", "अनुभाग"),
  teacher: t("Teacher", "शिक्षक"),
  room: t("Room", "कक्ष"),
  print: t("Print", "प्रिंट"),
};
type Kind = "section" | "teacher" | "room";
const PARAM: Record<Kind, string> = { section: "section", teacher: "staff", room: "room" };
const SOURCE: Record<Kind, { resource: string; label: string; search?: boolean }> = {
  section: { resource: "people/sections", label: "label" },
  teacher: { resource: "people/staff", label: "full_name", search: true },
  room: { resource: "timetable/rooms", label: "name" },
};

export default function TimetableView() {
  const { lang, can } = useSession();
  const [kind, setKind] = useState<Kind>("section");
  const [id, setId] = useState<number | null>(null);
  const [grid, setGrid] = useState<Grid | null>(null);

  useEffect(() => {
    if (!id) {
      setGrid(null);
      return;
    }
    api.get<Grid>(`timetable/views/${kind}?${PARAM[kind]}=${id}`).then(setGrid).catch(() => setGrid(null));
  }, [kind, id]);

  if (!can("timetable.entry.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Space wrap>
        <Segmented<Kind> value={kind} onChange={(k) => { setKind(k); setId(null); }}
          options={[{ value: "section", label: tr(L.section, lang) }, { value: "teacher", label: tr(L.teacher, lang) }, { value: "room", label: tr(L.room, lang) }]} />
        <div style={{ minWidth: 240 }} key={kind}>
          <RelationSelect {...SOURCE[kind]} value={id} placeholder={tr(L[kind], lang)} onChange={(v) => setId(v as number | null)} />
        </div>
        {id && (
          <Button icon={<PrinterOutlined />} href={`${API}/timetable/views/${kind}?${PARAM[kind]}=${id}&pdf=1`} target="_blank">
            {tr(L.print, lang)}
          </Button>
        )}
      </Space>
      {!grid && <Empty />}
      {grid && <TimetableGrid grid={grid} />}
    </Space>
  );
}
