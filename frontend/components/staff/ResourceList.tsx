"use client";

import { DeleteButton, EditButton, List, useTable } from "@refinedev/antd";
import { DownloadOutlined } from "@ant-design/icons";
import { useCustomMutation, useInvalidate } from "@refinedev/core";
import { Alert, App, Button, Dropdown, Input, Modal, Popconfirm, Select, Space, Table } from "antd";
import { useState } from "react";

import { getPath, RelationSelect, renderCell } from "@/components/staff/fields";
import { ImportModal } from "@/components/staff/ImportModal";
import { UI } from "@/lib/i18n";
import { API } from "@/lib/refine/dataProvider";
import { useSession } from "@/lib/refine/session";
import type { ActionDef, ResourceDef } from "@/lib/resources";
import { tr } from "@/lib/resources";

type Row = Record<string, unknown> & { id: number };

export function ResourceList({ def }: { def: ResourceDef }) {
  const { lang, can, allBranches } = useSession();
  const { message } = App.useApp();
  const invalidate = useInvalidate();
  const { mutateAsync } = useCustomMutation();
  const [busy, setBusy] = useState<string | null>(null);

  const [prompting, setPrompting] = useState<{ action: ActionDef; row: Row; value: string } | null>(null);

  const { tableProps, setFilters, filters, sorters } = useTable<Row>({
    resource: def.name,
    syncWithLocation: true,
    pagination: { pageSize: 25 },
    sorters: { initial: def.defaultSort ? [def.defaultSort] : [] },
  });

  const canManage = can(`${def.perm}.manage`) && !allBranches;

  function exportUrl(format: "xlsx" | "csv") {
    const q = new URLSearchParams({ format });
    for (const f of filters) {
      if (!("field" in f) || f.value === undefined || f.value === null || f.value === "") continue;
      q.set(f.field === "q" ? "search" : f.field, String(f.value));
    }
    if (sorters.length) q.set("ordering", sorters.map((s) => (s.order === "desc" ? `-${s.field}` : s.field)).join(","));
    return `${API}/${def.name}?${q}`;
  }

  function startAction(action: ActionDef, row: Row) {
    if (action.method === "link") {
      const href = (action.href ?? "").replace("{id}", String(row.id));
      if (action.newTab) window.open(href, "_blank", "noopener");
      else window.location.assign(href);
      return;
    }
    if (action.prompt) {
      setPrompting({ action, row, value: "" });
      return;
    }
    void runAction(action, row);
  }

  async function runAction(action: ActionDef, row: Row, extra?: Record<string, unknown>) {
    const key = `${action.key}-${row.id}`;
    setBusy(key);
    try {
      await mutateAsync({
        url: `${API}/${def.name}/${row.id}/${action.path ? `${action.path}/` : ""}`,
        method: action.method as "post" | "patch",
        values: { ...(action.body ?? {}), ...(extra ?? {}) },
        successNotification: () => ({ type: "success", message: tr(UI.done, lang) }),
        errorNotification: (err) => ({ type: "error", message: err?.message ?? "Error" }),
      });
      invalidate({ resource: def.name, invalidates: ["list"] });
    } catch {
      /* notification already shown */
    } finally {
      setBusy(null);
    }
  }

  const rowActions = (def.actions ?? []).filter((a) => can(a.perm) && !allBranches);
  const showActions = rowActions.length > 0 || (canManage && (def.canEdit || def.canDelete));

  return (
    <List
      title={tr(def.label, lang)}
      canCreate={Boolean(def.canCreate) && canManage}
      headerButtons={({ defaultButtons }) => (
        <Space wrap>
          {def.importable && canManage && <ImportModal resource={def.name} />}
          {def.exportable !== false && (
            <Dropdown
              menu={{
                items: [
                  { key: "xlsx", label: <a href={exportUrl("xlsx")}>Excel (.xlsx)</a> },
                  { key: "csv", label: <a href={exportUrl("csv")}>CSV</a> },
                ],
              }}
            >
              <Button icon={<DownloadOutlined />}>{tr(UI.export, lang)}</Button>
            </Dropdown>
          )}
          {defaultButtons}
        </Space>
      )}
    >
      {allBranches && <Alert style={{ marginBottom: 12 }} type="info" showIcon message={tr(UI.readOnlyAll, lang)} />}
      <Space wrap style={{ marginBottom: 12 }}>
        {def.searchable && (
          <Input.Search
            allowClear
            placeholder={tr(UI.search, lang)}
            style={{ width: 260 }}
            onSearch={(v) => setFilters([{ field: "q", operator: "contains", value: v }], "merge")}
          />
        )}
        {(def.filters ?? []).map((f) =>
          f.options ? (
            <Select
              key={f.field}
              allowClear
              placeholder={tr(f.label, lang)}
              style={{ minWidth: 160 }}
              options={f.options.map((o) => ({ value: o.value, label: tr(o.label, lang) }))}
              onChange={(v) => setFilters([{ field: f.field, operator: "eq", value: v }], "merge")}
            />
          ) : f.relation ? (
            <div key={f.field} style={{ minWidth: 200 }}>
              <RelationSelect
                resource={f.relation.resource}
                label={f.relation.label}
                search={f.relation.search}
                placeholder={tr(f.label, lang)}
                onChange={(v) => setFilters([{ field: f.field, operator: "eq", value: v }], "merge")}
              />
            </div>
          ) : null,
        )}
      </Space>
      <Table<Row> {...tableProps} rowKey="id" scroll={{ x: true }} size="middle">
        {def.columns.map((col) => (
          <Table.Column<Row>
            key={col.key}
            dataIndex={col.key.split(".")}
            title={tr(col.label, lang)}
            sorter={col.sorter ? { multiple: 1 } : undefined}
            render={(_, row) => renderCell(col, getPath(row, col.key), lang)}
          />
        ))}
        {showActions && (
          <Table.Column<Row>
            key="__actions"
            title={tr(UI.actions, lang)}
            fixed="right"
            render={(_, row) => (
              <Space size="small" wrap>
                {rowActions
                  .filter((a) => !a.visibleWhen || getPath(row, a.visibleWhen.field) === a.visibleWhen.equals)
                  .map((a) => {
                    const btn = (
                      <Button size="small" danger={a.danger} loading={busy === `${a.key}-${row.id}`}
                        onClick={a.confirm ? undefined : () => startAction(a, row)}>
                        {tr(a.label, lang)}
                      </Button>
                    );
                    return a.confirm ? (
                      <Popconfirm key={a.key} title={tr(a.confirm, lang)} okText={tr(UI.yes, lang)} cancelText={tr(UI.no, lang)}
                        onConfirm={() => startAction(a, row)}>
                        {btn}
                      </Popconfirm>
                    ) : (
                      <span key={a.key}>{btn}</span>
                    );
                  })}
                {def.canEdit && canManage && <EditButton hideText size="small" recordItemId={row.id} />}
                {def.canDelete && canManage && (
                  <DeleteButton hideText={!def.deleteLabel} size="small" recordItemId={row.id}
                    confirmTitle={tr(UI.confirm, lang)} confirmOkText={tr(UI.yes, lang)} confirmCancelText={tr(UI.no, lang)}>
                    {def.deleteLabel ? tr(def.deleteLabel, lang) : undefined}
                  </DeleteButton>
                )}
              </Space>
            )}
          />
        )}
      </Table>
      <Modal
        open={prompting !== null}
        title={prompting ? `${tr(prompting.action.label, lang)} — ${prompting.action.prompt ? tr(prompting.action.prompt.label, lang) : ""}` : ""}
        okText={prompting ? tr(prompting.action.label, lang) : undefined}
        okButtonProps={{ danger: prompting?.action.danger, disabled: !prompting?.value.trim() }}
        cancelText={tr(UI.no, lang)}
        onCancel={() => setPrompting(null)}
        onOk={async () => {
          if (!prompting?.action.prompt) return;
          const { action, row, value } = prompting;
          setPrompting(null);
          await runAction(action, row, { [action.prompt!.field]: value.trim() });
        }}
        destroyOnHidden
      >
        <Input.TextArea
          autoFocus
          rows={3}
          maxLength={200}
          value={prompting?.value ?? ""}
          onChange={(e) => setPrompting((p) => (p ? { ...p, value: e.target.value } : p))}
        />
      </Modal>
    </List>
  );
}
