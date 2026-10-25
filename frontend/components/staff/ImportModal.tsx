"use client";

import { UploadOutlined } from "@ant-design/icons";
import { useInvalidate } from "@refinedev/core";
import { Alert, App, Button, Modal, Space, Table, Upload } from "antd";
import { useState } from "react";

import { UI } from "@/lib/i18n";
import { API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import { tr } from "@/lib/resources";

interface ImportResult {
  created: number;
  dry_run: boolean;
  errors: { row: number; errors: string[] }[];
}

/** Excel/CSV import with "check only" first; nothing is saved if any row fails. */
export function ImportModal({ resource }: { resource: string }) {
  const { lang } = useSession();
  const { message } = App.useApp();
  const invalidate = useInvalidate();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);

  async function run(dryRun: boolean) {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append("file", file);
    form.append("dry_run", dryRun ? "true" : "false");
    try {
      // Read the body whatever the status: a 400 here carries the row errors.
      const res = await fetch(`${API}/${resource}/import`, { method: "POST", body: form, credentials: "same-origin" });
      const body = (await res.json().catch(() => null)) as (ImportResult & { file?: string[]; detail?: string }) | null;
      if (body && Array.isArray(body.errors)) {
        setResult(body);
        if (res.ok && !body.dry_run) {
          message.success(`${tr(UI.imported, lang)}: ${body.created}`);
          invalidate({ resource, invalidates: ["list"] });
          setOpen(false);
        }
      } else {
        const reason = body?.file?.[0] ?? body?.detail ?? `HTTP ${res.status}`;
        setResult({ created: 0, dry_run: true, errors: [{ row: 0, errors: [reason] }] });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button icon={<UploadOutlined />} onClick={() => setOpen(true)}>
        {tr(UI.import, lang)}
      </Button>
      <Modal
        open={open}
        title={tr(UI.import, lang)}
        onCancel={() => setOpen(false)}
        footer={
          <Space>
            <Button onClick={() => run(true)} disabled={!file} loading={busy}>
              {tr(UI.checkOnly, lang)}
            </Button>
            <Button type="primary" onClick={() => run(false)} disabled={!file} loading={busy}>
              {tr(UI.importNow, lang)}
            </Button>
          </Space>
        }
        width={720}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Alert type="info" showIcon message={tr(UI.importHelp, lang)} />
          <Upload
            accept=".xlsx,.csv"
            maxCount={1}
            beforeUpload={(f) => {
              setFile(f);
              setResult(null);
              return false;
            }}
            onRemove={() => setFile(null)}
          >
            <Button icon={<UploadOutlined />}>.xlsx / .csv</Button>
          </Upload>
          {result && result.errors.length === 0 && (
            <Alert type="success" showIcon message={`${tr(UI.allOk, lang)} (${result.created})`} />
          )}
          {result && result.errors.length > 0 && (
            <Table
              size="small"
              rowKey={(r) => String(r.row)}
              pagination={false}
              dataSource={result.errors}
              columns={[
                { title: tr(UI.row, lang), dataIndex: "row", width: 80 },
                { title: "", dataIndex: "errors", render: (e: string[]) => e.join("; ") },
              ]}
            />
          )}
        </Space>
      </Modal>
    </>
  );
}
