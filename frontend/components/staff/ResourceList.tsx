"use client";

import { DeleteButton, EditButton, List, useTable } from "@refinedev/antd";
import { useCustomMutation, useInvalidate } from "@refinedev/core";
import { Alert, App, Button, Input, Popconfirm, Select, Space, Table } from "antd";
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

  const { tableProps, setFilters } = useTable<Row>({
    resource: def.name,
    syncWithLocation: true,
    pagination: { pageSize: 25 },
    sorters: { initial: def.defaultSort ? [def.defaultSort] : [] },
  });

  const canManage = can(`${def.perm}.manage`) && !allBranches;

  async function runAction(action: ActionDef, row: Row) {
    const key = `${action.key}-${row.id}`;
    setBusy(key);
    try {
      await mutateAsync({
        url: `${API}/${def.name}/${row.id}/${action.path ? `${action.path}/` : ""}`,
        method: action.method,
        values: action.body ?? {},
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
                        onClick={a.confirm ? undefined : () => runAction(a, row)}>
                        {tr(a.label, lang)}
                      </Button>
                    );
                    return a.confirm ? (
                      <Popconfirm key={a.key} title={tr(a.confirm, lang)} okText={tr(UI.yes, lang)} cancelText={tr(UI.no, lang)}
                        onConfirm={() => runAction(a, row)}>
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
    </List>
  );
}
