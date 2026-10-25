"use client";

import { Alert, App, Empty, Form, Modal, Result, Space, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { type Grid, TimetableGrid } from "@/components/staff/TimetableGrid";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Place periods on a section's week; every clash is refused by the server with the reason. */
const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Build timetable", "समय-सारणी बनाएँ"),
  section: t("Section", "अनुभाग"),
  pick: t("Choose a section", "अनुभाग चुनें"),
  add: t("Add period", "कालांश जोड़ें"),
  teaching: t("Subject and teacher (from the teaching allocation)", "विषय एवं शिक्षक (शिक्षण आवंटन से)"),
  room: t("Room (optional)", "कक्ष (वैकल्पिक)"),
  noSchedule: t("No bell schedule applies to this section. Create one under Timetable → Bell schedules.",
    "इस अनुभाग पर कोई घंटी समय-सारणी लागू नहीं। समय-सारणी → घंटी समय-सारणी में बनाएँ।"),
};

export default function Builder() {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const [section, setSection] = useState<number | null>(null);
  const [grid, setGrid] = useState<Grid | null>(null);
  const [adding, setAdding] = useState<{ day: number; slot: number } | null>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setGrid(section ? await api.get<Grid>(`timetable/views/section?section=${section}`) : null);
  }, [section]);
  useEffect(() => {
    void load();
  }, [load]);

  if (!can("timetable.entry.manage")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  if (allBranches) return <Result status="info" title={tr(UI.readOnlyAll, lang)} />;

  const fail = (e: unknown) => {
    const err = e as { message?: string; errors?: Record<string, string[]> };
    message.error((err.errors ? Object.values(err.errors).flat()[0] : undefined) ?? err.message ?? "Error", 6);
  };

  async function add(values: { assignment: number; room?: number | null }) {
    if (!adding || !section) return;
    setSaving(true);
    try {
      await api.post("timetable/entries", { section, day: adding.day, slot: adding.slot, assignment: values.assignment, room: values.room ?? null });
      setAdding(null);
      form.resetFields();
      await load();
    } catch (e) {
      fail(e);
    } finally {
      setSaving(false);
    }
  }

  async function remove(entry: number) {
    try {
      await fetch(`/api/proxy/timetable/entries/${entry}`, { method: "DELETE", credentials: "same-origin" });
      await load();
    } catch (e) {
      fail(e);
    }
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <div style={{ maxWidth: 280 }}>
        <RelationSelect resource="people/sections" label="label" value={section} placeholder={tr(L.section, lang)}
          onChange={(v) => setSection(v as number | null)} />
      </div>
      {!section && <Empty description={tr(L.pick, lang)} />}
      {grid && !grid.schedule && <Alert type="warning" showIcon message={tr(L.noSchedule, lang)} />}
      {grid && grid.schedule && (
        <>
          <Typography.Text type="secondary">{grid.title} · {grid.schedule}</Typography.Text>
          <TimetableGrid grid={grid} onAdd={(day, slot) => setAdding({ day, slot })} onRemove={remove} />
        </>
      )}
      <Modal open={adding !== null} title={tr(L.add, lang)} onCancel={() => setAdding(null)} onOk={() => form.submit()}
        okButtonProps={{ loading: saving }} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={add}>
          <Form.Item name="assignment" label={tr(L.teaching, lang)} rules={[{ required: true }]}>
            <RelationSelect resource="people/teaching" label="label" filters={[{ field: "section", value: section }]} />
          </Form.Item>
          <Form.Item name="room" label={tr(L.room, lang)}>
            <RelationSelect resource="timetable/rooms" label="name" />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
