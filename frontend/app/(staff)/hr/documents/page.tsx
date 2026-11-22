"use client";

import { DeleteOutlined, DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, App, Button, Card, Form, Input, Popconfirm, Result, Select, Space, Table, Typography, Upload } from "antd";
import type { UploadFile } from "antd";
import { useCallback, useEffect, useState } from "react";

import { RelationSelect } from "@/components/staff/fields";
import { UI } from "@/lib/i18n";
import { api, API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr, type T } from "@/lib/resources";

/** Staff documents: upload (PDF/JPG/PNG ≤ 5 MB), list, private download, delete. */
interface Doc { id: number; staff: number; staff_name: string; kind: string; title: string; original_name: string; size: number; uploaded_by: string; created_at: string; download_url: string }

const t = (en: string, hi: string): T => ({ en, hi });
const L = {
  title: t("Staff documents", "कर्मचारी दस्तावेज़"),
  staff: t("Staff", "कर्मचारी"), kind: t("Type", "प्रकार"), docTitle: t("Title", "शीर्षक"), file: t("File (PDF, JPG or PNG, up to 5 MB)", "फ़ाइल (PDF, JPG या PNG, 5 MB तक)"),
  upload: t("Upload", "अपलोड"), uploaded: t("Uploaded", "अपलोड हुआ"), by: t("By", "द्वारा"), size: t("Size", "आकार"),
  pick: t("Choose a staff member to see their documents.", "दस्तावेज़ देखने के लिए कर्मचारी चुनें।"),
};
const KINDS = [
  { value: "appointment", label: t("Appointment letter", "नियुक्ति पत्र") },
  { value: "certificate", label: t("Certificate", "प्रमाणपत्र") },
  { value: "id_proof", label: t("ID proof", "पहचान प्रमाण") },
  { value: "other", label: t("Other", "अन्य") },
];

export default function StaffDocuments() {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const [staff, setStaff] = useState<number | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [form] = Form.useForm();

  const load = useCallback(async () => {
    if (!staff) return setDocs([]);
    const res = await api.get<{ results: Doc[] }>(`hr/documents?staff=${staff}&page_size=100`);
    setDocs(res.results);
  }, [staff]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!can("hr.document.view")) return <Result status="403" title={tr(UI.noAccess, lang)} />;
  const canManage = can("hr.document.manage") && !allBranches;

  async function upload(values: { kind: string; title: string }) {
    const f = files[0]?.originFileObj;
    if (!staff || !f) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append("staff", String(staff));
      body.append("kind", values.kind);
      body.append("title", values.title);
      body.append("file", f);
      await api.post("hr/documents", body);
      message.success(tr(UI.done, lang));
      form.resetFields();
      setFiles([]);
      await load();
    } catch (e) {
      const err = e as { message?: string; errors?: Record<string, string[]> };
      message.error(err.errors?.file?.[0] ?? err.message ?? "Error");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await fetch(`${API}/hr/documents/${id}`, { method: "DELETE", credentials: "same-origin" });
    await load();
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: "100%", padding: 8 }}>
      <Typography.Title level={3} style={{ margin: 0 }}>{tr(L.title, lang)}</Typography.Title>
      <RelationSelect resource="people/staff" label="full_name" search value={staff ?? undefined}
        onChange={(v) => setStaff((v as number) ?? null)} style={{ minWidth: 280 }} placeholder={tr(L.staff, lang)} />
      {!staff && <Alert type="info" showIcon message={tr(L.pick, lang)} />}
      {staff && canManage && (
        <Card size="small">
          <Form form={form} layout="inline" onFinish={upload} initialValues={{ kind: "appointment" }}>
            <Form.Item name="kind" label={tr(L.kind, lang)}>
              <Select style={{ width: 180 }} options={KINDS.map((k) => ({ value: k.value, label: tr(k.label, lang) }))} />
            </Form.Item>
            <Form.Item name="title" label={tr(L.docTitle, lang)} rules={[{ required: true }]}><Input style={{ width: 220 }} /></Form.Item>
            <Form.Item label={tr(L.file, lang)} required>
              <Upload accept=".pdf,.jpg,.jpeg,.png" maxCount={1} fileList={files} beforeUpload={() => false}
                onChange={({ fileList }) => setFiles(fileList.slice(-1))}>
                <Button icon={<UploadOutlined />}>{tr(L.file, lang).split(" (")[0]}</Button>
              </Upload>
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={busy} disabled={!files.length}>{tr(L.upload, lang)}</Button>
          </Form>
        </Card>
      )}
      {staff && (
        <Table<Doc> rowKey="id" size="small" dataSource={docs} pagination={false}
          columns={[
            { title: tr(L.docTitle, lang), dataIndex: "title" },
            { title: tr(L.kind, lang), dataIndex: "kind", render: (v) => tr(KINDS.find((k) => k.value === v)?.label ?? L.kind, lang) },
            { title: tr(L.size, lang), dataIndex: "size", render: (v: number) => `${Math.ceil(v / 1024)} KB` },
            { title: tr(L.uploaded, lang), dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleDateString("en-IN") },
            { title: tr(L.by, lang), dataIndex: "uploaded_by", responsive: ["md"] },
            {
              title: tr(UI.actions, lang), key: "a",
              render: (_, d) => (
                <Space>
                  <Button size="small" icon={<DownloadOutlined />} href={`${API}/hr/documents/${d.id}/download`} />
                  {canManage && (
                    <Popconfirm title={tr(UI.confirm, lang)} onConfirm={() => remove(d.id)}>
                      <Button size="small" danger icon={<DeleteOutlined />} />
                    </Popconfirm>
                  )}
                </Space>
              ),
            },
          ]}
        />
      )}
    </Space>
  );
}
