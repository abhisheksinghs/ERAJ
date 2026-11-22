"use client";

import { App, Button, Card, Form, Input, Result, Space, Typography } from "antd";
import { useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Study material with a file (PDF, slides, photos) — the registry form handles notes and links. */
const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Upload study material", "अध्ययन सामग्री अपलोड"), subject: t("Subject", "विषय"), program: t("Class (all sections)", "कक्षा (सभी अनुभाग)"),
  section: t("…or one section", "…या एक अनुभाग"), chapter: t("Chapter", "अध्याय"), name: t("Title", "शीर्षक"), file: t("File (PDF, slides, Word, photo — up to 10 MB)", "फ़ाइल (10 MB तक)"),
  send: t("Upload", "अपलोड करें"), done: t("Uploaded", "अपलोड हुआ"),
};

interface V { subject: number; program?: number; section?: number; chapter?: string; title: string }

export default function Upload() {
  const { lang, can } = useSession();
  const { message } = App.useApp();
  const [form] = Form.useForm<V>();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  if (!can("learning.material.manage")) return <Result status="403" title={tr(UI.noAccess, lang)} />;

  async function send(v: V) {
    if (!file) return;
    const fd = new FormData();
    for (const [k, val] of Object.entries(v)) if (val !== undefined && val !== null && val !== "") fd.append(k, String(val));
    fd.append("kind", "file");
    fd.append("upload", file);
    setBusy(true);
    try { await api.post("learning/materials", fd); message.success(tr(L.done, lang)); form.resetFields(); setFile(null); }
    catch (e) { message.error((e as { message?: string }).message ?? "Error"); }
    finally { setBusy(false); }
  }

  return (
    <Space direction="vertical" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <Card style={{ maxWidth: 640 }}>
        <Form form={form} layout="vertical" onFinish={(v) => void send(v)}>
          <Form.Item name="subject" label={tr(L.subject, lang)} rules={[{ required: true }]}><RelationSelect resource="people/subjects" label="name" search /></Form.Item>
          <Form.Item name="program" label={tr(L.program, lang)}><RelationSelect resource="people/programs" label="name" /></Form.Item>
          <Form.Item name="section" label={tr(L.section, lang)}><RelationSelect resource="people/sections" label="label" search /></Form.Item>
          <Form.Item name="chapter" label={tr(L.chapter, lang)}><Input /></Form.Item>
          <Form.Item name="title" label={tr(L.name, lang)} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item label={tr(L.file, lang)} required>
            <input data-testid="material-file" type="file" accept=".pdf,.pptx,.docx,.jpg,.jpeg,.png" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={busy} disabled={!file}>{tr(L.send, lang)}</Button>
        </Form>
      </Card>
    </Space>
  );
}
