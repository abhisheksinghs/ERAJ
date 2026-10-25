"use client";

import { Create, Edit, useForm } from "@refinedev/antd";
import { Col, Form, Row } from "antd";

import { FormField } from "@/components/staff/fields";
import { useSession } from "@/lib/refine/session";
import type { ResourceDef } from "@/lib/resources";
import { tr } from "@/lib/resources";

export function ResourceForm({ def, mode, id }: { def: ResourceDef; mode: "create" | "edit"; id?: string }) {
  const { lang } = useSession();
  const { formProps, saveButtonProps } = useForm({
    resource: def.name,
    action: mode,
    id,
    redirect: "list",
    meta: { createEndpoint: def.createEndpoint },
  });

  const fields = (def.fields ?? []).filter((f) => (mode === "create" ? !f.editOnly : !f.createOnly));
  const body = (
    <Form {...formProps} layout="vertical">
      <Row gutter={16}>
        {fields.map((f) => (
          <Col key={f.name} xs={24} md={f.type === "textarea" ? 24 : 12}>
            <FormField field={f} lang={lang} />
          </Col>
        ))}
      </Row>
    </Form>
  );
  const title = tr(def.label, lang);
  return mode === "create" ? (
    <Create title={title} saveButtonProps={saveButtonProps}>
      {body}
    </Create>
  ) : (
    <Edit title={title} saveButtonProps={saveButtonProps}>
      {body}
    </Edit>
  );
}
