"use client";

import { useSelect } from "@refinedev/antd";
import { DatePicker, Form, Input, InputNumber, Select, type SelectProps, Switch, Tag, Typography } from "antd";
import dayjs from "dayjs";

import type { ColumnDef, FieldDef } from "@/lib/resources";
import { tr } from "@/lib/resources";
import type { Lang } from "@/lib/refine/session";

/** Select backed by another resource, searchable on the server. */
export function RelationSelect({
  resource,
  label,
  search,
  value,
  onChange,
  placeholder,
}: {
  resource: string;
  label: string;
  search?: boolean;
  value?: number | null;
  onChange?: (v: number | null) => void;
  placeholder?: string;
}) {
  const { selectProps } = useSelect({
    resource,
    optionLabel: label as never,
    optionValue: "id" as never,
    defaultValue: value ?? undefined,
    pagination: { pageSize: 50, mode: "server" },
    onSearch: search ? (v) => [{ field: "q", operator: "contains", value: v }] : undefined,
    debounce: 300,
  });
  return (
    <Select
      {...(selectProps as unknown as SelectProps<number>)}
      value={value ?? undefined}
      onChange={(v) => onChange?.(v ?? null)}
      allowClear
      showSearch={Boolean(search) || selectProps.showSearch}
      filterOption={search ? false : (input, option) => String(option?.label ?? "").toLowerCase().includes(input.toLowerCase())}
      placeholder={placeholder}
      style={{ width: "100%" }}
    />
  );
}

export function FormField({ field, lang }: { field: FieldDef; lang: Lang }) {
  const common = {
    name: field.name,
    label: tr(field.label, lang),
    rules: field.required ? [{ required: true, message: `${tr(field.label, lang)}?` }] : [],
    extra: field.help ? tr(field.help, lang) : undefined,
  };
  switch (field.type) {
    case "textarea":
      return (
        <Form.Item {...common}>
          <Input.TextArea rows={3} />
        </Form.Item>
      );
    case "number":
      return (
        <Form.Item {...common}>
          <InputNumber style={{ width: "100%" }} />
        </Form.Item>
      );
    case "money":
      return (
        <Form.Item {...common}>
          <InputNumber style={{ width: "100%" }} min={0} step={1} precision={2} prefix="₹" stringMode />
        </Form.Item>
      );
    case "date":
      return (
        <Form.Item
          {...common}
          getValueProps={(v: string | null) => ({ value: v ? dayjs(v) : undefined })}
          normalize={(d: dayjs.Dayjs | null) => (d ? d.format("YYYY-MM-DD") : null)}
        >
          <DatePicker style={{ width: "100%" }} format="DD-MM-YYYY" />
        </Form.Item>
      );
    case "boolean":
      return (
        <Form.Item {...common} valuePropName="checked">
          <Switch />
        </Form.Item>
      );
    case "select":
    case "multiselect":
      return (
        <Form.Item {...common}>
          <Select
            mode={field.type === "multiselect" ? "multiple" : undefined}
            allowClear
            options={field.options?.map((o) => ({ value: o.value, label: tr(o.label, lang) }))}
          />
        </Form.Item>
      );
    case "relation":
      return (
        <Form.Item {...common}>
          <RelationSelect
            resource={field.relation!.resource}
            label={field.relation!.label}
            search={field.relation!.search}
          />
        </Form.Item>
      );
    case "password":
      return (
        <Form.Item {...common}>
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      );
    case "email":
      return (
        <Form.Item {...common} rules={[...common.rules, { type: "email" }]}>
          <Input />
        </Form.Item>
      );
    default:
      return (
        <Form.Item {...common}>
          <Input />
        </Form.Item>
      );
  }
}

export function getPath(row: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, k) => (acc && typeof acc === "object" ? (acc as Record<string, unknown>)[k] : undefined), row);
}

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });

export function renderCell(col: ColumnDef, value: unknown, lang: Lang) {
  if (value === null || value === undefined || value === "") return <Typography.Text type="secondary">—</Typography.Text>;
  switch (col.type) {
    case "money":
      return inr.format(Number(value));
    case "date":
      return dayjs(String(value)).format("DD-MM-YYYY");
    case "datetime":
      return dayjs(String(value)).format("DD-MM-YYYY HH:mm");
    case "bool":
      return value ? <Tag color="green">✓</Tag> : <Tag>—</Tag>;
    case "tag": {
      const opt = col.options?.find((o) => o.value === value);
      return <Tag>{opt ? tr(opt.label, lang) : String(value)}</Tag>;
    }
    default:
      return String(value);
  }
}
